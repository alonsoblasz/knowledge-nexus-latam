"""Recuperación híbrida: candidatos vectoriales, léxicos y por expansión."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..data.corpus import SemanticCorpus, SemanticDocument
from ..data.graph_port import GraphNavigator, GraphPort
from ..settings import EngineConfig
from .lexical import BM25Index
from .query import QueryContext
from .vector import VectorSearcher

VECTOR_CHANNEL = "vector"
LEXICAL_CHANNEL = "lexical"
GRAPH_CHANNEL = "graph"


@dataclass
class Candidate:
    """Entidad recuperada con la traza de cómo llegó al conjunto de candidatos."""

    id: str
    entity_type: str
    entity: dict[str, Any]
    document: SemanticDocument | None = None
    vector_score: float = 0.0
    lexical_score: float = 0.0
    lexical_normalized: float = 0.0
    matched_terms: list[str] = field(default_factory=list)
    channels: set[str] = field(default_factory=set)
    graph_hops: int | None = None
    graph_path: list[dict[str, Any]] = field(default_factory=list)
    graph_seed: str | None = None

    @property
    def title(self) -> str:
        return str(self.entity.get("title") or (self.document.title if self.document else self.id))

    @property
    def properties(self) -> dict[str, Any]:
        return dict(self.entity.get("properties") or {})

    @property
    def graph_only(self) -> bool:
        return self.channels == {GRAPH_CHANNEL}

    def channel_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "channels": sorted(self.channels),
            "vector_similarity": round(self.vector_score, 4),
            "lexical_bm25": round(self.lexical_score, 4),
            "lexical_normalized": round(self.lexical_normalized, 4),
            "matched_terms": self.matched_terms[:8],
        }
        if self.graph_hops is not None:
            summary["graph_expansion"] = {
                "hops": self.graph_hops,
                "seed_id": self.graph_seed,
                "path": [
                    {
                        "relationship": step["relationship"],
                        "from_id": step["from_id"],
                        "to_id": step["to_id"],
                        "relation_origin": step["relation_origin"],
                    }
                    for step in self.graph_path
                ],
            }
        return summary


@dataclass
class RetrievalResult:
    """Candidatos deduplicados junto con el diagnóstico de la recuperación."""

    context: QueryContext
    candidates: list[Candidate]
    diagnostics: dict[str, Any] = field(default_factory=dict)


class HybridRetriever:
    """Genera candidatos combinando los tres canales y deduplicando por ID."""

    def __init__(
        self,
        config: EngineConfig,
        corpus: SemanticCorpus,
        graph: GraphPort,
        navigator: GraphNavigator,
        vector_searcher: VectorSearcher,
        lexical_index: BM25Index,
    ):
        self._config = config
        self._corpus = corpus
        self._graph = graph
        self._navigator = navigator
        self._vector = vector_searcher
        self._lexical = lexical_index

    @property
    def _retrieval_config(self) -> dict[str, Any]:
        return self._config.ranking.get("retrieval", {})

    def retrieve(self, context: QueryContext) -> RetrievalResult:
        started = time.perf_counter()
        settings = self._retrieval_config
        types = list(context.target_types)
        candidates: dict[str, Candidate] = {}

        # 1. Canal vectorial, top-k por tipo.
        vector_hits = self._vector.search_by_type(
            context.vector, types, int(settings.get("vector_top_k_per_type", 30))
        )
        for entity_type, hits in vector_hits.items():
            for identifier, score in hits:
                candidate = self._ensure_candidate(candidates, identifier, entity_type)
                if candidate is None:
                    continue
                candidate.vector_score = max(candidate.vector_score, float(score))
                candidate.channels.add(VECTOR_CHANNEL)

        # 2. Canal léxico como línea base determinista.
        lexical_hits = self._lexical.search_by_type(
            list(context.expanded_terms), types, int(settings.get("lexical_top_k_per_type", 30))
        )
        for entity_type, hits in lexical_hits.items():
            for identifier, score in hits:
                candidate = self._ensure_candidate(candidates, identifier, entity_type)
                if candidate is None:
                    continue
                candidate.lexical_score = max(candidate.lexical_score, float(score))
                candidate.channels.add(LEXICAL_CHANNEL)

        seeds_before_expansion = len(candidates)

        # 3. Expansión por relaciones explícitas desde las mejores semillas y
        #    desde la propia entidad de origen.
        seed_ids = self._select_seeds(candidates, int(settings.get("expansion_seeds", 12)))
        if context.source_id:
            seed_ids = [context.source_id, *seed_ids]
        expanded = self._navigator.expand(
            seed_ids,
            max_hops=int(settings.get("expansion_max_hops", 2)),
            allowed_types=frozenset(types),
        )
        for identifier, payload in expanded.items():
            if context.source_id and identifier == context.source_id:
                continue
            entity = payload["entity"]
            candidate = candidates.get(identifier)
            if candidate is None:
                candidate = Candidate(
                    id=identifier,
                    entity_type=str(entity.get("entity_type")),
                    entity=entity,
                    document=self._corpus.get(identifier),
                )
                candidates[identifier] = candidate
            candidate.channels.add(GRAPH_CHANNEL)
            if candidate.graph_hops is None or payload["hops"] < candidate.graph_hops:
                candidate.graph_hops = int(payload["hops"])
                candidate.graph_path = list(payload["path"])
                candidate.graph_seed = str(payload["seed_id"])

        # 4. Señales completas para todo candidato, venga del canal que venga.
        self._complete_signals(candidates, context)

        ordered = sorted(
            candidates.values(),
            key=lambda item: (
                -(0.7 * item.vector_score + 0.3 * item.lexical_normalized),
                item.id,
            ),
        )
        capped = ordered[: int(settings.get("candidate_cap", 400))]
        diagnostics = {
            "candidates_total": len(candidates),
            "candidates_returned": len(capped),
            "candidates_before_expansion": seeds_before_expansion,
            "expansion_seeds": seed_ids[:12],
            "by_channel": {
                VECTOR_CHANNEL: sum(1 for item in capped if VECTOR_CHANNEL in item.channels),
                LEXICAL_CHANNEL: sum(1 for item in capped if LEXICAL_CHANNEL in item.channels),
                GRAPH_CHANNEL: sum(1 for item in capped if GRAPH_CHANNEL in item.channels),
            },
            "retrieval_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        return RetrievalResult(context=context, candidates=capped, diagnostics=diagnostics)

    # Utilidades internas ------------------------------------------------
    def _ensure_candidate(
        self, candidates: dict[str, Candidate], identifier: str, entity_type: str
    ) -> Candidate | None:
        existing = candidates.get(identifier)
        if existing is not None:
            return existing
        entity = self._graph.get_entity(entity_type, identifier)
        if entity is None:
            # Un documento semántico sin nodo en el grafo se ignora y se reporta
            # a la persona 1: el motor no inventa entidades.
            return None
        candidate = Candidate(
            id=identifier,
            entity_type=entity_type,
            entity=entity,
            document=self._corpus.get(identifier),
        )
        candidates[identifier] = candidate
        return candidate

    def _select_seeds(self, candidates: dict[str, Candidate], limit: int) -> list[str]:
        maximum = max((item.lexical_score for item in candidates.values()), default=0.0)
        scored = sorted(
            candidates.values(),
            key=lambda item: (
                -(
                    0.7 * item.vector_score
                    + 0.3 * (item.lexical_score / maximum if maximum > 0 else 0.0)
                ),
                item.id,
            ),
        )
        return [item.id for item in scored[:limit]]

    def _complete_signals(self, candidates: dict[str, Candidate], context: QueryContext) -> None:
        terms = list(context.expanded_terms)
        for candidate in candidates.values():
            if VECTOR_CHANNEL not in candidate.channels:
                similarity = self._vector.similarity(context.vector, candidate.id)
                if similarity is not None:
                    candidate.vector_score = float(similarity)
            if LEXICAL_CHANNEL not in candidate.channels:
                position = self._lexical.document_terms(candidate.id)
                if position:
                    candidate.lexical_score = max(
                        candidate.lexical_score,
                        self._lexical.score(
                            self._lexical._index[candidate.id],  # noqa: SLF001
                            terms,
                        ),
                    )
            candidate.matched_terms = self._lexical.matched_terms(candidate.id, terms)
        maximum = max((item.lexical_score for item in candidates.values()), default=0.0)
        for candidate in candidates.values():
            candidate.lexical_normalized = (
                candidate.lexical_score / maximum if maximum > 0 else 0.0
            )


def build_candidate_index(candidates: Sequence[Candidate]) -> dict[str, Candidate]:
    return {candidate.id: candidate for candidate in candidates}
