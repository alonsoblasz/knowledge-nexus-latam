"""Contratos de entrada y salida de la API.

La respuesta de búsqueda conserva la estructura de
`team_fixture_search_response.json`. Se añaden campos compatibles (`graph`,
`meta`, `components_detail`, `retrieval`), pero no se renombra ni se elimina
ninguno de los existentes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Tipos aceptados por la API. Limitar el conjunto evita que una solicitud
# arbitraria alcance etiquetas o consultas no previstas.
ALLOWED_ENTITY_TYPES = (
    "Faculty",
    "Program",
    "ResearchGroup",
    "ResearchLine",
    "Capability",
    "Researcher",
    "Expertise",
    "Subject",
    "Competency",
    "LearningOutcome",
    "InstitutionalNeed",
    "Project",
    "Thesis",
    "Publication",
    "Document",
)


class SearchRequestModel(BaseModel):
    """Solicitud mínima de búsqueda."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(default="", max_length=2000, description="Pregunta o necesidad en texto libre")
    source_entity_id: str | None = Field(
        default=None, max_length=64, description="ID canónico de la entidad de origen, por ejemplo NEED-001"
    )
    target_types: list[str] | None = Field(
        default=None, description="Tipos de entidad a recuperar; por defecto los priorizados para una necesidad"
    )
    limit: int = Field(default=5, ge=1, le=50)
    include_opportunities: bool = True
    max_opportunities: int = Field(default=3, ge=0, le=10)
    include_graph: bool = True
    include_discarded: bool = True
    discarded_limit: int = Field(default=3, ge=0, le=10)

    @model_validator(mode="after")
    def _validate(self) -> "SearchRequestModel":
        if not self.query.strip() and not (self.source_entity_id or "").strip():
            raise ValueError("Indica `query`, `source_entity_id` o ambos")
        if self.target_types is not None:
            if not self.target_types:
                raise ValueError("`target_types` no puede ser una lista vacía")
            unknown = sorted(set(self.target_types) - set(ALLOWED_ENTITY_TYPES))
            if unknown:
                raise ValueError(
                    f"Tipos de entidad no permitidos: {unknown}. "
                    f"Permitidos: {list(ALLOWED_ENTITY_TYPES)}"
                )
        return self


class OpportunitiesRequestModel(SearchRequestModel):
    """Solicitud de oportunidades; reutiliza el contrato de búsqueda."""

    limit: int = Field(default=10, ge=1, le=50)
    max_opportunities: int = Field(default=3, ge=1, le=10)


class EntitySummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None
    type: str | None
    title: str | None


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    file: str | None
    row: int | None
    record_id: str
    field: str
    excerpt: str


class RelevanceBreakdown(BaseModel):
    model_config = ConfigDict(extra="allow")

    total: float
    semantic: float
    domain: float
    method: float
    graph: float
    evidence: float


class ConnectionModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    connection_id: str
    source: EntitySummary
    target: EntitySummary
    relation: str
    relation_origin: str
    relevance: RelevanceBreakdown
    explanation: str
    evidence: list[EvidenceItem]


class OpportunityModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    opportunity_id: str
    type: str
    title: str
    reason: str
    priority: str
    related_entities: list[EntitySummary]


class SearchResponseModel(BaseModel):
    """Misma forma que el fixture del equipo, con extensiones compatibles."""

    model_config = ConfigDict(extra="allow")

    contract_version: str
    fixture_only: bool
    warning: str
    query_entity: EntitySummary
    connections: list[ConnectionModel]
    opportunities: list[OpportunityModel]


class OpportunitiesResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    contract_version: str
    fixture_only: bool
    warning: str
    query_entity: EntitySummary
    opportunities: list[OpportunityModel]


class HealthResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    service: str
    version: str
    contract_version: str
    ranking_version: str
    embedding_model: str
    embedding_dimension: int
    documents_indexed: int


class ErrorResponseModel(BaseModel):
    detail: str
    hint: str | None = None


class EntityResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    contract_version: str
    entity: dict[str, Any]
    neighbors: list[dict[str, Any]]
    evidence: dict[str, Any]
