"""Índice vectorial en memoria a partir del artefacto de embeddings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ..data.corpus import SemanticCorpus
from .pipeline import text_sha256


class EmbeddingStoreError(RuntimeError):
    """Problemas de carga o consistencia del artefacto de embeddings."""


class EmbeddingStore:
    """Vectores normalizados indexados por ID, con su modelo y dimensión."""

    def __init__(
        self,
        ids: list[str],
        matrix: np.ndarray,
        model: str,
        dimension: int,
        entity_types: list[str] | None = None,
        text_hashes: list[str] | None = None,
    ):
        if matrix.shape[0] != len(ids):
            raise EmbeddingStoreError("La matriz no coincide con el número de IDs")
        self._ids = ids
        self._index = {identifier: position for position, identifier in enumerate(ids)}
        if len(self._index) != len(ids):
            raise EmbeddingStoreError("Hay IDs duplicados en el artefacto de embeddings")
        self._matrix = matrix.astype(np.float32)
        self._model = model
        self._dimension = dimension
        self._entity_types = entity_types or ["Unknown"] * len(ids)
        self._text_hashes = text_hashes or [""] * len(ids)
        self._rows_by_type: dict[str, np.ndarray] = {}
        for position, entity_type in enumerate(self._entity_types):
            self._rows_by_type.setdefault(entity_type, []).append(position)  # type: ignore[arg-type]
        self._rows_by_type = {
            key: np.asarray(value, dtype=np.int32)
            for key, value in self._rows_by_type.items()  # type: ignore[union-attr]
        }

    # Carga ---------------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "EmbeddingStore":
        if not path.is_file():
            raise EmbeddingStoreError(
                f"No existe el artefacto de embeddings en {path}. "
                "Genera los vectores con `knowledge-nexus embeddings build`."
            )
        ids: list[str] = []
        entity_types: list[str] = []
        hashes: list[str] = []
        vectors: list[list[float]] = []
        model: str | None = None
        dimension: int | None = None
        with path.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                record = json.loads(stripped)
                identifier = str(record.get("id", ""))
                if not identifier:
                    raise EmbeddingStoreError(f"{path}:{number} no tiene `id`")
                record_model = str(record.get("model", ""))
                record_dimension = int(record.get("dimension", 0))
                if model is None:
                    model, dimension = record_model, record_dimension
                elif record_model != model or record_dimension != dimension:
                    raise EmbeddingStoreError(
                        f"{path}:{number} mezcla modelos o dimensiones "
                        f"({record_model}/{record_dimension} frente a {model}/{dimension})."
                    )
                embedding = record.get("embedding") or []
                if len(embedding) != record_dimension:
                    raise EmbeddingStoreError(
                        f"{path}:{number} declara dimensión {record_dimension} "
                        f"pero el vector tiene {len(embedding)} valores."
                    )
                ids.append(identifier)
                entity_types.append(str(record.get("entity_type") or "Unknown"))
                hashes.append(str(record.get("text_sha256") or ""))
                vectors.append(embedding)
        if not ids or model is None or dimension is None:
            raise EmbeddingStoreError(f"El artefacto {path} está vacío")
        matrix = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        matrix = matrix / norms
        return cls(ids, matrix, model, dimension, entity_types, hashes)

    # Propiedades ---------------------------------------------------------
    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def ids(self) -> list[str]:
        return list(self._ids)

    @property
    def matrix(self) -> np.ndarray:
        return self._matrix

    def __len__(self) -> int:
        return len(self._ids)

    def __contains__(self, identifier: object) -> bool:
        return str(identifier) in self._index

    def vector(self, identifier: str) -> np.ndarray | None:
        position = self._index.get(identifier)
        if position is None:
            return None
        return self._matrix[position]

    def rows_of_type(self, entity_type: str) -> np.ndarray:
        return self._rows_by_type.get(entity_type, np.asarray([], dtype=np.int32))

    def id_at(self, position: int) -> str:
        return self._ids[position]

    # Validaciones --------------------------------------------------------
    def validate_coverage(self, corpus: SemanticCorpus) -> None:
        """Comprueba cobertura total y que el texto indexado no haya cambiado."""

        missing = [identifier for identifier in corpus.ids if identifier not in self._index]
        if missing:
            raise EmbeddingStoreError(
                f"Faltan embeddings para {len(missing)} documentos, por ejemplo {missing[:5]}"
            )
        stale: list[str] = []
        for document in corpus:
            position = self._index[document.id]
            stored = self._text_hashes[position]
            if stored and stored != text_sha256(document.text):
                stale.append(document.id)
        if stale:
            raise EmbeddingStoreError(
                f"{len(stale)} documentos cambiaron desde la última indexación "
                f"(por ejemplo {stale[:5]}). Vuelve a ejecutar el pipeline."
            )

    def validate_provider(self, model: str, dimension: int) -> None:
        """Impide consultar el índice con un modelo distinto al que lo generó."""

        if model != self._model or dimension != self._dimension:
            raise EmbeddingStoreError(
                f"El índice fue generado con {self._model} ({self._dimension}d) y el "
                f"proveedor activo es {model} ({dimension}d). No se pueden mezclar."
            )

    def describe(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for entity_type in self._entity_types:
            counts[entity_type] = counts.get(entity_type, 0) + 1
        return {
            "model": self._model,
            "dimension": self._dimension,
            "vectors": len(self._ids),
            "by_type": dict(sorted(counts.items())),
        }
