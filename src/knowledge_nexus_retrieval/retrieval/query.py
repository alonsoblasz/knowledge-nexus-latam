"""Construcción del contexto de consulta que alimenta recuperación y ranking."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..data.corpus import SemanticCorpus, SemanticDocument
from ..data.graph_port import GraphPort
from ..embeddings.providers import EmbeddingProvider
from ..settings import EngineConfig
from ..text import Lexicon, extract_canonical_ids, ngrams, token_counter, tokenize


@dataclass(frozen=True)
class QueryContext:
    """Todo lo que el motor sabe de una consulta antes de puntuar candidatos."""

    raw_query: str
    target_types: tuple[str, ...]
    vector: np.ndarray
    base_terms: tuple[str, ...]
    expanded_terms: tuple[str, ...]
    domain_terms: Counter[str]
    method_terms: frozenset[str]
    anchors: frozenset[str]
    source_entity: dict[str, Any] | None = None
    source_document: SemanticDocument | None = None
    lexicon_expansion: bool = True
    notes: list[str] = field(default_factory=list)

    @property
    def source_id(self) -> str | None:
        if not self.source_entity:
            return None
        return str(self.source_entity.get("id"))

    @property
    def source_type(self) -> str | None:
        if not self.source_entity:
            return None
        return str(self.source_entity.get("entity_type"))

    @property
    def has_method_signal(self) -> bool:
        return bool(self.method_terms)

    def describe(self) -> dict[str, Any]:
        return {
            "query": self.raw_query,
            "source_entity_id": self.source_id,
            "target_types": list(self.target_types),
            "terms": list(self.base_terms)[:20],
            "expanded_terms_added": len(set(self.expanded_terms) - set(self.base_terms)),
            "method_terms": sorted(self.method_terms),
            "anchors": sorted(self.anchors),
            "lexicon_expansion": self.lexicon_expansion,
            "notes": list(self.notes),
        }


class QueryContextBuilder:
    """Combina texto libre y entidad de origen en una sola representación."""

    def __init__(
        self,
        config: EngineConfig,
        provider: EmbeddingProvider,
        graph: GraphPort,
        corpus: SemanticCorpus,
        lexicon: Lexicon,
        known_ids: frozenset[str],
    ):
        self._config = config
        self._provider = provider
        self._graph = graph
        self._corpus = corpus
        self._lexicon = lexicon
        self._known_ids = known_ids

    def build(
        self,
        query: str,
        source_entity_id: str | None = None,
        target_types: Sequence[str] | None = None,
    ) -> QueryContext:
        notes: list[str] = []
        retrieval_config = self._config.ranking.get("retrieval", {})
        types = tuple(target_types or retrieval_config.get("default_target_types", []))
        if not types:
            raise ValueError("Debe indicarse al menos un tipo de entidad objetivo")

        source_entity: dict[str, Any] | None = None
        source_document: SemanticDocument | None = None
        if source_entity_id:
            source_entity = self._load_source(source_entity_id)
            if source_entity is None:
                raise LookupError(
                    f"La entidad de origen {source_entity_id} no existe en Data V1.0"
                )
            source_document = self._corpus.get(source_entity_id)

        query_text = (query or "").strip()
        if not query_text and source_document is not None:
            query_text = source_document.text
            notes.append(
                "La consulta usa el texto de la entidad de origen porque no se envió texto libre."
            )
        if not query_text:
            raise ValueError("La consulta necesita texto o una entidad de origen con texto")

        stopwords = self._lexicon.stopwords
        query_tokens = tokenize(query, stopwords) if query else []
        base_terms = [*query_tokens, *ngrams(query_tokens, 2)]
        source_terms: list[str] = []
        if source_document is not None:
            source_tokens = tokenize(source_document.title, stopwords)
            source_terms = [*source_tokens, *ngrams(source_tokens, 2)]
        if source_entity is not None:
            profile = self._config.profile(source_entity.get("entity_type"))
            for field_name in profile.get("domain_fields", []) or []:
                value = source_entity.get("properties", {}).get(field_name)
                tokens = tokenize(value, stopwords)
                source_terms.extend([*tokens, *ngrams(tokens, 2)])
        combined_terms = list(dict.fromkeys([*base_terms, *source_terms]))

        use_lexicon = bool(retrieval_config.get("use_lexicon_expansion", True))
        if use_lexicon:
            expanded = self._lexicon.expand_terms(combined_terms)
            expanded_terms = list(dict.fromkeys([*combined_terms, *sorted(expanded)]))
        else:
            expanded_terms = combined_terms
            notes.append("Expansión léxica desactivada por configuración.")

        domain_terms = token_counter([query, query], stopwords)
        if source_entity is not None:
            profile = self._config.profile(source_entity.get("entity_type"))
            values = [
                source_entity.get("properties", {}).get(field_name)
                for field_name in (profile.get("domain_fields", []) or [])
            ]
            domain_terms.update(token_counter(values, stopwords))

        method_terms = set(self._lexicon.method_signals(query))
        if source_entity is not None:
            profile = self._config.profile(source_entity.get("entity_type"))
            for field_name in profile.get("method_fields", []) or []:
                method_terms |= self._lexicon.method_signals(
                    source_entity.get("properties", {}).get(field_name)
                )

        anchors: set[str] = set()
        if source_entity is not None:
            properties = source_entity.get("properties", {})
            for field_name in self._config.anchor_fields:
                anchors |= extract_canonical_ids(properties.get(field_name), self._known_ids)
            anchors.discard(str(source_entity.get("id")))

        vector = self._build_vector(query, source_document, source_entity)
        return QueryContext(
            raw_query=query_text,
            target_types=types,
            vector=vector,
            base_terms=tuple(combined_terms),
            expanded_terms=tuple(expanded_terms),
            domain_terms=domain_terms,
            method_terms=frozenset(method_terms),
            anchors=frozenset(anchors),
            source_entity=source_entity,
            source_document=source_document,
            lexicon_expansion=use_lexicon,
            notes=notes,
        )

    def _load_source(self, source_entity_id: str) -> dict[str, Any] | None:
        document = self._corpus.get(source_entity_id)
        if document is not None:
            entity = self._graph.get_entity(document.entity_type, source_entity_id)
            if entity is not None:
                return entity
        for entity_type in self._corpus.entity_types:
            entity = self._graph.get_entity(entity_type, source_entity_id)
            if entity is not None:
                return entity
        return None

    def _build_vector(
        self,
        query: str,
        source_document: SemanticDocument | None,
        source_entity: dict[str, Any] | None,
    ) -> np.ndarray:
        """Mezcla el vector del texto libre con el de la entidad de origen.

        Ambos se codifican como consulta para no mezclar convenciones de
        codificación entre documentos y preguntas.
        """

        weight = float(self._config.ranking.get("semantic", {}).get("query_text_weight", 0.65))
        query_text = (query or "").strip()
        source_text = ""
        if source_document is not None:
            source_text = source_document.text
        elif source_entity is not None:
            source_text = str(source_entity.get("semantic_text") or "")

        if query_text and source_text:
            query_vector = self._provider.encode_query(query_text)
            source_vector = self._provider.encode_query(source_text)
            mixed = weight * query_vector + (1.0 - weight) * source_vector
        elif query_text:
            mixed = self._provider.encode_query(query_text)
        else:
            mixed = self._provider.encode_query(source_text)
        norm = float(np.linalg.norm(mixed))
        if norm > 0.0:
            mixed = mixed / norm
        return mixed.astype(np.float32)
