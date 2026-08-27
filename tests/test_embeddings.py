"""Pruebas del pipeline de embeddings: dimensión, cobertura y reanudación."""

from __future__ import annotations

import json

import pytest

from knowledge_nexus_retrieval.data.corpus import (
    DuplicateDocumentError,
    SemanticCorpus,
    SemanticDocument,
)
from knowledge_nexus_retrieval.embeddings.pipeline import (
    EmbeddingModelMismatchError,
    EmbeddingPipeline,
    text_sha256,
)
from knowledge_nexus_retrieval.embeddings.providers import HashingEmbeddingProvider
from knowledge_nexus_retrieval.embeddings.store import EmbeddingStore, EmbeddingStoreError


def _pipeline(tmp_path, dimension: int = 64) -> EmbeddingPipeline:
    provider = HashingEmbeddingProvider(dimension)
    return EmbeddingPipeline(
        provider, tmp_path / "embeddings.jsonl", tmp_path / "manifest.json", batch_size=32
    )


def test_dimension_constante_y_cobertura_total(tmp_path, corpus):
    pipeline = _pipeline(tmp_path)
    subset = corpus.ids[:120]
    result = pipeline.run(corpus, document_ids=subset)

    assert result.generated == 120
    records = [
        json.loads(line)
        for line in (tmp_path / "embeddings.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 120
    assert {len(record["embedding"]) for record in records} == {64}
    assert {record["dimension"] for record in records} == {64}
    assert [record["id"] for record in records] == list(subset)


def test_hash_del_texto_indexado(tmp_path, corpus):
    pipeline = _pipeline(tmp_path)
    pipeline.run(corpus, document_ids=corpus.ids[:20])
    records = [
        json.loads(line)
        for line in (tmp_path / "embeddings.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    for record in records:
        assert record["text_sha256"] == text_sha256(corpus.require(record["id"]).text)


def test_reanudacion_no_recalcula(tmp_path, corpus):
    pipeline = _pipeline(tmp_path)
    pipeline.run(corpus, document_ids=corpus.ids[:50])
    second = pipeline.run(corpus, document_ids=corpus.ids[:50])
    assert second.generated == 0
    assert second.reused == 50


def test_no_se_mezclan_modelos(tmp_path, corpus):
    _pipeline(tmp_path, dimension=64).run(corpus, document_ids=corpus.ids[:10])
    otro = EmbeddingPipeline(
        HashingEmbeddingProvider(128),
        tmp_path / "embeddings.jsonl",
        tmp_path / "manifest.json",
    )
    with pytest.raises(EmbeddingModelMismatchError):
        otro.run(corpus, document_ids=corpus.ids[:10])


def test_ids_duplicados_fallan():
    documento = SemanticDocument(id="PRJ-002", entity_type="Project", title="t", text="x")
    with pytest.raises(DuplicateDocumentError):
        SemanticCorpus([documento, documento])


def test_manifiesto_registra_modelo_y_dimension(tmp_path, corpus, settings):
    pipeline = _pipeline(tmp_path)
    pipeline.run(corpus, source_path=settings.semantic_documents_path, document_ids=corpus.ids[:10])
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model"] == HashingEmbeddingProvider.MODEL_NAME
    assert manifest["dimension"] == 64
    assert manifest["normalized"] is True
    assert manifest["source_sha256"]
    assert manifest["generated_at"]


def test_artefacto_no_contiene_texto_ni_secretos(tmp_path, corpus):
    pipeline = _pipeline(tmp_path)
    pipeline.run(corpus, document_ids=corpus.ids[:30])
    contenido = (tmp_path / "embeddings.jsonl").read_text(encoding="utf-8")
    for registro in (json.loads(linea) for linea in contenido.splitlines()):
        assert set(registro) == {"id", "entity_type", "model", "dimension", "text_sha256", "embedding"}
    for prohibido in ("password", "neo4j+s://", "NEO4J_PASSWORD", "AURA"):
        assert prohibido.lower() not in contenido.lower()


def test_store_rechaza_dimension_inconsistente(tmp_path):
    ruta = tmp_path / "roto.jsonl"
    ruta.write_text(
        json.dumps({"id": "A-1", "model": "m", "dimension": 3, "embedding": [1.0, 0.0]}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(EmbeddingStoreError):
        EmbeddingStore.load(ruta)


def test_store_detecta_cobertura_incompleta(tmp_path, corpus):
    pipeline = _pipeline(tmp_path)
    pipeline.run(corpus, document_ids=corpus.ids[:10])
    store = EmbeddingStore.load(tmp_path / "embeddings.jsonl")
    with pytest.raises(EmbeddingStoreError):
        store.validate_coverage(corpus)


def test_store_rechaza_otro_modelo(tmp_path, corpus):
    pipeline = _pipeline(tmp_path)
    pipeline.run(corpus, document_ids=corpus.ids[:10])
    store = EmbeddingStore.load(tmp_path / "embeddings.jsonl")
    with pytest.raises(EmbeddingStoreError):
        store.validate_provider("BAAI/bge-m3", 1024)
