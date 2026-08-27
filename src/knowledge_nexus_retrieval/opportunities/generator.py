"""Generador determinista de oportunidades de investigación.

La estructura y las entidades las decide el sistema a partir del paquete de
evidencia. Un LLM puede mejorar la redacción, pero nunca añade IDs, personas,
capacidades ni fuentes. Una oportunidad es una hipótesis sustentada, no una
decisión académica aprobada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..data.graph_port import GraphNavigator
from ..evidence.assembler import EvidencePackage
from ..ranking.scorer import ScoredConnection
from ..retrieval.query import QueryContext
from ..settings import EngineConfig

VALID_TYPES = (
    "NEW_RESEARCH",
    "RESEARCH_CONTINUITY",
    "THESIS_TOPIC",
    "COLLABORATION",
    "CAPABILITY_ACTIVATION",
    "CURRICULAR_INTEGRATION",
    "KNOWLEDGE_TRANSFER",
)

CURRICULAR_TYPES = frozenset({"Subject", "Competency", "LearningOutcome", "Program"})
COMPLETED_STATUSES = frozenset({"COMPLETED", "APPROVED", "PUBLISHED", "CLOSED", "DEFENDED"})


@dataclass
class SupportSummary:
    """Recuento de respaldo disponible entre las conexiones mejor rankeadas."""

    completed_antecedents: list[str] = field(default_factory=list)
    theses: list[str] = field(default_factory=list)
    publications: list[str] = field(default_factory=list)
    researchers: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    mature_capabilities: list[str] = field(default_factory=list)
    curricular: list[str] = field(default_factory=list)
    top_score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "completed_antecedents": self.completed_antecedents,
            "theses": self.theses,
            "publications": self.publications,
            "researchers": self.researchers,
            "distinct_groups": self.groups,
            "capabilities": self.capabilities,
            "mature_capabilities": self.mature_capabilities,
            "curricular": self.curricular,
            "top_score": round(self.top_score, 4),
        }


@dataclass
class Opportunity:
    """Oportunidad propuesta con sus entidades de respaldo y su incertidumbre."""

    opportunity_id: str
    type: str
    title: str
    reason: str
    priority: str
    related_entities: list[dict[str, Any]]
    supporting_connections: list[str] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    relation_origin: str = "INFERRED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "type": self.type,
            "title": self.title,
            "reason": self.reason,
            "priority": self.priority,
            "related_entities": self.related_entities,
            "supporting_connections": self.supporting_connections,
            "uncertainty": self.uncertainty,
            "relation_origin": self.relation_origin,
            "status": "PROPOSED",
            "disclaimer": (
                "Hipótesis sustentada en evidencia recuperada; no representa una "
                "decisión ni una aprobación institucional."
            ),
        }


class OpportunityGenerator:
    """Clasifica el tipo de oportunidad y completa una plantilla con evidencia."""

    def __init__(self, config: EngineConfig, navigator: GraphNavigator):
        self._config = config
        self._navigator = navigator

    def summarize(
        self, connections: list[ScoredConnection], window: int = 10
    ) -> SupportSummary:
        summary = SupportSummary()
        selected = connections[:window]
        if selected:
            summary.top_score = selected[0].total
        for connection in selected:
            candidate = connection.candidate
            properties = candidate.properties
            status = str(properties.get("status") or "").strip().upper()
            entity_type = candidate.entity_type
            if entity_type == "Project" and status in COMPLETED_STATUSES:
                summary.completed_antecedents.append(candidate.id)
            elif entity_type == "Thesis":
                summary.theses.append(candidate.id)
                if status in COMPLETED_STATUSES:
                    summary.completed_antecedents.append(candidate.id)
            elif entity_type == "Publication":
                summary.publications.append(candidate.id)
                summary.completed_antecedents.append(candidate.id)
            elif entity_type == "Researcher":
                summary.researchers.append(candidate.id)
            elif entity_type == "ResearchGroup":
                summary.groups.append(candidate.id)
            elif entity_type == "Capability":
                summary.capabilities.append(candidate.id)
                try:
                    if float(properties.get("maturity_level")) >= 3:  # type: ignore[arg-type]
                        summary.mature_capabilities.append(candidate.id)
                except (TypeError, ValueError):
                    pass
            elif entity_type in CURRICULAR_TYPES:
                summary.curricular.append(candidate.id)

        # Los grupos de los investigadores recuperados amplían el respaldo de
        # colaboración sin inventar relaciones: se leen del grafo explícito.
        for researcher_id in summary.researchers:
            for neighbor in self._navigator.neighbors(researcher_id):
                if neighbor["relationship"] == "MEMBER_OF_GROUP":
                    group_id = str(neighbor["target"]["id"])
                    if group_id not in summary.groups:
                        summary.groups.append(group_id)
        return summary

    def generate(
        self,
        context: QueryContext,
        connections: list[ScoredConnection],
        package: EvidencePackage,
        limit: int = 3,
    ) -> list[Opportunity]:
        if not connections:
            return []
        summary = self.summarize(connections)
        rules = self._config.relation_rules.get("opportunity_rules", []) or []
        thresholds = self._config.relation_rules.get("priority_thresholds", {})
        focus = self._focus(context, connections)
        base = context.source_id or "QUERY"

        opportunities: list[Opportunity] = []
        for rule in rules:
            if len(opportunities) >= limit:
                break
            rule_type = str(rule.get("type"))
            if rule_type not in VALID_TYPES:
                raise ValueError(f"Tipo de oportunidad no permitido: {rule_type}")
            if rule.get("fallback") and opportunities:
                # Regla de respaldo: solo aplica si nada más encontró soporte.
                continue
            if not self._satisfies(rule.get("requires") or {}, summary):
                continue
            supporting = self._supporting_connections(rule_type, connections, summary)
            if not supporting:
                continue
            related = self._related_entities(context, supporting, package)
            if not related:
                continue
            opportunity = Opportunity(
                opportunity_id=f"OPP-{base}-{len(opportunities) + 1:03d}",
                type=rule_type,
                title=str(rule.get("title_template", "Oportunidad sobre {focus}")).format(
                    focus=focus
                ),
                reason=self._reason(rule_type, supporting, summary, context),
                priority=self._priority(context, summary, thresholds),
                related_entities=related,
                supporting_connections=[item.candidate.id for item in supporting],
                uncertainty=self._uncertainty(context, summary, supporting),
            )
            package.guard.validate(
                [str(entity["id"]) for entity in opportunity.related_entities],
                f"oportunidad {opportunity.opportunity_id}",
            )
            opportunities.append(opportunity)
        return opportunities

    # Reglas ---------------------------------------------------------------
    def _satisfies(self, requires: dict[str, Any], summary: SupportSummary) -> bool:
        checks = {
            "completed_antecedents_min": len(summary.completed_antecedents),
            "theses_min": len(summary.theses),
            "publications_min": len(summary.publications),
            "researchers_min": len(summary.researchers),
            "distinct_groups_min": len(set(summary.groups)),
            "capabilities_min": len(summary.capabilities),
            "curricular_min": len(summary.curricular),
        }
        for key, minimum in requires.items():
            if key == "min_top_score":
                if summary.top_score < float(minimum):
                    return False
            elif key == "capability_min_maturity":
                if not summary.mature_capabilities:
                    return False
            elif key in checks:
                if checks[key] < int(minimum):
                    return False
            else:
                raise ValueError(f"Requisito de oportunidad desconocido: {key}")
        return True

    def _supporting_connections(
        self,
        opportunity_type: str,
        connections: list[ScoredConnection],
        summary: SupportSummary,
    ) -> list[ScoredConnection]:
        preferred: dict[str, tuple[str, ...]] = {
            "RESEARCH_CONTINUITY": ("Project", "Thesis", "Publication", "Researcher", "Capability"),
            "CAPABILITY_ACTIVATION": ("Capability", "Researcher", "Project", "Subject"),
            "THESIS_TOPIC": ("Thesis", "Subject", "Researcher", "Project"),
            "COLLABORATION": ("Researcher", "ResearchGroup", "Project", "Capability"),
            "CURRICULAR_INTEGRATION": ("Subject", "Competency", "LearningOutcome", "Program"),
            "KNOWLEDGE_TRANSFER": ("Publication", "Capability", "Project", "Researcher"),
            "NEW_RESEARCH": ("Project", "Thesis", "Researcher", "Capability", "Subject"),
        }
        order = preferred.get(opportunity_type, ())
        selected: list[ScoredConnection] = []
        for entity_type in order:
            for connection in connections:
                if connection.candidate.entity_type != entity_type:
                    continue
                if connection not in selected:
                    selected.append(connection)
                    break
        return selected[:5]

    def _focus(self, context: QueryContext, connections: list[ScoredConnection]) -> str:
        if context.source_entity is not None:
            title = str(context.source_entity.get("title") or "").strip()
            if title:
                return title[0].lower() + title[1:] if title[:1].isupper() else title
        top = connections[0].candidate.title if connections else ""
        return (top or context.raw_query).strip()[:110]

    def _related_entities(
        self,
        context: QueryContext,
        supporting: list[ScoredConnection],
        package: EvidencePackage,
    ) -> list[dict[str, Any]]:
        related: list[dict[str, Any]] = []
        seen: set[str] = set()
        if context.source_entity is not None:
            summary = package.entity_summary(str(context.source_entity["id"]))
            if summary is not None:
                related.append(summary)
                seen.add(str(summary["id"]))
        for connection in supporting:
            identifier = connection.candidate.id
            if identifier in seen:
                continue
            summary = package.entity_summary(identifier)
            if summary is None:
                continue
            related.append(summary)
            seen.add(identifier)
        return related

    def _reason(
        self,
        opportunity_type: str,
        supporting: list[ScoredConnection],
        summary: SupportSummary,
        context: QueryContext,
    ) -> str:
        references = ", ".join(
            f"{connection.candidate.id} ({connection.candidate.entity_type})"
            for connection in supporting[:4]
        )
        need = (
            f"la necesidad {context.source_id}"
            if context.source_id
            else "la consulta recibida"
        )
        motives = {
            "RESEARCH_CONTINUITY": (
                f"Existen antecedentes terminados ({', '.join(summary.completed_antecedents[:3])}) "
                f"que pueden continuarse para atender {need}."
            ),
            "CAPABILITY_ACTIVATION": (
                f"Hay capacidad institucional declarada con madurez suficiente "
                f"({', '.join(summary.mature_capabilities[:3])}) aplicable a {need}."
            ),
            "THESIS_TOPIC": (
                f"Se identificaron trabajos de grado afines ({', '.join(summary.theses[:3])}) "
                f"que permiten abrir una línea de tesis sobre {need}."
            ),
            "COLLABORATION": (
                f"Participan investigadores de {len(set(summary.groups))} grupos distintos, "
                f"lo que habilita una colaboración interdisciplinaria para {need}."
            ),
            "CURRICULAR_INTEGRATION": (
                f"Existen elementos curriculares afines ({', '.join(summary.curricular[:3])}) "
                f"que pueden integrarse para responder a {need}."
            ),
            "KNOWLEDGE_TRANSFER": (
                f"Hay producción publicada ({', '.join(summary.publications[:3])}) y capacidad "
                f"instalada para transferir conocimiento hacia {need}."
            ),
            "NEW_RESEARCH": (
                f"No se encontraron antecedentes terminados suficientes para {need}, "
                "por lo que se propone una investigación exploratoria."
            ),
        }
        motive = motives.get(opportunity_type, f"Respaldo disponible para {need}.")
        return f"{motive} Respaldo recuperado: {references}."

    def _priority(
        self, context: QueryContext, summary: SupportSummary, thresholds: dict[str, Any]
    ) -> str:
        declared = ""
        if context.source_entity is not None:
            declared = str(
                context.source_entity.get("properties", {}).get("priority") or ""
            ).strip().upper()
        high = float(thresholds.get("HIGH", 0.60))
        medium = float(thresholds.get("MEDIUM", 0.40))
        if declared == "HIGH" or summary.top_score >= high:
            return "HIGH"
        if declared == "MEDIUM" or summary.top_score >= medium:
            return "MEDIUM"
        return "LOW"

    def _uncertainty(
        self,
        context: QueryContext,
        summary: SupportSummary,
        supporting: list[ScoredConnection],
    ) -> list[str]:
        notes: list[str] = [
            "Las conexiones que sustentan esta oportunidad son inferidas por similitud "
            "y estructura del grafo; no existen como relación explícita en Data V1.0."
        ]
        if context.source_id is None:
            notes.append(
                "La consulta no indicó una necesidad institucional: el foco se derivó del texto."
            )
        if not summary.mature_capabilities:
            notes.append("No se recuperó una capacidad con nivel de madurez declarado.")
        if not summary.researchers:
            notes.append("No se recuperaron investigadores directamente asociados.")
        weak = [item for item in supporting if item.total < 0.45]
        if weak:
            notes.append(
                "Parte del respaldo tiene relevancia moderada: "
                + ", ".join(f"{item.candidate.id} ({item.total:.2f})" for item in weak[:3])
            )
        return notes
