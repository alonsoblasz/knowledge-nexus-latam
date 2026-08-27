"""Canal vectorial: búsqueda de vecinos más cercanos por tipo de entidad."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ..embeddings.store import EmbeddingStore


class VectorSearcher:
    """Búsqueda por coseno sobre vectores normalizados, filtrada por tipo.

    Filtrar por tipo antes de ordenar evita listas que mezclan entidades no
    comparables (una asignatura y una tesis compiten en escalas distintas).
    """

    def __init__(self, store: EmbeddingStore):
        self._store = store

    @property
    def store(self) -> EmbeddingStore:
        return self._store

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 30,
        entity_types: Sequence[str] | None = None,
    ) -> list[tuple[str, float]]:
        matrix = self._store.matrix
        if matrix.shape[0] == 0:
            return []
        if entity_types:
            rows = np.concatenate(
                [self._store.rows_of_type(entity_type) for entity_type in entity_types]
                or [np.asarray([], dtype=np.int32)]
            )
            if rows.size == 0:
                return []
        else:
            rows = np.arange(matrix.shape[0], dtype=np.int32)
        similarities = matrix[rows] @ query_vector.astype(np.float32)
        limit = min(top_k, similarities.shape[0])
        if limit <= 0:
            return []
        top = np.argpartition(-similarities, limit - 1)[:limit]
        ordered = top[np.argsort(-similarities[top], kind="stable")]
        return [
            (self._store.id_at(int(rows[position])), float(similarities[position]))
            for position in ordered
        ]

    def search_by_type(
        self,
        query_vector: np.ndarray,
        entity_types: Sequence[str],
        top_k_per_type: int = 30,
    ) -> dict[str, list[tuple[str, float]]]:
        return {
            entity_type: self.search(query_vector, top_k=top_k_per_type, entity_types=[entity_type])
            for entity_type in entity_types
        }

    def similarity(self, query_vector: np.ndarray, identifier: str) -> float | None:
        vector = self._store.vector(identifier)
        if vector is None:
            return None
        return float(np.dot(vector, query_vector.astype(np.float32)))
