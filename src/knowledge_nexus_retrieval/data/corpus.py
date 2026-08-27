"""Carga y validación del corpus de documentos semánticos."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SemanticDocument:
    """Documento semántico tal como lo entrega la capa de datos."""

    id: str
    entity_type: str
    title: str
    text: str
    source: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "SemanticDocument":
        identifier = str(payload.get("id", "")).strip()
        if not identifier:
            raise ValueError("Documento semántico sin `id`")
        return cls(
            id=identifier,
            entity_type=str(payload.get("entity_type") or "Unknown"),
            title=str(payload.get("title") or ""),
            text=str(payload.get("text") or ""),
            source=dict(payload.get("source") or {}),
            metadata=dict(payload.get("metadata") or {}),
        )


class DuplicateDocumentError(ValueError):
    """Se levanta cuando dos documentos semánticos comparten el mismo ID."""


class SemanticCorpus:
    """Colección inmutable de documentos semánticos indexada por ID."""

    def __init__(self, documents: list[SemanticDocument]):
        self._documents: dict[str, SemanticDocument] = {}
        for document in documents:
            if document.id in self._documents:
                raise DuplicateDocumentError(
                    f"ID duplicado en el corpus semántico: {document.id}"
                )
            self._documents[document.id] = document
        self._order: tuple[str, ...] = tuple(self._documents)
        self._by_type: dict[str, tuple[str, ...]] = {}
        grouped: dict[str, list[str]] = {}
        for document in self._documents.values():
            grouped.setdefault(document.entity_type, []).append(document.id)
        self._by_type = {key: tuple(value) for key, value in grouped.items()}

    @classmethod
    def from_jsonl(cls, path: Path) -> "SemanticCorpus":
        documents: list[SemanticDocument] = []
        with path.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError as error:  # pragma: no cover - datos corruptos
                    raise ValueError(f"{path}:{number} no es JSON válido") from error
                documents.append(SemanticDocument.from_json(payload))
        return cls(documents)

    def __len__(self) -> int:
        return len(self._documents)

    def __contains__(self, identifier: object) -> bool:
        return str(identifier) in self._documents

    def __iter__(self) -> Iterator[SemanticDocument]:
        return iter(self._documents.values())

    def get(self, identifier: str) -> SemanticDocument | None:
        return self._documents.get(identifier)

    def require(self, identifier: str) -> SemanticDocument:
        document = self._documents.get(identifier)
        if document is None:
            raise KeyError(f"No existe el documento semántico {identifier}")
        return document

    @property
    def ids(self) -> tuple[str, ...]:
        return self._order

    @property
    def entity_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_type))

    def ids_of_type(self, entity_type: str) -> tuple[str, ...]:
        return self._by_type.get(entity_type, ())

    def counts_by_type(self) -> dict[str, int]:
        return {key: len(value) for key, value in sorted(self._by_type.items())}
