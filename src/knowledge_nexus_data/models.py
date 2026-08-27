"""Contratos serializables compartidos con búsqueda e interfaz."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GraphNode:
    id: str
    label: str
    title: str
    properties: dict[str, Any]
    source_file: str
    source_row: int
    semantic_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GraphEdge:
    source_id: str
    source_label: str
    relationship: str
    target_id: str
    target_label: str
    properties: dict[str, Any] = field(default_factory=dict)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    relation_origin: str = "EXPLICIT"

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source_id, self.relationship, self.target_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

