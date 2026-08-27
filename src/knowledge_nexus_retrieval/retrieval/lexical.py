"""Canal léxico: línea base BM25 sobre los documentos semánticos.

Es el equivalente local del índice `semantic_text_fulltext` de Neo4j. Se calcula
en el motor para que el comportamiento sea idéntico con JSONL y con Aura, y para
poder explicar exactamente qué términos coincidieron.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence

from ..data.corpus import SemanticCorpus
from ..text import ngrams, tokenize

K1 = 1.2
B = 0.75


class BM25Index:
    """Índice BM25 con unigramas y bigramas, filtrable por tipo de entidad."""

    def __init__(
        self,
        documents: Sequence[tuple[str, str, str]],
        stopwords: frozenset[str] = frozenset(),
    ):
        self._ids: list[str] = []
        self._types: list[str] = []
        self._frequencies: list[Counter[str]] = []
        self._lengths: list[int] = []
        self._postings: dict[str, list[int]] = {}
        for identifier, entity_type, text in documents:
            tokens = tokenize(text, stopwords)
            terms = [*tokens, *ngrams(tokens, 2)]
            counter = Counter(terms)
            position = len(self._ids)
            self._ids.append(identifier)
            self._types.append(entity_type)
            self._frequencies.append(counter)
            self._lengths.append(max(1, len(tokens)))
            for term in counter:
                self._postings.setdefault(term, []).append(position)
        self._index = {identifier: position for position, identifier in enumerate(self._ids)}
        total = len(self._ids)
        self._average_length = (sum(self._lengths) / total) if total else 1.0
        self._idf = {
            term: math.log(1.0 + (total - len(positions) + 0.5) / (len(positions) + 0.5))
            for term, positions in self._postings.items()
        }
        self._rows_by_type: dict[str, set[int]] = {}
        for position, entity_type in enumerate(self._types):
            self._rows_by_type.setdefault(entity_type, set()).add(position)

    @classmethod
    def from_corpus(
        cls, corpus: SemanticCorpus, stopwords: frozenset[str] = frozenset()
    ) -> "BM25Index":
        return cls(
            [(document.id, document.entity_type, document.text) for document in corpus],
            stopwords=stopwords,
        )

    def __len__(self) -> int:
        return len(self._ids)

    def score(self, position: int, query_terms: Iterable[str]) -> float:
        counter = self._frequencies[position]
        length = self._lengths[position]
        total = 0.0
        for term in query_terms:
            frequency = counter.get(term, 0)
            if not frequency:
                continue
            idf = self._idf.get(term, 0.0)
            denominator = frequency + K1 * (1 - B + B * length / self._average_length)
            total += idf * (frequency * (K1 + 1)) / denominator
        return total

    def search(
        self,
        query_terms: Sequence[str],
        top_k: int = 30,
        entity_types: Sequence[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Mejores documentos por tipo; devuelve `(id, score)` ordenado."""

        unique_terms = list(dict.fromkeys(query_terms))
        if not unique_terms:
            return []
        candidate_positions: set[int] = set()
        for term in unique_terms:
            candidate_positions.update(self._postings.get(term, ()))
        if entity_types:
            allowed: set[int] = set()
            for entity_type in entity_types:
                allowed |= self._rows_by_type.get(entity_type, set())
            candidate_positions &= allowed
        scored = [
            (self._ids[position], self.score(position, unique_terms))
            for position in candidate_positions
        ]
        scored = [item for item in scored if item[1] > 0.0]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:top_k]

    def search_by_type(
        self,
        query_terms: Sequence[str],
        entity_types: Sequence[str],
        top_k_per_type: int = 30,
    ) -> dict[str, list[tuple[str, float]]]:
        return {
            entity_type: self.search(query_terms, top_k=top_k_per_type, entity_types=[entity_type])
            for entity_type in entity_types
        }

    def matched_terms(self, identifier: str, query_terms: Iterable[str]) -> list[str]:
        """Términos de la consulta presentes en un documento, para explicar."""

        position = self._index.get(identifier)
        if position is None:
            return []
        counter = self._frequencies[position]
        matched = [term for term in dict.fromkeys(query_terms) if counter.get(term)]
        # Se prioriza el término más específico (bigrama) sobre el genérico.
        matched.sort(key=lambda term: (-self._idf.get(term, 0.0), term))
        return matched

    def document_terms(self, identifier: str) -> Counter[str]:
        position = self._index.get(identifier)
        if position is None:
            return Counter()
        return self._frequencies[position]
