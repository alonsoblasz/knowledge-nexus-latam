"""Señales del ranking: qué se tiene en cuenta y cómo se calcula cada componente.

Cada función devuelve un `ComponentScore` con el valor en `[0, 1]` y el detalle
que permite explicar por qué una entidad aparece antes que otra. Ninguna señal
depende del reloj: el año de referencia se toma de los propios datos.

Resumen de las seis señales:

- `semantic`  similitud del texto con la consulta (vectorial + léxica);
- `domain`    afinidad institucional y temática declarada;
- `method`    compatibilidad metodológica;
- `graph`     soporte estructural en las relaciones explícitas;
- `evidence`  cobertura de evidencia y procedencia;
- `actionable` potencial de acción (estado, vigencia, personas y recursos).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..data.graph_port import EntityResolver, GraphNavigator, entity_fields
from ..retrieval.hybrid import Candidate
from ..retrieval.query import QueryContext
from ..settings import EngineConfig
from ..text import (
    Lexicon,
    clamp01,
    counter_cosine,
    extract_canonical_ids,
    jaccard,
    overlap_coefficient,
    rescale,
    term_set,
    token_counter,
)

AREA_FIELDS = ("disciplinary_area", "research_area", "main_area", "application_context")


@dataclass(frozen=True)
class ComponentScore:
    """Valor de una señal junto con la explicación de su cálculo."""

    value: float
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def rounded(self) -> float:
        return round(self.value, 4)


def _weighted_available(parts: list[tuple[str, float | None, float]]) -> tuple[float, dict[str, Any]]:
    """Combina subseñales ignorando las que la consulta no puede evaluar.

    Una subseñal `None` significa "la consulta no aporta información para
    evaluarla", no "el candidato no la cumple": en ese caso se reparte su peso
    entre las demás en lugar de penalizar al candidato.
    """

    available = [(name, value, weight) for name, value, weight in parts if value is not None]
    detail: dict[str, Any] = {
        "subsignals": {name: (None if value is None else round(value, 4)) for name, value, _ in parts},
        "weights": {name: weight for name, _, weight in parts},
    }
    total_weight = sum(weight for _, _, weight in available)
    if not available or total_weight <= 0.0:
        detail["status"] = "sin_señal_evaluable"
        return 0.0, detail
    detail["applied_weights"] = {
        name: round(weight / total_weight, 4) for name, _, weight in available
    }
    value = sum((value or 0.0) * weight for _, value, weight in available) / total_weight
    return clamp01(value), detail


@dataclass
class FeatureContext:
    """Datos compartidos por todas las señales durante una consulta."""

    config: EngineConfig
    lexicon: Lexicon
    navigator: GraphNavigator
    resolver: EntityResolver
    context: QueryContext
    reference_year: int
    cosine_floor: float
    cosine_ceiling: float
    query_area_terms: frozenset[str] = frozenset()
    source_neighbor_ids: frozenset[str] = frozenset()

    @classmethod
    def build(
        cls,
        config: EngineConfig,
        lexicon: Lexicon,
        navigator: GraphNavigator,
        resolver: EntityResolver,
        context: QueryContext,
        reference_year: int,
        cosine_floor: float,
        cosine_ceiling: float,
    ) -> "FeatureContext":
        area_terms: set[str] = set()
        neighbor_ids: set[str] = set()
        source = context.source_entity
        if source is not None:
            properties = source.get("properties", {})
            for field_name in AREA_FIELDS:
                area_terms |= term_set(properties.get(field_name), lexicon.stopwords)
            neighbor_ids = navigator.neighbor_ids(str(source["id"]))
        # Las unidades declaradas por la entidad de origen aportan su propia
        # área: una necesidad no declara área disciplinar, pero su facultad sí.
        for anchor in context.anchors:
            entity = resolver.resolve(anchor)
            if entity is None:
                continue
            properties = entity.get("properties", {})
            for field_name in (*AREA_FIELDS, "faculty_name", "program_name", "group_name"):
                area_terms |= term_set(properties.get(field_name), lexicon.stopwords)
        return cls(
            config=config,
            lexicon=lexicon,
            navigator=navigator,
            resolver=resolver,
            context=context,
            reference_year=reference_year,
            cosine_floor=cosine_floor,
            cosine_ceiling=cosine_ceiling,
            query_area_terms=frozenset(area_terms),
            source_neighbor_ids=frozenset(neighbor_ids),
        )

    def profile(self, entity_type: str) -> dict[str, Any]:
        return self.config.profile(entity_type)


# --------------------------------------------------------------------------
# 1. Similitud semántica
# --------------------------------------------------------------------------
def semantic_component(candidate: Candidate, features: FeatureContext) -> ComponentScore:
    """Fusiona el canal vectorial (multilingüe) con el canal léxico BM25.

    El coseno se reescala con la calibración medida para el modelo: por debajo
    del piso la similitud es indistinguible del ruido del corpus.
    """

    config = features.config.ranking.get("semantic", {})
    vector_weight = float(config.get("vector_weight", 0.70))
    lexical_weight = float(config.get("lexical_weight", 0.30))
    calibrated = rescale(candidate.vector_score, features.cosine_floor, features.cosine_ceiling)
    lexical = clamp01(candidate.lexical_normalized)
    total_weight = vector_weight + lexical_weight
    value = (vector_weight * calibrated + lexical_weight * lexical) / max(total_weight, 1e-9)
    return ComponentScore(
        value=clamp01(value),
        detail={
            "vector_similarity": round(candidate.vector_score, 4),
            "vector_calibrated": round(calibrated, 4),
            "calibration": {
                "floor": features.cosine_floor,
                "ceiling": features.cosine_ceiling,
            },
            "lexical_bm25": round(candidate.lexical_score, 4),
            "lexical_normalized": round(lexical, 4),
            "matched_terms": candidate.matched_terms[:8],
            "weights": {"vector": vector_weight, "lexical": lexical_weight},
            "channels": sorted(candidate.channels),
        },
    )


# --------------------------------------------------------------------------
# 2. Compatibilidad de dominio
# --------------------------------------------------------------------------
def _candidate_anchors(candidate: Candidate, features: FeatureContext) -> set[str]:
    properties = candidate.properties
    anchors: set[str] = set()
    for field_name in features.config.anchor_fields:
        anchors |= extract_canonical_ids(properties.get(field_name), features.resolver.known_ids)
    return anchors


def domain_component(candidate: Candidate, features: FeatureContext) -> ComponentScore:
    """Mide si el candidato pertenece al mismo dominio institucional y temático."""

    config = features.config.ranking.get("domain", {})
    context = features.context
    profile = features.profile(candidate.entity_type)
    properties = candidate.properties

    query_anchors = set(context.anchors)
    institutional: float | None = None
    shared_anchors: list[str] = []
    if query_anchors:
        candidate_anchors = _candidate_anchors(candidate, features)
        shared = query_anchors & candidate_anchors
        shared_anchors = sorted(shared)
        institutional = len(shared) / len(query_anchors)

    candidate_terms = token_counter(
        [properties.get(field_name) for field_name in (profile.get("domain_fields") or [])],
        features.lexicon.stopwords,
    )
    topical: float | None = None
    shared_terms: list[str] = []
    if context.domain_terms and candidate_terms:
        topical = counter_cosine(context.domain_terms, candidate_terms)
        shared_terms = sorted(set(context.domain_terms) & set(candidate_terms))[:8]

    area: float | None = None
    candidate_area_terms: set[str] = set()
    if features.query_area_terms:
        for field_name in AREA_FIELDS:
            candidate_area_terms |= term_set(
                properties.get(field_name), features.lexicon.stopwords
            )
        area = (
            overlap_coefficient(set(features.query_area_terms), candidate_area_terms)
            if candidate_area_terms
            else 0.0
        )

    value, detail = _weighted_available(
        [
            ("institutional", institutional, float(config.get("institutional_weight", 0.35))),
            ("topical", topical, float(config.get("topical_weight", 0.40))),
            ("area", area, float(config.get("area_weight", 0.25))),
        ]
    )
    detail.update(
        {
            "shared_units": shared_anchors,
            "shared_terms": shared_terms,
            "candidate_area_terms": sorted(candidate_area_terms)[:8],
        }
    )
    return ComponentScore(value=value, detail=detail)


# --------------------------------------------------------------------------
# 3. Compatibilidad metodológica
# --------------------------------------------------------------------------
def method_component(candidate: Candidate, features: FeatureContext) -> ComponentScore:
    """Compara el vocabulario metodológico declarado por ambas partes."""

    config = features.config.ranking.get("method", {})
    profile = features.profile(candidate.entity_type)
    properties = candidate.properties
    method_values = [properties.get(field_name) for field_name in (profile.get("method_fields") or [])]
    method_text = " ".join(str(value) for value in method_values if value)
    candidate_terms = features.lexicon.method_signals(method_text)

    if features.context.method_terms:
        query_terms = set(features.context.method_terms)
        shared = query_terms & candidate_terms
        value = len(shared) / len(query_terms) if query_terms else 0.0
        detail = {
            "mode": "comparada_con_la_consulta",
            "query_method_terms": sorted(query_terms),
            "candidate_method_terms": sorted(candidate_terms),
            "shared_method_terms": sorted(shared),
        }
        return ComponentScore(value=clamp01(value), detail=detail)

    # Sin señal metodológica en la consulta se evalúa la sustancia declarada por
    # el candidato: tener metodología explícita es información accionable.
    declared = 1.0 if method_text.strip() else 0.0
    density = min(1.0, len(candidate_terms) / 3.0)
    value = float(config.get("declared_weight", 0.5)) * declared + float(
        config.get("density_weight", 0.5)
    ) * density
    value = min(value, float(config.get("fallback_cap", 0.75)))
    return ComponentScore(
        value=clamp01(value),
        detail={
            "mode": "sustancia_metodologica_declarada",
            "reason": "La consulta no declara metodología; se valora la del candidato.",
            "declared": bool(method_text.strip()),
            "fallback_cap": float(config.get("fallback_cap", 0.75)),
            "candidate_method_terms": sorted(candidate_terms),
        },
    )


# --------------------------------------------------------------------------
# 4. Soporte estructural del grafo
# --------------------------------------------------------------------------
def graph_component(candidate: Candidate, features: FeatureContext) -> ComponentScore:
    """Mide cercanía estructural, conectividad y puentes compartidos.

    Solo usa relaciones explícitas de Data V1.0. Una necesidad sin aristas hacia
    proyectos obtiene proximidad cero: el motor no inventa el enlace que falta.
    """

    config = features.config.ranking.get("graph", {})
    decay = [float(value) for value in config.get("hop_decay", [1.0, 0.6, 0.3])]
    context = features.context

    proximity: float | None = None
    distance: int | None = None
    if context.source_id:
        distance = features.navigator.distance(context.source_id, candidate.id)
        proximity = decay[distance - 1] if distance and 1 <= distance <= len(decay) else 0.0
    if candidate.graph_hops is not None and 1 <= candidate.graph_hops <= len(decay):
        # Alcanzado por expansión desde un candidato recuperado: cuenta como
        # soporte, con descuento por no partir de la entidad consultada.
        seed_support = 0.75 * decay[candidate.graph_hops - 1]
        proximity = seed_support if proximity is None else max(proximity, seed_support)

    degree = features.navigator.degree(candidate.id)
    degree_cap = float(config.get("degree_cap", 12))
    connectivity = clamp01(math.log1p(degree) / math.log1p(degree_cap)) if degree_cap > 0 else 0.0

    bridge: float | None = None
    shared_neighbors: list[str] = []
    reference = set(features.source_neighbor_ids) | set(context.anchors)
    if reference:
        candidate_neighbors = features.navigator.neighbor_ids(candidate.id)
        shared = reference & candidate_neighbors
        shared_neighbors = sorted(shared)[:8]
        bridge = jaccard(reference, candidate_neighbors) if shared else 0.0
        if shared:
            bridge = max(bridge, len(shared) / len(reference))

    value, detail = _weighted_available(
        [
            ("proximity", proximity, float(config.get("proximity_weight", 0.45))),
            ("connectivity", connectivity, float(config.get("connectivity_weight", 0.35))),
            ("context_bridge", bridge, float(config.get("context_bridge_weight", 0.20))),
        ]
    )
    detail.update(
        {
            "explicit_distance_from_source": distance,
            "expansion_hops": candidate.graph_hops,
            "degree": degree,
            "shared_neighbors": shared_neighbors,
        }
    )
    return ComponentScore(value=value, detail=detail)


# --------------------------------------------------------------------------
# 5. Cobertura de evidencia
# --------------------------------------------------------------------------
def evidence_component(candidate: Candidate, features: FeatureContext) -> ComponentScore:
    """Cuánta evidencia verificable respalda a la entidad candidata."""

    config = features.config.ranking.get("evidence", {})
    profile = features.profile(candidate.entity_type)
    properties = entity_fields(candidate.entity)
    fields = list(profile.get("evidence_fields") or [])
    filled = [name for name in fields if str(properties.get(name) or "").strip()]
    field_coverage = len(filled) / len(fields) if fields else 0.0

    source = candidate.entity.get("source") or {}
    present = sum(1 for key in ("file", "row", "path") if source.get(key) not in (None, ""))
    provenance = present / 3.0

    neighbors = features.navigator.neighbors(candidate.id)
    with_provenance = [item for item in neighbors if item.get("provenance")]
    cap = float(config.get("relation_provenance_cap", 3))
    relation_provenance = clamp01(len(with_provenance) / cap) if cap > 0 else 0.0

    has_document = any(item.get("relationship") == "DESCRIBES" for item in neighbors)
    document_reference = bool(
        str(properties.get("source_document") or properties.get("repository_reference") or "").strip()
    )
    document_support = 1.0 if (has_document or document_reference) else 0.0

    value, detail = _weighted_available(
        [
            ("field_coverage", field_coverage, float(config.get("field_coverage_weight", 0.50))),
            ("provenance", provenance, float(config.get("provenance_weight", 0.20))),
            (
                "relation_provenance",
                relation_provenance,
                float(config.get("relation_provenance_weight", 0.20)),
            ),
            ("document_support", document_support, float(config.get("document_weight", 0.10))),
        ]
    )
    detail.update(
        {
            "fields_with_content": filled,
            "fields_expected": fields,
            "relations_with_provenance": len(with_provenance),
            "has_document": has_document,
        }
    )
    return ComponentScore(value=value, detail=detail)


# --------------------------------------------------------------------------
# 6. Potencial accionable
# --------------------------------------------------------------------------
def _entity_year(properties: dict[str, Any], profile: dict[str, Any]) -> int | None:
    for field_name in profile.get("year_fields") or []:
        value = properties.get(field_name)
        try:
            year = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if 1900 < year < 2200:
            return year
    return None


def actionable_component(candidate: Candidate, features: FeatureContext) -> ComponentScore:
    """Estima si la conexión puede traducirse en una acción institucional."""

    config = features.config.ranking.get("actionable", {})
    profile = features.profile(candidate.entity_type)
    properties = candidate.properties

    status_scores = {
        str(key).upper(): float(value) for key, value in (config.get("status_scores") or {}).items()
    }
    default_status = float(config.get("default_status_score", 0.70))
    raw_status = properties.get(profile.get("status_field") or "status")
    active_flag = properties.get(profile.get("active_field") or "active")
    if raw_status not in (None, ""):
        status = status_scores.get(str(raw_status).strip().upper(), default_status)
    elif isinstance(active_flag, bool):
        status = 1.0 if active_flag else float(status_scores.get("INACTIVE", 0.2))
    else:
        status = default_status

    year = _entity_year(properties, profile)
    half_life = float(config.get("recency_half_life_years", 6.0))
    recency: float | None = None
    if year is not None and half_life > 0:
        age = max(0, features.reference_year - year)
        recency = clamp01(math.pow(0.5, age / half_life))

    neighbors = features.navigator.neighbors(candidate.id)
    people = [
        item for item in neighbors if str(item["target"].get("entity_type")) == "Researcher"
    ]
    people_signal: float | None = None
    if candidate.entity_type == "Researcher":
        people_signal = clamp01(len(neighbors) / 4.0)
    elif people or candidate.entity_type in {"Project", "Thesis", "Publication", "ResearchGroup"}:
        people_signal = clamp01(len(people) / 2.0)

    output_relations = set(profile.get("output_relations") or [])
    outputs: float | None = None
    if output_relations:
        produced = [item for item in neighbors if item["relationship"] in output_relations]
        outputs = clamp01(len(produced) / 2.0)

    resources: float | None = None
    maturity_field = profile.get("maturity_field")
    if maturity_field:
        try:
            maturity = float(properties.get(maturity_field))  # type: ignore[arg-type]
            resources = clamp01(maturity / float(profile.get("maturity_max", 5)))
        except (TypeError, ValueError):
            resources = None

    value, detail = _weighted_available(
        [
            ("status", status, 0.35),
            ("recency", recency, 0.25),
            ("people", people_signal, 0.20),
            ("outputs", outputs, 0.10),
            ("resources", resources, 0.10),
        ]
    )
    detail.update(
        {
            "status_value": raw_status if raw_status not in (None, "") else active_flag,
            "year": year,
            "reference_year": features.reference_year,
            "linked_researchers": len(people),
        }
    )
    return ComponentScore(value=value, detail=detail)


COMPONENT_FUNCTIONS = {
    "semantic": semantic_component,
    "domain": domain_component,
    "method": method_component,
    "graph": graph_component,
    "evidence": evidence_component,
    "actionable": actionable_component,
}


DUPLICATE_TEXT_CHARS = 600


def candidate_term_profile(
    candidate: Candidate,
    lexicon: Lexicon,
    cache: dict[str, Counter[str]] | None = None,
) -> Counter[str]:
    """Vector de términos del candidato, memorizado por consulta.

    Se acota el texto porque la detección de redundancia solo necesita
    reconocer registros casi idénticos, no comparar documentos completos.
    """

    if cache is not None and candidate.id in cache:
        return cache[candidate.id]
    body = candidate.document.text[:DUPLICATE_TEXT_CHARS] if candidate.document else ""
    profile = token_counter([candidate.title, body], lexicon.stopwords)
    if cache is not None:
        cache[candidate.id] = profile
    return profile


def duplicate_similarity(
    left: Candidate,
    right: Candidate,
    lexicon: Lexicon,
    cache: dict[str, Counter[str]] | None = None,
) -> float:
    """Similitud superficial entre candidatos, usada para detectar redundancia."""

    return counter_cosine(
        candidate_term_profile(left, lexicon, cache),
        candidate_term_profile(right, lexicon, cache),
    )
