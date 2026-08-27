"""Motor de consulta híbrida: orquesta recuperación, ranking, evidencia y oportunidades."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from . import CONTRACT_VERSION, __version__
from .data.corpus import SemanticCorpus
from .data.graph_port import EntityResolver, GraphNavigator, GraphPort, build_graph_port
from .embeddings.providers import EmbeddingProvider, build_provider, calibration_for
from .embeddings.store import EmbeddingStore
from .evidence.assembler import EvidenceAssembler, EvidencePackage, IdentifierGuard
from .llm.provider import GuardedNarrator, build_narrator
from .opportunities.generator import OpportunityGenerator
from .ranking.features import FeatureContext
from .ranking.scorer import ExplainableRanker, ScoredConnection
from .retrieval.hybrid import HybridRetriever
from .retrieval.lexical import BM25Index
from .retrieval.query import QueryContextBuilder
from .retrieval.vector import VectorSearcher
from .settings import EngineConfig, Settings, get_engine_config, get_settings
from .text import Lexicon

SCORE_DISCLAIMER = (
    "Los scores expresan relevancia para esta consulta. No son verdad científica, "
    "probabilidad de éxito ni aprobación institucional."
)
MAX_GRAPH_NODES = 20


@dataclass
class SearchRequest:
    query: str
    source_entity_id: str | None = None
    target_types: list[str] | None = None
    limit: int = 5
    include_opportunities: bool = True
    max_opportunities: int = 3
    include_graph: bool = True
    include_discarded: bool = True
    discarded_limit: int = 3


class KnowledgeNexusEngine:
    """Punto de entrada único del frente de recuperación."""

    def __init__(
        self,
        settings: Settings,
        config: EngineConfig,
        corpus: SemanticCorpus,
        graph: GraphPort,
        store: EmbeddingStore,
        provider: EmbeddingProvider,
    ):
        self._settings = settings
        self._config = config
        self._corpus = corpus
        self._graph = graph
        self._store = store
        self._provider = provider
        self._lexicon = Lexicon.from_config(config.lexicon)
        self._navigator = GraphNavigator(
            graph, max_depth=int(config.ranking.get("graph", {}).get("max_distance", 3))
        )
        self._resolver = EntityResolver(
            graph, {document.id: document.entity_type for document in corpus}
        )
        self._vector = VectorSearcher(store)
        self._lexical = BM25Index.from_corpus(corpus, self._lexicon.stopwords)
        self._builder = QueryContextBuilder(
            config, provider, graph, corpus, self._lexicon, self._resolver.known_ids
        )
        self._retriever = HybridRetriever(
            config, corpus, graph, self._navigator, self._vector, self._lexical
        )
        self._ranker = ExplainableRanker(config, self._lexicon)
        self._assembler = EvidenceAssembler(config, self._navigator, self._lexicon)
        self._opportunities = OpportunityGenerator(config, self._navigator)
        self._narrator = build_narrator(settings)
        self._reference_year = _reference_year(corpus, graph, self._resolver)
        calibration = calibration_for(
            store.model,
            {
                "cosine_floor": float(config.ranking.get("semantic", {}).get("cosine_floor", 0.25)),
                "cosine_ceiling": float(
                    config.ranking.get("semantic", {}).get("cosine_ceiling", 0.85)
                ),
            },
        )
        self._cosine_floor = float(calibration["cosine_floor"])
        self._cosine_ceiling = float(calibration["cosine_ceiling"])

    # Construcción --------------------------------------------------------
    @classmethod
    def build(cls, settings: Settings | None = None) -> "KnowledgeNexusEngine":
        active = settings or get_settings()
        config = get_engine_config() if settings is None else EngineConfig.load(active)
        corpus = SemanticCorpus.from_jsonl(active.semantic_documents_path)
        store = EmbeddingStore.load(active.embeddings_path)
        store.validate_coverage(corpus)
        provider = build_provider(active)
        store.validate_provider(provider.name, provider.dimension)
        graph = build_graph_port(active)
        return cls(active, config, corpus, graph, store, provider)

    def close(self) -> None:
        self._graph.close()

    # Endpoints -----------------------------------------------------------
    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "knowledge-nexus-retrieval",
            "version": __version__,
            "contract_version": CONTRACT_VERSION,
            "ranking_version": self._config.ranking_version,
            "graph_backend": self._settings.graph_backend,
            "embedding_model": self._store.model,
            "embedding_dimension": self._store.dimension,
            "documents_indexed": len(self._store),
            "semantic_documents": len(self._corpus),
            "lexical_documents": len(self._lexical),
            "lexicon_version": self._lexicon.version,
            "llm_provider": self._narrator.name,
            "reference_year": self._reference_year,
            "cosine_calibration": {
                "floor": self._cosine_floor,
                "ceiling": self._cosine_ceiling,
            },
            "score_disclaimer": SCORE_DISCLAIMER,
        }

    def search(self, request: SearchRequest) -> dict[str, Any]:
        started = time.perf_counter()
        context = self._builder.build(
            request.query, request.source_entity_id, request.target_types
        )
        retrieval = self._retriever.retrieve(context)
        features = FeatureContext.build(
            self._config,
            self._lexicon,
            self._navigator,
            self._resolver,
            context,
            self._reference_year,
            self._cosine_floor,
            self._cosine_ceiling,
        )
        ranked = self._ranker.rank(retrieval, features)
        selected = self._select(ranked, max(1, request.limit), context)
        for connection in selected:
            if not connection.explanation:
                connection.explanation = self._ranker.explain(connection, features)

        package = EvidencePackage(guard=IdentifierGuard(set()))
        if context.source_entity is not None:
            package.register_entity(context.source_entity)
        for connection in selected:
            package.register_entity(connection.candidate.entity)
        narrator = GuardedNarrator(self._narrator, package.guard)

        source_summary = self._query_entity(context)
        connections: list[dict[str, Any]] = []
        for connection in selected:
            evidence = self._assembler.assemble(connection)
            if not evidence:
                # Nunca se muestra una conexión sin evidencia verificable.
                continue
            package.evidence_by_connection[_connection_id(context, connection)] = evidence
            connections.append(
                self._connection_payload(
                    context,
                    connection,
                    evidence,
                    source_summary,
                    narrator,
                    position=len(connections) + 1,
                )
            )

        opportunities: list[dict[str, Any]] = []
        if request.include_opportunities and connections:
            for opportunity in self._opportunities.generate(
                context, selected, package, limit=request.max_opportunities
            ):
                opportunities.append(opportunity.as_dict())

        response: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "fixture_only": False,
            "warning": SCORE_DISCLAIMER,
            "query_entity": source_summary,
            "connections": connections,
            "opportunities": opportunities,
        }
        if request.include_discarded:
            response["discarded"] = self._discarded_payload(
                ranked, selected, request.discarded_limit
            )
        if request.include_graph:
            response["graph"] = self._graph_payload(context, selected[: len(connections)])
        response["query"] = context.describe()
        response["confidence"] = self._confidence(selected[: len(connections)])
        response["meta"] = {
            "ranking_version": self._config.ranking_version,
            "weights": self._ranker.weights,
            "embedding_model": self._store.model,
            "embedding_dimension": self._store.dimension,
            "graph_backend": self._settings.graph_backend,
            "llm_provider": narrator.name,
            "llm_rejections": narrator.rejections,
            "retrieval": retrieval.diagnostics,
            "results_returned": len(connections),
            "candidates_evaluated": len(ranked),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "empty_result": not connections,
        }
        if not connections:
            response["meta"]["reason"] = (
                "Ninguna entidad de los tipos solicitados alcanzó evidencia verificable "
                "para esta consulta."
            )
        return response

    def opportunities(self, request: SearchRequest) -> dict[str, Any]:
        payload = self.search(
            SearchRequest(
                query=request.query,
                source_entity_id=request.source_entity_id,
                target_types=request.target_types,
                limit=max(request.limit, 10),
                include_opportunities=True,
                max_opportunities=request.max_opportunities,
                include_graph=False,
            )
        )
        return {
            "contract_version": CONTRACT_VERSION,
            "fixture_only": False,
            "warning": SCORE_DISCLAIMER,
            "query_entity": payload["query_entity"],
            "opportunities": payload["opportunities"],
            "supporting_connections": [
                {
                    "connection_id": item["connection_id"],
                    "target": item["target"],
                    "relation": item["relation"],
                    "relevance_total": item["relevance"]["total"],
                }
                for item in payload["connections"]
            ],
            "meta": payload["meta"],
        }

    def entity(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        entity = self._graph.get_entity(entity_type, entity_id)
        if entity is None:
            return None
        neighbors = self._navigator.neighbors(entity_id)
        evidence = self._graph.get_evidence(entity_id) or {}
        document = self._corpus.get(entity_id)
        return {
            "contract_version": CONTRACT_VERSION,
            "entity": entity,
            "semantic_document": (
                {
                    "id": document.id,
                    "entity_type": document.entity_type,
                    "title": document.title,
                    "text": document.text,
                    "source": document.source,
                }
                if document
                else None
            ),
            "neighbors": [
                {
                    "relationship": item["relationship"],
                    "direction": item["direction"],
                    "relation_origin": item["relation_origin"],
                    "provenance": item["provenance"],
                    "target": {
                        "id": item["target"]["id"],
                        "type": item["target"]["entity_type"],
                        "title": item["target"]["title"],
                    },
                }
                for item in neighbors
            ],
            "evidence": {
                "source": evidence.get("source"),
                "documents": [
                    {"id": item["id"], "title": item["title"], "source": item["source"]}
                    for item in evidence.get("documents", [])
                ],
                "relation_evidence": evidence.get("relation_evidence", []),
                "relation_provenance": self._assembler.entity_evidence(entity_id)[:20],
            },
            "indexed": entity_id in self._store,
        }

    def _select(
        self, ranked: list[ScoredConnection], limit: int, context: Any
    ) -> list[ScoredConnection]:
        """Toma los mejores respetando una cuota por tipo cuando se piden varios.

        La diversificación no reordena por criterios ajenos al score: solo evita
        que un único tipo de entidad ocupe toda la respuesta cuando la consulta
        pidió varios. El primer puesto siempre es el de mayor relevancia.
        """

        if not ranked:
            return []
        # Umbral de calidad: por debajo de él una conexión no se muestra aunque
        # sea la mejor disponible. Permite responder "sin resultados" de forma
        # honesta en lugar de rellenar con coincidencias débiles.
        floor = float(self._config.ranking.get("retrieval", {}).get("min_total_score", 0.0))
        ranked = [item for item in ranked if item.total >= floor]
        if not ranked:
            return []
        selection = self._config.ranking.get("selection", {})
        types_requested = len(set(context.target_types))
        if not selection.get("diversify_by_type", True) or types_requested < 2:
            return ranked[:limit]
        quota = int(selection.get("max_per_type", 2))
        chosen: list[ScoredConnection] = []
        used: dict[str, int] = {}
        for connection in ranked:
            entity_type = connection.candidate.entity_type
            if used.get(entity_type, 0) >= quota:
                continue
            chosen.append(connection)
            used[entity_type] = used.get(entity_type, 0) + 1
            if len(chosen) >= limit:
                return chosen
        # Si la cuota dejó huecos, se completan con los siguientes por score.
        for connection in ranked:
            if len(chosen) >= limit:
                break
            if connection not in chosen:
                chosen.append(connection)
        return chosen

    def list_needs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Necesidades institucionales ordenadas por ID, para poblar el selector."""

        results: list[dict[str, Any]] = []
        for document in self._corpus:
            if document.entity_type != "InstitutionalNeed":
                continue
            entity = self._resolver.resolve(document.id)
            properties = (entity or {}).get("properties", {})
            results.append(
                {
                    "id": document.id,
                    "type": document.entity_type,
                    "title": document.title,
                    "priority": properties.get("priority"),
                    "status": properties.get("status"),
                    "year": properties.get("year"),
                }
            )
        results.sort(key=lambda item: str(item["id"]))
        return results[:limit]

    def _confidence(self, selected: list[ScoredConnection]) -> dict[str, Any]:
        """Declara cuánta confianza merece la respuesta.

        Entregar el mejor resultado disponible no es lo mismo que afirmar que
        responde a la pregunta. Cuando la señal semántica del primer resultado es
        baja, la respuesta se marca como poco fiable en lugar de presentarse como
        un hallazgo.
        """

        selection = self._config.ranking.get("selection", {})
        semantic_floor = float(selection.get("low_confidence_semantic_below", 0.45))
        total_floor = float(selection.get("low_confidence_total_below", 0.55))
        if not selected:
            return {
                "level": "sin_resultados",
                "label": "Sin resultados",
                "message": "Ninguna entidad alcanzó evidencia verificable para esta consulta.",
            }
        top = selected[0]
        semantic = top.components["semantic"].value
        if semantic < semantic_floor or top.total < total_floor:
            return {
                "level": "baja",
                "label": "Confianza baja",
                "message": (
                    "Ninguna entidad de Data V1.0 responde claramente a esta consulta. "
                    "Lo que se muestra son las coincidencias más cercanas que se "
                    "encontraron, no una respuesta: revisa el desglose antes de usarlas."
                ),
                "top_semantic": round(semantic, 4),
                "top_total": round(top.total, 4),
                "thresholds": {"semantic": semantic_floor, "total": total_floor},
            }
        level = "alta" if top.total >= 0.70 else "media"
        return {
            "level": level,
            "label": "Confianza alta" if level == "alta" else "Confianza media",
            "message": (
                "El primer resultado tiene respaldo semántico y evidencia verificable."
                if level == "alta"
                else "Hay coincidencias razonables; conviene revisar el desglose de cada una."
            ),
            "top_semantic": round(semantic, 4),
            "top_total": round(top.total, 4),
            "thresholds": {"semantic": semantic_floor, "total": total_floor},
        }

    def _discarded_payload(
        self,
        ranked: list[ScoredConnection],
        selected: list[ScoredConnection],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Candidatos que quedaron fuera, con el motivo concreto.

        Poder decir por qué una conexión **no** es relevante es tan importante
        como justificar las que sí aparecen: evita presentar el ranking como una
        caja negra.
        """

        if limit <= 0 or not ranked:
            return []
        floor = float(self._config.ranking.get("retrieval", {}).get("min_total_score", 0.0))
        quota = int(self._config.ranking.get("selection", {}).get("max_per_type", 2))
        chosen = {item.candidate.id for item in selected}
        cutoff = min((item.total for item in selected), default=0.0)
        shown_types: dict[str, int] = {}
        for item in selected:
            shown_types[item.candidate.entity_type] = (
                shown_types.get(item.candidate.entity_type, 0) + 1
            )

        def describe(connection: ScoredConnection, kind: str) -> dict[str, Any]:
            weakest = min(connection.weighted.items(), key=lambda item: item[1])
            reasons: list[str] = []
            if connection.total < floor:
                reasons.append(
                    f"Quedó por debajo del umbral mínimo de relevancia ({floor:.2f})."
                )
            if connection.penalties:
                reasons.append(
                    "Penalizada por: "
                    + "; ".join(item["reason"] for item in connection.penalties)
                )
            if shown_types.get(connection.candidate.entity_type, 0) >= quota:
                reasons.append(
                    f"Ya se mostraban {quota} entidades de tipo "
                    f"{connection.candidate.entity_type}; la cuota por tipo evita "
                    "que un solo tipo ocupe toda la respuesta."
                )
            if not reasons:
                reasons.append(
                    f"Quedó {cutoff - connection.total:.3f} por debajo del último "
                    f"resultado mostrado; su señal más débil es «{weakest[0]}» "
                    f"({connection.components[weakest[0]].value:.2f})."
                )
            return {
                "id": connection.candidate.id,
                "type": connection.candidate.entity_type,
                "title": connection.candidate.title,
                "total": round(connection.total, 4),
                "global_rank": connection.rank,
                "kind": kind,
                "weakest_signal": {
                    "name": weakest[0],
                    "value": round(connection.components[weakest[0]].value, 4),
                },
                "relevance": {
                    name: round(connection.components[name].value, 4)
                    for name in connection.components
                },
                "reason": " ".join(reasons),
            }

        results: list[dict[str, Any]] = []
        # Los que se quedaron a las puertas.
        near_limit = max(1, limit - 1) if limit > 1 else limit
        for connection in ranked:
            if len(results) >= near_limit:
                break
            if connection.candidate.id in chosen:
                continue
            results.append(describe(connection, "quedo_cerca"))
        # Y uno claramente descartado, para mostrar el otro extremo del ranking.
        if limit > 1 and len(ranked) > len(results) + len(chosen):
            worst = ranked[-1]
            if worst.candidate.id not in chosen:
                results.append(describe(worst, "descartado_claramente"))
        return results

    # Utilidades ----------------------------------------------------------
    def _query_entity(self, context: Any) -> dict[str, Any]:
        if context.source_entity is not None:
            return {
                "id": context.source_entity.get("id"),
                "type": context.source_entity.get("entity_type"),
                "title": context.source_entity.get("title"),
            }
        return {"id": None, "type": "FreeTextQuery", "title": context.raw_query[:180]}

    def _connection_payload(
        self,
        context: Any,
        connection: ScoredConnection,
        evidence: list[dict[str, Any]],
        source_summary: dict[str, Any],
        narrator: GuardedNarrator,
        position: int,
    ) -> dict[str, Any]:
        candidate = connection.candidate
        explanation = narrator.rewrite(
            connection.explanation,
            {
                "connection_id": _connection_id(context, connection),
                "target_id": candidate.id,
                "evidence": evidence,
            },
        )
        return {
            "connection_id": _connection_id(context, connection),
            "source": source_summary,
            "target": {
                "id": candidate.id,
                "type": candidate.entity_type,
                "title": candidate.title,
            },
            "relation": connection.relation,
            "relation_origin": connection.relation_origin,
            "relevance": connection.relevance_payload(
                self._ranker.weights, self._config.ranking_version
            ),
            "explanation": explanation,
            "evidence": evidence,
            "rank": position,
            "global_rank": connection.rank,
            "components_detail": connection.components_detail(),
            "retrieval": candidate.channel_summary(),
        }

    def _graph_payload(
        self, context: Any, connections: list[ScoredConnection]
    ) -> dict[str, Any]:
        """Subgrafo compacto para la interfaz.

        Incluye las aristas inferidas del ranking y, además, las relaciones
        explícitas reales que ya existen entre las entidades mostradas. Así la
        interfaz puede dibujar unas discontinuas y otras continuas sin tener que
        consultar el grafo por su cuenta.
        """

        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        def add_node(entity: dict[str, Any]) -> bool:
            identifier = str(entity.get("id") or "")
            if not identifier or len(nodes) >= MAX_GRAPH_NODES:
                return identifier in nodes
            if identifier not in nodes:
                nodes[identifier] = {
                    "id": identifier,
                    "label": entity.get("entity_type"),
                    "title": entity.get("title"),
                    "source_file": (entity.get("source") or {}).get("file"),
                    "source_row": (entity.get("source") or {}).get("row"),
                }
            return True

        def add_edge(edge: dict[str, Any]) -> None:
            key = (str(edge["source_id"]), str(edge["relationship"]), str(edge["target_id"]))
            if key in seen:
                return
            seen.add(key)
            edges.append(edge)

        source_id = context.source_id
        if context.source_entity is not None:
            add_node(context.source_entity)
        for connection in connections:
            add_node(connection.candidate.entity)
        # Entidades puente que aparecieron en los caminos de expansión.
        for connection in connections:
            for step in connection.candidate.graph_path:
                for identifier in (str(step["from_id"]), str(step["to_id"])):
                    if identifier in nodes:
                        continue
                    entity = self._resolver.resolve(identifier)
                    if entity is not None:
                        add_node(entity)

        # Aristas inferidas: el resultado del ranking.
        for connection in connections:
            if not source_id:
                continue
            add_edge(
                {
                    "source_id": source_id,
                    "source_label": context.source_type,
                    "relationship": connection.relation,
                    "target_id": connection.candidate.id,
                    "target_label": connection.candidate.entity_type,
                    "properties": {"score_total": round(connection.total, 4)},
                    "provenance": [],
                    "relation_origin": connection.relation_origin,
                }
            )

        # Aristas explícitas reales entre las entidades mostradas.
        for identifier in list(nodes):
            for neighbor in self._navigator.neighbors(identifier):
                target_id = str(neighbor["target"]["id"])
                if target_id not in nodes:
                    continue
                if neighbor["direction"] == "OUTGOING":
                    origin, destination = identifier, target_id
                else:
                    origin, destination = target_id, identifier
                add_edge(
                    {
                        "source_id": origin,
                        "source_label": nodes[origin]["label"],
                        "relationship": neighbor["relationship"],
                        "target_id": destination,
                        "target_label": nodes[destination]["label"],
                        "properties": dict(neighbor["properties"]),
                        "provenance": neighbor["provenance"],
                        "relation_origin": neighbor["relation_origin"] or "EXPLICIT",
                    }
                )
        return {
            "description": (
                "Subgrafo de la respuesta. Las aristas INFERRED provienen del ranking; "
                "las EXPLICIT provienen de Data V1.0."
            ),
            "nodes": list(nodes.values()),
            "edges": edges,
        }


def _connection_id(context: Any, connection: ScoredConnection) -> str:
    base = context.source_id or "QUERY"
    return f"CONN-{base}-{connection.candidate.id}"


def _reference_year(
    corpus: SemanticCorpus, graph: GraphPort, resolver: EntityResolver
) -> int:
    """Año más reciente presente en los datos; hace reproducible la vigencia."""

    year_fields = ("year", "end_year", "graduation_year", "start_year", "creation_year")
    maximum = 0
    for document in corpus:
        entity = resolver.resolve(document.id)
        if entity is None:
            continue
        properties = entity.get("properties") or {}
        for field_name in year_fields:
            try:
                value = int(properties.get(field_name))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if 1900 < value < 2200:
                maximum = max(maximum, value)
    return maximum or 2026


def load_dataset_manifest(settings: Settings) -> dict[str, Any]:
    path = settings.dataset_manifest_path
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
