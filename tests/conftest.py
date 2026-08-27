"""Fixtures compartidas: un motor determinista sin descargas y uno real."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from knowledge_nexus_retrieval.data.corpus import SemanticCorpus
from knowledge_nexus_retrieval.data.graph_port import build_graph_port
from knowledge_nexus_retrieval.embeddings.pipeline import EmbeddingPipeline
from knowledge_nexus_retrieval.embeddings.providers import (
    HashingEmbeddingProvider,
    build_provider,
)
from knowledge_nexus_retrieval.embeddings.store import EmbeddingStore
from knowledge_nexus_retrieval.engine import KnowledgeNexusEngine
from knowledge_nexus_retrieval.settings import EngineConfig, Settings, get_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def corpus(settings: Settings) -> SemanticCorpus:
    return SemanticCorpus.from_jsonl(settings.semantic_documents_path)


@pytest.fixture(scope="session")
def fixture_contract(settings: Settings) -> dict:
    path = settings.data_dir / "team_fixture_search_response.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def offline_settings(tmp_path_factory: pytest.TempPathFactory, settings: Settings) -> Settings:
    """Ajustes sin descargas: proveedor determinista y artefacto temporal."""

    artifacts = tmp_path_factory.mktemp("offline-artifacts")
    return replace(
        settings,
        artifacts_dir=artifacts,
        embedding_provider="hashing",
        embedding_dimension=128,
        embedding_model=HashingEmbeddingProvider.MODEL_NAME,
    )


@pytest.fixture(scope="session")
def offline_engine(offline_settings: Settings, corpus: SemanticCorpus) -> KnowledgeNexusEngine:
    """Motor completo con embeddings deterministas; no requiere red ni modelo."""

    provider = build_provider(offline_settings)
    pipeline = EmbeddingPipeline(
        provider,
        offline_settings.embeddings_path,
        offline_settings.embeddings_manifest_path,
        batch_size=256,
    )
    pipeline.run(corpus, source_path=offline_settings.semantic_documents_path)
    store = EmbeddingStore.load(offline_settings.embeddings_path)
    store.validate_coverage(corpus)
    config = EngineConfig.load(offline_settings)
    graph = build_graph_port(offline_settings)
    engine = KnowledgeNexusEngine(
        offline_settings, config, corpus, graph, store, provider
    )
    yield engine
    engine.close()


@pytest.fixture(scope="session")
def real_engine(settings: Settings) -> KnowledgeNexusEngine:
    """Motor con el modelo multilingüe real; se omite si falta el artefacto."""

    if not settings.embeddings_path.is_file():
        pytest.skip(
            "Falta artifacts/embeddings/semantic_embeddings.jsonl; "
            "ejecuta `knowledge-nexus embeddings`."
        )
    try:
        engine = KnowledgeNexusEngine.build(settings)
    except Exception as error:  # pragma: no cover - depende del entorno
        pytest.skip(f"No se pudo cargar el modelo de embeddings: {error}")
    yield engine
    engine.close()

