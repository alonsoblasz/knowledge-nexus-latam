"""Aplicación FastAPI del motor de búsqueda híbrida.

La interfaz debe poder pasar del fixture a la API cambiando únicamente la URL
del servicio: la forma de la respuesta es la misma.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware

from .. import CONTRACT_VERSION, __version__
from ..engine import KnowledgeNexusEngine, SearchRequest
from ..settings import get_settings
from .schemas import (
    ALLOWED_ENTITY_TYPES,
    EntityResponseModel,
    ErrorResponseModel,
    HealthResponseModel,
    OpportunitiesRequestModel,
    OpportunitiesResponseModel,
    SearchRequestModel,
    SearchResponseModel,
)

LOGGER = logging.getLogger("knowledge_nexus.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Construye el motor una sola vez: los embeddings no se calculan por consulta."""

    settings = get_settings()
    LOGGER.info(
        "Iniciando motor (backend=%s, modelo=%s)",
        settings.graph_backend,
        settings.embedding_model,
    )
    engine = KnowledgeNexusEngine.build(settings)
    app.state.engine = engine
    try:
        yield
    finally:
        engine.close()


def get_engine(request: Request) -> KnowledgeNexusEngine:
    engine = getattr(request.app.state, "engine", None)
    if engine is None:  # pragma: no cover - solo si el arranque falló
        raise HTTPException(status_code=503, detail="El motor no está disponible")
    return engine


def create_app(engine: KnowledgeNexusEngine | None = None) -> FastAPI:
    """Crea la aplicación. Si se inyecta un motor, se omite el arranque perezoso."""

    app = FastAPI(
        title="Knowledge Nexus — Búsqueda híbrida",
        version=__version__,
        summary=(
            "Conexiones explicables entre necesidades institucionales y el "
            "conocimiento existente, con evidencia y procedencia."
        ),
        lifespan=None if engine is not None else lifespan,
    )
    if engine is not None:
        app.state.engine = engine

    origins = [
        item.strip()
        for item in os.environ.get("KNOWLEDGE_NEXUS_CORS_ORIGINS", "*").split(",")
        if item.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponseModel, tags=["operación"])
    def health(engine: KnowledgeNexusEngine = Depends(get_engine)) -> dict[str, Any]:
        """Estado del servicio, modelo activo y versión del ranking."""

        return engine.health()

    @app.post(
        "/v1/search",
        response_model=SearchResponseModel,
        tags=["búsqueda"],
        responses={404: {"model": ErrorResponseModel}},
    )
    def search(
        payload: SearchRequestModel,
        engine: KnowledgeNexusEngine = Depends(get_engine),
    ) -> dict[str, Any]:
        """Conexiones priorizadas con desglose del ranking, evidencia y procedencia."""

        return _run(engine, payload, opportunities_only=False)

    @app.post(
        "/v1/opportunities",
        response_model=OpportunitiesResponseModel,
        tags=["oportunidades"],
        responses={404: {"model": ErrorResponseModel}},
    )
    def opportunities(
        payload: OpportunitiesRequestModel,
        engine: KnowledgeNexusEngine = Depends(get_engine),
    ) -> dict[str, Any]:
        """Oportunidades sustentadas únicamente en entidades recuperadas."""

        return _run(engine, payload, opportunities_only=True)

    @app.get(
        "/v1/entities/{entity_type}/{entity_id}",
        response_model=EntityResponseModel,
        tags=["entidades"],
        responses={404: {"model": ErrorResponseModel}},
    )
    def entity(
        entity_type: str = Path(..., description="Etiqueta canónica, por ejemplo Project"),
        entity_id: str = Path(..., max_length=64),
        engine: KnowledgeNexusEngine = Depends(get_engine),
    ) -> dict[str, Any]:
        """Entidad canónica con su vecindario explícito y su evidencia."""

        if entity_type not in ALLOWED_ENTITY_TYPES:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Tipo de entidad no permitido: {entity_type}. "
                    f"Permitidos: {list(ALLOWED_ENTITY_TYPES)}"
                ),
            )
        payload = engine.entity(entity_type, entity_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail=f"No existe {entity_type} {entity_id} en Data V1.0",
            )
        return payload

    @app.get("/v1/needs", tags=["entidades"])
    def needs(
        limit: int = 50,
        engine: KnowledgeNexusEngine = Depends(get_engine),
    ) -> dict[str, Any]:
        """Necesidades institucionales disponibles para el selector de la interfaz."""

        return {"contract_version": CONTRACT_VERSION, "needs": engine.list_needs(limit)}

    return app


def _run(
    engine: KnowledgeNexusEngine,
    payload: SearchRequestModel,
    opportunities_only: bool,
) -> dict[str, Any]:
    request = SearchRequest(
        query=payload.query,
        source_entity_id=payload.source_entity_id,
        target_types=payload.target_types,
        limit=payload.limit,
        include_opportunities=payload.include_opportunities,
        max_opportunities=payload.max_opportunities,
        include_graph=payload.include_graph,
        include_discarded=payload.include_discarded,
        discarded_limit=payload.discarded_limit,
    )
    try:
        return engine.opportunities(request) if opportunities_only else engine.search(request)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


app = create_app()
