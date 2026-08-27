"""Repositorio de grafo local sobre los JSONL exportados por la capa de datos.

Replica exactamente el contrato de `knowledge_nexus_data.GraphRepository` para
poder desarrollar y probar sin credenciales de Neo4j Aura. Las respuestas tienen
la misma forma en ambos backends, de modo que el motor no distingue cuál usa.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DEFAULT_RELATED_LIMIT = 50

_EXCLUDED_PROPERTIES = frozenset(
    {
        "id",
        "entity_type",
        "title",
        "semantic_text",
        "source_file",
        "source_row",
        "source_path",
    }
)


def _entity_payload(node: dict[str, Any]) -> dict[str, Any]:
    """Construye la misma carga útil que devuelve el repositorio de Neo4j."""

    properties = dict(node.get("properties") or {})
    properties.pop("embedding", None)
    label = node.get("label")
    labels = ["Entity", str(label)] if label else ["Entity"]
    if label and label != "Document":
        labels.append("SemanticEntity")
    return {
        "id": node.get("id"),
        "entity_type": properties.get("entity_type") or label,
        "labels": labels,
        "title": node.get("title"),
        "semantic_text": node.get("semantic_text"),
        "source": {
            "file": properties.get("source_file") or node.get("source_file"),
            "row": properties.get("source_row") or node.get("source_row"),
            "path": properties.get("source_path"),
        },
        "properties": {
            key: value for key, value in properties.items() if key not in _EXCLUDED_PROPERTIES
        },
    }


class JsonlGraphRepository:
    """Implementación local del contrato de lectura del grafo."""

    def __init__(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]):
        self._nodes: dict[str, dict[str, Any]] = {}
        for node in nodes:
            identifier = str(node.get("id", "")).strip()
            if not identifier:
                raise ValueError("Nodo sin `id` en graph_nodes.jsonl")
            if identifier in self._nodes:
                raise ValueError(f"ID de nodo duplicado en el grafo: {identifier}")
            self._nodes[identifier] = node
        self._edges = edges
        self._outgoing: dict[str, list[dict[str, Any]]] = {}
        self._incoming: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            source_id = str(edge.get("source_id"))
            target_id = str(edge.get("target_id"))
            if source_id not in self._nodes or target_id not in self._nodes:
                # La capa de datos garantiza integridad referencial; una arista
                # colgante se ignora en lectura y se reporta a la persona 1.
                continue
            self._outgoing.setdefault(source_id, []).append(edge)
            self._incoming.setdefault(target_id, []).append(edge)

    # Construcción -------------------------------------------------------
    @classmethod
    def from_jsonl(cls, nodes_path: Path, edges_path: Path) -> "JsonlGraphRepository":
        return cls(_read_jsonl(nodes_path), _read_jsonl(edges_path))

    def close(self) -> None:  # Compatibilidad con el repositorio de Neo4j.
        return None

    def __enter__(self) -> "JsonlGraphRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # Contrato de lectura ------------------------------------------------
    def get_entity(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        node = self._nodes.get(_validate_identifier(entity_id))
        if node is None:
            return None
        label = entity_type.strip()
        if label and node.get("label") != label:
            return None
        return _entity_payload(node)

    def get_neighbors(
        self,
        entity_id: str,
        relation_types: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        identifier = _validate_identifier(entity_id)
        allowed = _validate_relation_types(relation_types)
        neighbors: list[dict[str, Any]] = []
        for edge in self._outgoing.get(identifier, []):
            if allowed and edge.get("relationship") not in allowed:
                continue
            neighbors.append(self._neighbor_payload(edge, "OUTGOING", edge["target_id"]))
        for edge in self._incoming.get(identifier, []):
            if allowed and edge.get("relationship") not in allowed:
                continue
            neighbors.append(self._neighbor_payload(edge, "INCOMING", edge["source_id"]))
        return sorted(
            neighbors,
            key=lambda item: (item["relationship"], item["target"]["id"], item["direction"]),
        )

    def get_evidence(self, entity_id: str) -> dict[str, Any] | None:
        identifier = _validate_identifier(entity_id)
        node = self._nodes.get(identifier)
        if node is None:
            return None
        entity = _entity_payload(node)
        documents = [
            _entity_payload(self._nodes[edge["source_id"]])
            for edge in sorted(
                self._incoming.get(identifier, []), key=lambda item: str(item["source_id"])
            )
            if edge.get("relationship") == "DESCRIBES"
        ]
        relation_evidence: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        related = [*self._outgoing.get(identifier, []), *self._incoming.get(identifier, [])]
        for edge in sorted(related, key=lambda item: str(item.get("relationship"))):
            provenance = edge.get("provenance") or []
            if not provenance:
                continue
            key = (str(edge.get("relationship")), json.dumps(provenance, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            relation_evidence.append(
                {
                    "relationship": edge.get("relationship"),
                    "provenance": [dict(item) for item in provenance],
                }
            )
        return {
            "entity_id": identifier,
            "entity": entity,
            "source": entity["source"],
            "documents": documents,
            "relation_evidence": relation_evidence,
        }

    def find_related_entities(self, entity_id: str, target_type: str) -> list[dict[str, Any]]:
        """Coincidencias directas y, solo si no existen, a exactamente dos saltos."""

        identifier = _validate_identifier(entity_id)
        label = target_type.strip()
        direct = self._walk(identifier, label, hops=1, limit=DEFAULT_RELATED_LIMIT)
        if direct:
            return direct
        return self._walk(identifier, label, hops=2, limit=DEFAULT_RELATED_LIMIT)

    # Utilidades internas ------------------------------------------------
    def _neighbor_payload(
        self, edge: dict[str, Any], direction: str, target_id: str
    ) -> dict[str, Any]:
        return {
            "relationship": edge.get("relationship"),
            "direction": direction,
            "relation_origin": edge.get("relation_origin"),
            "properties": dict(edge.get("properties") or {}),
            "provenance": [dict(item) for item in (edge.get("provenance") or [])],
            "target": _entity_payload(self._nodes[target_id]),
        }

    def _walk(
        self, entity_id: str, label: str, hops: int, limit: int
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = {entity_id}
        frontier: list[tuple[str, list[dict[str, Any]]]] = [(entity_id, [])]
        for depth in range(1, hops + 1):
            next_frontier: list[tuple[str, list[dict[str, Any]]]] = []
            for current, path in frontier:
                for neighbor in self.get_neighbors(current):
                    target = neighbor["target"]
                    target_id = str(target["id"])
                    step = {
                        "relationship": neighbor["relationship"],
                        "relation_origin": neighbor["relation_origin"],
                        "properties": neighbor["properties"],
                        "provenance": neighbor["provenance"],
                    }
                    extended = [*path, step]
                    if depth == hops and target_id not in seen and target["entity_type"] == label:
                        seen.add(target_id)
                        results.append({"target": target, "hops": depth, "path": extended})
                    if depth < hops:
                        next_frontier.append((target_id, extended))
            frontier = next_frontier
        results.sort(key=lambda item: (item["hops"], str(item["target"]["id"])))
        return results[:limit]

    # Extensiones locales (no forman parte del contrato compartido) -------
    @property
    def node_ids(self) -> frozenset[str]:
        return frozenset(self._nodes)

    def degree(self, entity_id: str) -> int:
        return len(self._outgoing.get(entity_id, [])) + len(self._incoming.get(entity_id, []))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as error:  # pragma: no cover - datos corruptos
                raise ValueError(f"{path}:{number} no es JSON válido") from error
    return records


def _validate_identifier(entity_id: str) -> str:
    identifier = str(entity_id).strip()
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
        value = str(relationship).strip()
        if not value or not value.replace("_", "").isalnum() or not value.isupper():
            raise ValueError(f"Tipo de relación no permitido: {relationship}")
        validated.append(value)
    return sorted(set(validated))
