"""Ranking explicable: combinación ponderada, penalizaciones y desglose.

El total expresa **relevancia para la consulta**. No es una probabilidad, ni una
medida de calidad científica, ni una validación institucional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..retrieval.hybrid import GRAPH_CHANNEL, Candidate, RetrievalResult
from ..text import Lexicon, clamp01
from .features import COMPONENT_FUNCTIONS, ComponentScore, FeatureContext, duplicate_similarity

COMPONENT_ORDER = ("semantic", "domain", "method", "graph", "evidence", "actionable")


@dataclass
class ScoredConnection:
    """Un candidato puntuado con todo lo necesario para explicarlo."""

    candidate: Candidate
    components: dict[str, ComponentScore]
    weighted: dict[str, float]
    penalties: list[dict[str, Any]] = field(default_factory=list)
    base_total: float = 0.0
    total: float = 0.0
    relation: str = "SEMANTICALLY_RELATED"
    relation_origin: str = "INFERRED"
    explanation: str = ""
    rank: int = 0

    @property
    def penalty_total(self) -> float:
        return round(sum(item["value"] for item in self.penalties), 4)

    def relevance_payload(self, weights: dict[str, float], ranking_version: str) -> dict[str, Any]:
        """Desglose que consume la interfaz; conserva las claves del contrato."""

        payload: dict[str, Any] = {"total": round(self.total, 4)}
        for name in COMPONENT_ORDER:
            payload[name] = round(self.components[name].value, 4)
        payload["weights"] = dict(weights)
        payload["weighted_contributions"] = {
            name: round(value, 4) for name, value in self.weighted.items()
        }
        payload["base_total"] = round(self.base_total, 4)
        payload["penalties"] = [
            {"name": item["name"], "value": round(item["value"], 4), "reason": item["reason"]}
            for item in self.penalties
        ]
        payload["penalty_total"] = self.penalty_total
        payload["ranking_version"] = ranking_version
        payload["interpretation"] = (
            "Relevancia para esta consulta; no expresa verdad ni aprobación institucional."
        )
        return payload

    def components_detail(self) -> dict[str, Any]:
        return {name: self.components[name].detail for name in COMPONENT_ORDER}


class ExplainableRanker:
    """Aplica la fórmula versionada y explica por qué A aparece antes que B."""

    def __init__(self, config: Any, lexicon: Lexicon):
        self._config = config
        self._lexicon = lexicon

    @property
    def weights(self) -> dict[str, float]:
        raw = self._config.ranking.get("weights", {})
        return {name: float(raw.get(name, 0.0)) for name in COMPONENT_ORDER}

    @property
    def ranking_version(self) -> str:
        return self._config.ranking_version

    def rank(
        self, retrieval: RetrievalResult, features: FeatureContext, limit: int | None = None
    ) -> list[ScoredConnection]:
        weights = self.weights
        scored: list[ScoredConnection] = []
        for candidate in retrieval.candidates:
            components = {
                name: function(candidate, features)
                for name, function in COMPONENT_FUNCTIONS.items()
            }
            weighted = {
                name: weights[name] * components[name].value for name in COMPONENT_ORDER
            }
            base_total = sum(weighted.values())
            penalties = self._penalties(candidate, components, features)
            connection = ScoredConnection(
                candidate=candidate,
                components=components,
                weighted=weighted,
                penalties=penalties,
                base_total=base_total,
                total=clamp01(base_total - sum(item["value"] for item in penalties)),
            )
            connection.relation = self._infer_relation(candidate, components)
            scored.append(connection)

        scored.sort(key=lambda item: (-item.total, item.candidate.id))
        scored = self._apply_redundancy(scored)
        scored.sort(key=lambda item: (-item.total, item.candidate.id))
        explain_top_k = int(
            self._config.ranking.get("selection", {}).get("explain_top_k", 25)
        )
        for position, connection in enumerate(scored, start=1):
            connection.rank = position
            if position <= max(explain_top_k, limit or 0):
                connection.explanation = self.explain(connection, features)
        return scored[:limit] if limit else scored

    # Penalizaciones ------------------------------------------------------
    def _penalties(
        self,
        candidate: Candidate,
        components: dict[str, ComponentScore],
        features: FeatureContext,
    ) -> list[dict[str, Any]]:
        config = self._config.ranking.get("penalties", {})
        thresholds = self._config.ranking.get("thresholds", {})
        penalties: list[dict[str, Any]] = []
        properties = candidate.properties

        status = str(properties.get("status") or "").strip().upper()
        active = properties.get("active")
        if status in {"INACTIVE", "CLOSED", "DEPRECATED", "SUSPENDED"} or active is False:
            penalties.append(
                {
                    "name": "inactive_entity",
                    "value": float(config.get("inactive_entity", 0.15)),
                    "reason": f"La entidad está marcada como {status or 'inactiva'}.",
                }
            )

        evidence_value = components["evidence"].value
        if evidence_value < float(thresholds.get("missing_evidence_below", 0.30)):
            penalties.append(
                {
                    "name": "missing_evidence",
                    "value": float(config.get("missing_evidence", 0.10)),
                    "reason": f"Cobertura de evidencia baja ({evidence_value:.2f}).",
                }
            )

        semantic_value = components["semantic"].value
        graph_value = components["graph"].detail.get("subsignals", {}).get("proximity") or 0.0
        if (
            semantic_value < float(thresholds.get("superficial_semantic_below", 0.35))
            and len(candidate.matched_terms) <= 1
            and not graph_value
        ):
            penalties.append(
                {
                    "name": "superficial_match",
                    "value": float(config.get("superficial_match", 0.08)),
                    "reason": "Coincidencia débil y sin soporte estructural en el grafo.",
                }
            )

        if (
            components["domain"].value == 0.0
            and semantic_value < float(thresholds.get("domain_mismatch_semantic_below", 0.55))
            and features.query_area_terms
        ):
            penalties.append(
                {
                    "name": "domain_mismatch",
                    "value": float(config.get("domain_mismatch", 0.10)),
                    "reason": "No comparte unidad, área ni vocabulario con el dominio consultado.",
                }
            )

        maximum = float(config.get("max_total", 0.35))
        total = sum(item["value"] for item in penalties)
        if total > maximum and penalties:
            factor = maximum / total
            for item in penalties:
                item["value"] = round(item["value"] * factor, 4)
                item["reason"] += " (penalización recortada por el tope configurado)"
        return penalties

    def _apply_redundancy(self, scored: list[ScoredConnection]) -> list[ScoredConnection]:
        """Penaliza duplicados casi idénticos ya representados por otro resultado."""

        config = self._config.ranking.get("penalties", {})
        thresholds = self._config.ranking.get("thresholds", {})
        threshold = float(thresholds.get("redundancy_similarity_above", 0.92))
        value = float(config.get("redundancy", 0.06))
        window = int(
            self._config.ranking.get("selection", {}).get("redundancy_window", 50)
        )
        cache: dict[str, Any] = {}
        kept: list[ScoredConnection] = []
        for connection in scored[:window]:
            duplicate_of: str | None = None
            for previous in kept:
                if previous.candidate.entity_type != connection.candidate.entity_type:
                    continue
                similarity = duplicate_similarity(
                    previous.candidate, connection.candidate, self._lexicon, cache
                )
                if similarity >= threshold:
                    duplicate_of = previous.candidate.id
                    break
            if duplicate_of is not None:
                connection.penalties.append(
                    {
                        "name": "redundancy",
                        "value": value,
                        "reason": f"Contenido casi idéntico a {duplicate_of}, ya presente en el ranking.",
                    }
                )
                connection.total = clamp01(
                    connection.base_total - sum(item["value"] for item in connection.penalties)
                )
            kept.append(connection)
        return scored

    # Relación inferida ---------------------------------------------------
    def _infer_relation(
        self, candidate: Candidate, components: dict[str, ComponentScore]
    ) -> str:
        rules = self._config.relation_rules
        overrides = rules.get("overrides", {})
        relation = str(
            rules.get("relation_by_type", {}).get(candidate.entity_type, "SEMANTICALLY_RELATED")
        )
        if relation == "RELEVANT_ANTECEDENT" and overrides.get(
            "antecedent_requires_completed_status", True
        ):
            completed = {
                str(value).upper() for value in overrides.get("completed_statuses", []) or []
            }
            always = set(overrides.get("types_always_completed", []) or [])
            status = str(candidate.properties.get("status") or "").strip().upper()
            if candidate.entity_type not in always and status not in completed:
                relation = str(overrides.get("antecedent_fallback", "SEMANTICALLY_RELATED"))

        method_value = components["method"].value
        domain_value = components["domain"].value
        margin = float(overrides.get("method_dominance_margin", 0.25))
        # Solo se etiqueta compatibilidad metodológica si hubo comparación real
        # contra la metodología pedida; el modo de respaldo no la justifica.
        compared = components["method"].detail.get("mode") == "comparada_con_la_consulta"
        if compared and method_value >= float(overrides.get("method_min_score", 0.60)) and (
            method_value - domain_value
        ) >= margin:
            relation = str(overrides.get("method_relation", "METHODOLOGICALLY_COMPATIBLE"))

        if candidate.channels == {GRAPH_CHANNEL}:
            relation = str(overrides.get("graph_only_relation", "COMPLEMENTS"))
        return relation

    # Explicación ---------------------------------------------------------
    def explain(self, connection: ScoredConnection, features: FeatureContext) -> str:
        """Explicación determinista construida solo con hechos del paquete."""

        candidate = connection.candidate
        parts: list[str] = []
        ordered = sorted(connection.weighted.items(), key=lambda item: -item[1])
        semantic = connection.components["semantic"].detail
        matched = semantic.get("matched_terms") or []
        if matched:
            terms = ", ".join(f"«{term}»" for term in matched[:3])
            parts.append(
                f"coincide con la consulta en {terms} "
                f"(similitud vectorial {semantic.get('vector_similarity')})"
            )
        else:
            parts.append(
                "se aproxima a la consulta por similitud vectorial "
                f"{semantic.get('vector_similarity')} sin coincidencia literal de términos"
            )

        domain = connection.components["domain"].detail
        shared_units = domain.get("shared_units") or []
        if shared_units:
            parts.append(f"comparte la unidad institucional {', '.join(shared_units)}")
        elif domain.get("shared_terms"):
            parts.append(
                "comparte vocabulario de dominio "
                f"({', '.join(str(term) for term in domain['shared_terms'][:3])})"
            )

        method = connection.components["method"].detail
        shared_methods = method.get("shared_method_terms") or method.get("candidate_method_terms")
        if shared_methods:
            readable = [self._lexicon.display(str(term)) for term in shared_methods[:2]]
            parts.append(f"declara metodología de {', '.join(readable)}")

        graph = connection.components["graph"].detail
        distance = graph.get("explicit_distance_from_source")
        if distance:
            parts.append(f"está a {distance} salto(s) explícitos de la entidad consultada")
        elif graph.get("expansion_hops") and candidate.graph_only:
            parts.append(
                f"se alcanzó por expansión del grafo desde {candidate.graph_seed} "
                f"en {graph['expansion_hops']} salto(s)"
            )
        elif graph.get("shared_neighbors"):
            parts.append(
                f"comparte vecinos en el grafo ({', '.join(graph['shared_neighbors'][:2])})"
            )

        actionable = connection.components["actionable"].detail
        status = actionable.get("status_value")
        people = actionable.get("linked_researchers") or 0
        if status:
            fragment = f"su estado registrado es {status}"
            if people:
                fragment += f" y tiene {people} investigador(es) identificable(s)"
            parts.append(fragment)
        elif people:
            parts.append(f"tiene {people} investigador(es) identificable(s)")

        top_component = ordered[0][0] if ordered else "semantic"
        summary = (
            f"{candidate.entity_type} {candidate.id}: " + "; ".join(parts) + "."
            if parts
            else f"{candidate.entity_type} {candidate.id}."
        )
        share = (
            connection.weighted[top_component] / connection.base_total
            if connection.base_total > 0
            else 0.0
        )
        summary += (
            f" La señal que más aporta es «{top_component}»"
            f" ({share:.0%} de la puntuación antes de penalizaciones)."
        )
        if connection.penalties:
            reasons = "; ".join(item["reason"] for item in connection.penalties)
            summary += f" Penalizaciones aplicadas: {reasons}"
        return summary
