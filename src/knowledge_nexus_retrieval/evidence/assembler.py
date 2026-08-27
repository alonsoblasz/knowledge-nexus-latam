"""Construye el paquete cerrado de evidencia que respalda cada conexión.

Regla del sistema: si una afirmación no puede vincularse a este paquete, no se
incluye en la respuesta. El paquete se arma **antes** de invocar cualquier LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..data.graph_port import GraphNavigator, entity_fields
from ..ranking.scorer import ScoredConnection
from ..settings import EngineConfig
from ..text import Lexicon, excerpt, normalize, parse_labeled_sections

MAX_EVIDENCE_PER_CONNECTION = 4


class IdentifierGuard:
    """Valida que toda la respuesta use IDs realmente recuperados."""

    def __init__(self, allowed_ids: set[str]):
        self._allowed = set(allowed_ids)

    def allow(self, identifier: str) -> None:
        self._allowed.add(identifier)

    def contains(self, identifier: str) -> bool:
        return identifier in self._allowed

    @property
    def allowed(self) -> frozenset[str]:
        return frozenset(self._allowed)

    def validate(self, identifiers: list[str], where: str) -> None:
        unknown = sorted({item for item in identifiers if item not in self._allowed})
        if unknown:
            raise ValueError(
                f"{where}: la respuesta referencia IDs que no están en el paquete "
                f"recuperado: {unknown}"
            )

    def filter(self, identifiers: list[str]) -> list[str]:
        return [item for item in identifiers if item in self._allowed]


@dataclass
class EvidencePackage:
    """Conjunto cerrado de entidades, conexiones y evidencia de una consulta."""

    entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence_by_connection: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    guard: IdentifierGuard = field(default_factory=lambda: IdentifierGuard(set()))

    def register_entity(self, entity: dict[str, Any]) -> None:
        identifier = str(entity.get("id"))
        if identifier:
            self.entities[identifier] = entity
            self.guard.allow(identifier)

    def entity_summary(self, identifier: str) -> dict[str, Any] | None:
        entity = self.entities.get(identifier)
        if entity is None:
            return None
        return {
            "id": entity.get("id"),
            "type": entity.get("entity_type"),
            "title": entity.get("title"),
        }


class EvidenceAssembler:
    """Selecciona los campos y relaciones que justifican cada conexión."""

    def __init__(self, config: EngineConfig, navigator: GraphNavigator, lexicon: Lexicon):
        self._config = config
        self._navigator = navigator
        self._lexicon = lexicon

    def assemble(
        self, connection: ScoredConnection, max_items: int = MAX_EVIDENCE_PER_CONNECTION
    ) -> list[dict[str, Any]]:
        candidate = connection.candidate
        entity = candidate.entity
        source = entity.get("source") or {}
        profile = self._config.profile(candidate.entity_type)
        properties = entity_fields(entity)
        if not properties and candidate.document is not None:
            # Sin propiedades normalizadas se recupera el campo desde el texto
            # semántico etiquetado, conservando el nombre real del campo.
            properties = parse_labeled_sections(candidate.document.text)

        matched_terms = [normalize(term) for term in candidate.matched_terms]
        fields = [name for name in (profile.get("evidence_fields") or []) if properties.get(name)]
        scored_fields: list[tuple[int, int, str]] = []
        for position, name in enumerate(fields):
            haystack = normalize(properties.get(name))
            hits = sum(1 for term in matched_terms if term and term in haystack)
            scored_fields.append((-hits, position, name))
        scored_fields.sort()

        items: list[dict[str, Any]] = []
        for negative_hits, _, name in scored_fields:
            if len(items) >= max_items:
                break
            items.append(
                {
                    "file": source.get("file"),
                    "row": source.get("row"),
                    "record_id": candidate.id,
                    "field": name,
                    "excerpt": excerpt(properties.get(name)),
                    "path": source.get("path"),
                    "origin": "entity_field",
                    "matched_query_terms": -negative_hits,
                }
            )

        for item in self._relation_evidence(connection):
            if len(items) >= max_items + 2:
                break
            items.append(item)

        if not items and candidate.document is not None:
            document_source = candidate.document.source or {}
            items.append(
                {
                    "file": document_source.get("file"),
                    "row": document_source.get("row"),
                    "record_id": candidate.id,
                    "field": "semantic_text",
                    "excerpt": excerpt(candidate.document.text),
                    "path": document_source.get("path"),
                    "origin": "semantic_document",
                    "matched_query_terms": 0,
                }
            )
        return items

    def _relation_evidence(self, connection: ScoredConnection) -> list[dict[str, Any]]:
        """Procedencia de las relaciones explícitas usadas en la expansión."""

        candidate = connection.candidate
        items: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for step in candidate.graph_path:
            # Solo se cita el tramo del camino que involucra al propio candidato:
            # la fila de otra entidad no es evidencia de esta conexión.
            if candidate.id not in {str(step.get("from_id")), str(step.get("to_id"))}:
                continue
            for provenance in step.get("provenance") or []:
                fields = provenance.get("fields") or (
                    [provenance["field"]] if provenance.get("field") else []
                )
                key = (
                    provenance.get("file"),
                    provenance.get("row"),
                    step.get("relationship"),
                    tuple(fields),
                )
                if key in seen:
                    continue
                seen.add(key)
                # `direction` indica el sentido real de la arista respecto al
                # nodo desde el que se avanzó durante la expansión.
                if step.get("direction") == "INCOMING":
                    origin, destination = step.get("to_id"), step.get("from_id")
                else:
                    origin, destination = step.get("from_id"), step.get("to_id")
                items.append(
                    {
                        "file": _basename(provenance.get("file")),
                        "row": provenance.get("row"),
                        "record_id": str(step.get("to_id") or candidate.id),
                        "field": ", ".join(str(item) for item in fields) or "relationship",
                        "excerpt": (
                            f"{origin} -[{step.get('relationship')}]-> "
                            f"{destination} (relación explícita de Data V1.0)"
                        ),
                        "path": provenance.get("file"),
                        "origin": "explicit_relation",
                        "relation_origin": step.get("relation_origin"),
                    }
                )
        return items

    def entity_evidence(self, entity_id: str) -> list[dict[str, Any]]:
        """Evidencia de relaciones de una entidad, para el endpoint de detalle."""

        items: list[dict[str, Any]] = []
        for neighbor in self._navigator.neighbors(entity_id):
            for provenance in neighbor.get("provenance") or []:
                fields = provenance.get("fields") or (
                    [provenance["field"]] if provenance.get("field") else []
                )
                items.append(
                    {
                        "file": _basename(provenance.get("file")),
                        "row": provenance.get("row"),
                        "record_id": str(neighbor["target"]["id"]),
                        "field": ", ".join(str(item) for item in fields) or "relationship",
                        "excerpt": (
                            f"{entity_id} -[{neighbor['relationship']}]- "
                            f"{neighbor['target']['id']}"
                        ),
                        "path": provenance.get("file"),
                        "origin": "explicit_relation",
                        "relation_origin": neighbor.get("relation_origin"),
                    }
                )
        return items


def _basename(path: Any) -> str | None:
    if path in (None, ""):
        return None
    return str(path).replace("\\", "/").split("/")[-1]
