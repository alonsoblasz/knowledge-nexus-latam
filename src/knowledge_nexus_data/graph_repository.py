"""Consultas de lectura estables para búsqueda, evidencia e interfaz."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from .catalog import NODE_SPEC_BY_LABEL
from .neo4j_loader import Neo4jConfig, _driver as create_driver


ALLOWED_ENTITY_TYPES = frozenset(NODE_SPEC_BY_LABEL) | {"Document"}
DEFAULT_RELATED_LIMIT = 50


class GraphRepository:
    """Contrato de lectura entre la capa de grafo y el motor de búsqueda."""

    def __init__(self, config: Neo4jConfig, driver: Any | None = None):
        self.config = config
        self._driver = driver or create_driver(config)
        self._owns_driver = driver is None

    @classmethod
    def from_env(cls) -> "GraphRepository":
        return cls(Neo4jConfig.from_env())

    def close(self) -> None:
        if self._owns_driver:
            self._driver.close()

    def __enter__(self) -> "GraphRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_entity(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        """Devuelve una entidad canónica por tipo e ID, o ``None`` si no existe."""

        label = _validate_entity_type(entity_type)
        identifier = _validate_identifier(entity_id)
        records = self._query(
            f"MATCH (entity:Entity:{label} {{id: $entity_id}}) "
            "RETURN properties(entity) AS properties, labels(entity) AS labels",
            entity_id=identifier,
        )
        if not records:
            return None
        return _entity_payload(records[0]["properties"], records[0]["labels"])

    def get_neighbors(
        self,
        entity_id: str,
        relation_types: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Devuelve vecinos entrantes y salientes, filtrados por relación opcional."""

        identifier = _validate_identifier(entity_id)
        relationships = _validate_relation_types(relation_types)
        common_return = (
            "RETURN properties(target) AS target_properties, labels(target) AS target_labels, "
            "type(relationship) AS relationship, properties(relationship) AS relation_properties"
        )
        outgoing = self._query(
            "MATCH (:Entity {id: $entity_id})-[relationship]->(target:Entity) "
            "WHERE size($relation_types) = 0 OR type(relationship) IN $relation_types "
            f"{common_return}, 'OUTGOING' AS direction",
            entity_id=identifier,
            relation_types=relationships,
        )
        incoming = self._query(
            "MATCH (:Entity {id: $entity_id})<-[relationship]-(target:Entity) "
            "WHERE size($relation_types) = 0 OR type(relationship) IN $relation_types "
            f"{common_return}, 'INCOMING' AS direction",
            entity_id=identifier,
            relation_types=relationships,
        )
        neighbors = [_neighbor_payload(record) for record in [*outgoing, *incoming]]
        return sorted(
            neighbors,
            key=lambda item: (
                item["relationship"],
                item["target"]["id"],
                item["direction"],
            ),
        )

    def get_evidence(self, entity_id: str) -> dict[str, Any] | None:
        """Devuelve procedencia, documentos y evidencia de relaciones de una entidad."""

        identifier = _validate_identifier(entity_id)
        entity_records = self._query(
            "MATCH (entity:Entity {id: $entity_id}) "
            "RETURN properties(entity) AS properties, labels(entity) AS labels",
            entity_id=identifier,
        )
        if not entity_records:
            return None
        entity = _entity_payload(
            entity_records[0]["properties"], entity_records[0]["labels"]
        )
        document_records = self._query(
            "MATCH (document:Document)-[:DESCRIBES]->(:Entity {id: $entity_id}) "
            "RETURN properties(document) AS properties, labels(document) AS labels "
            "ORDER BY document.id",
            entity_id=identifier,
        )
        relation_records = self._query(
            "MATCH (:Entity {id: $entity_id})-[relationship]-() "
            "WHERE relationship.provenance_json IS NOT NULL "
            "RETURN type(relationship) AS relationship, "
            "relationship.provenance_json AS provenance_json "
            "ORDER BY relationship",
            entity_id=identifier,
        )
        relation_evidence: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for record in relation_records:
            raw_provenance = record["provenance_json"] or ""
            key = (record["relationship"], raw_provenance)
            if key in seen:
                continue
            seen.add(key)
            relation_evidence.append(
                {
                    "relationship": record["relationship"],
                    "provenance": _parse_provenance(raw_provenance),
                }
            )
        return {
            "entity_id": identifier,
            "entity": entity,
            "source": entity["source"],
            "documents": [
                _entity_payload(record["properties"], record["labels"])
                for record in document_records
            ],
            "relation_evidence": relation_evidence,
        }

    def find_related_entities(
        self,
        entity_id: str,
        target_type: str,
    ) -> list[dict[str, Any]]:
        """Encuentra entidades directas o, si no existen, a exactamente dos saltos."""

        identifier = _validate_identifier(entity_id)
        label = _validate_entity_type(target_type)
        direct_records = self._query(
            "MATCH (source:Entity {id: $entity_id}) "
            f"MATCH (target:Entity:{label}) "
            "WHERE target <> source "
            "MATCH path = (source)-[*1]-(target) "
            "RETURN properties(target) AS target_properties, labels(target) AS target_labels, "
            "length(path) AS hops, "
            "[item IN relationships(path) | "
            "{relationship: type(item), properties: properties(item)}] AS path_relationships "
            "ORDER BY hops, target.id "
            "LIMIT $limit",
            entity_id=identifier,
            limit=DEFAULT_RELATED_LIMIT,
        )
        if direct_records:
            return _related_payloads(direct_records)
        indirect_records = self._query(
            "MATCH (source:Entity {id: $entity_id}) "
            f"MATCH (target:Entity:{label}) "
            "WHERE target <> source "
            "MATCH path = (source)-[*2]-(target) "
            "RETURN properties(target) AS target_properties, labels(target) AS target_labels, "
            "length(path) AS hops, "
            "[item IN relationships(path) | "
            "{relationship: type(item), properties: properties(item)}] AS path_relationships "
            "ORDER BY target.id "
            "LIMIT $limit",
            entity_id=identifier,
            limit=DEFAULT_RELATED_LIMIT * 4,
        )
        return _related_payloads(indirect_records)[:DEFAULT_RELATED_LIMIT]

    def _query(self, query: str, **parameters: Any) -> list[Any]:
        records, _, _ = self._driver.execute_query(
            query,
            parameters_=parameters,
            database_=self.config.database,
        )
        return list(records)


def _related_payloads(records: list[Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for record in records:
        target = _entity_payload(record["target_properties"], record["target_labels"])
        if target["id"] in seen_ids:
            continue
        seen_ids.add(target["id"])
        results.append(
            {
                "target": target,
                "hops": record["hops"],
                "path": [
                    _path_relationship_payload(item)
                    for item in record["path_relationships"]
                ],
            }
        )
    return results


def _validate_entity_type(entity_type: str) -> str:
    label = entity_type.strip()
    if label not in ALLOWED_ENTITY_TYPES:
        allowed = ", ".join(sorted(ALLOWED_ENTITY_TYPES))
        raise ValueError(f"Tipo de entidad no permitido: {entity_type}. Permitidos: {allowed}")
    return label


def _validate_identifier(entity_id: str) -> str:
    identifier = entity_id.strip()
    if not identifier:
        raise ValueError("entity_id no puede estar vacío")
    return identifier


def _validate_relation_types(relation_types: Sequence[str] | None) -> list[str]:
    if relation_types is None:
        return []
    if isinstance(relation_types, str):
        raise TypeError("relation_types debe ser una secuencia de nombres, no un texto")
    validated: list[str] = []
    for relationship in relation_types:
        value = relationship.strip()
        if not value or not value.replace("_", "").isalnum() or not value.isupper():
            raise ValueError(f"Tipo de relación no permitido: {relationship}")
        validated.append(value)
    return sorted(set(validated))


def _entity_payload(properties: Any, labels: Any) -> dict[str, Any]:
    values = dict(properties)
    values.pop("embedding", None)
    entity_type = values.get("entity_type") or next(
        (label for label in labels if label not in {"Entity", "SemanticEntity"}),
        None,
    )
    source = {
        "file": values.get("source_file"),
        "row": values.get("source_row"),
        "path": values.get("source_path"),
    }
    excluded = {
        "id",
        "entity_type",
        "title",
        "semantic_text",
        "source_file",
        "source_row",
        "source_path",
    }
    return {
        "id": values.get("id"),
        "entity_type": entity_type,
        "labels": list(labels),
        "title": values.get("title"),
        "semantic_text": values.get("semantic_text"),
        "source": source,
        "properties": {key: value for key, value in values.items() if key not in excluded},
    }


def _neighbor_payload(record: Any) -> dict[str, Any]:
    relation = _relationship_payload(record["relation_properties"])
    return {
        "relationship": record["relationship"],
        "direction": record["direction"],
        "relation_origin": relation["relation_origin"],
        "properties": relation["properties"],
        "provenance": relation["provenance"],
        "target": _entity_payload(record["target_properties"], record["target_labels"]),
    }


def _relationship_payload(properties: Any) -> dict[str, Any]:
    values = dict(properties)
    raw_provenance = values.pop("provenance_json", None)
    return {
        "relation_origin": values.pop("relation_origin", None),
        "properties": values,
        "provenance": _parse_provenance(raw_provenance),
    }


def _path_relationship_payload(item: Any) -> dict[str, Any]:
    relation = _relationship_payload(item["properties"])
    return {
        "relationship": item["relationship"],
        **relation,
    }


def _parse_provenance(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [dict(item) for item in raw]
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return [{"raw": str(raw)}]
    if isinstance(parsed, list):
        return [dict(item) for item in parsed]
    return [{"raw": parsed}]
