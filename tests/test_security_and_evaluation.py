"""Ausencia de secretos y métricas reproducibles del conjunto de revisión."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from knowledge_nexus_retrieval.evaluation.harness import EvaluationHarness

# Se exige un host después del esquema para no marcar los propios patrones.
PATRONES_PROHIBIDOS = (
    re.compile(r"neo4j\+s?://[A-Za-z0-9]", re.IGNORECASE),
    re.compile(r"bolt://[A-Za-z0-9]", re.IGNORECASE),
    re.compile(r"NEO4J_PASSWORD\s*[:=]\s*\S+"),
    re.compile(r"password\s*[:=]\s*['\"][^'\"]{3,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
)

EXTENSIONES = (".py", ".yaml", ".yml", ".md", ".toml", ".txt", ".json")
EXCLUIDOS = {".venv", "artifacts", "__pycache__", ".git", ".pytest_cache"}


def _archivos(raiz: Path):
    for ruta in raiz.rglob("*"):
        if not ruta.is_file() or ruta.suffix not in EXTENSIONES:
            continue
        if any(parte in EXCLUIDOS for parte in ruta.parts):
            continue
        yield ruta


def test_no_hay_secretos_en_el_repositorio(settings):
    hallazgos: list[str] = []
    for ruta in _archivos(settings.project_root):
        contenido = ruta.read_text(encoding="utf-8", errors="ignore")
        for patron in PATRONES_PROHIBIDOS:
            for coincidencia in patron.finditer(contenido):
                hallazgos.append(f"{ruta.name}: {coincidencia.group(0)[:40]}")
    assert not hallazgos, hallazgos


def test_no_se_versiona_un_archivo_env(settings):
    assert not (settings.project_root / ".env").exists()


def test_el_artefacto_de_embeddings_no_expone_texto_fuente(settings):
    ruta = settings.embeddings_path
    if not ruta.is_file():
        pytest.skip("Sin artefacto de embeddings")
    with ruta.open("r", encoding="utf-8") as handle:
        primera = handle.readline()
    assert "student attrition" not in primera
    assert "embedding" in primera


def test_la_respuesta_no_filtra_configuracion_sensible(offline_engine):
    salud = str(offline_engine.health()).lower()
    for prohibido in ("password", "neo4j+s://", "bolt://", "secret", "token"):
        assert prohibido not in salud


def test_metricas_estructurales_del_conjunto_de_revision(offline_engine, settings):
    casos = settings.project_root / "artifacts" / "evaluation" / "manual_review_set.json"
    reporte = EvaluationHarness(offline_engine).run(cases_path=casos, limit=5)
    assert reporte["summary"]["cases"] == 10
    assert reporte["summary"]["evidence_coverage"] == 1.0
    assert reporte["summary"]["full_traceability"] == 1.0
    assert reporte["summary"]["opportunities_only_existing_ids"] is True
    assert "Gold Standard" in reporte["disclaimer"]
    assert reporte["metric_notes"]["precision_at_k"]


def test_calidad_minima_con_el_modelo_real(real_engine):
    reporte = EvaluationHarness(real_engine).run(limit=5)
    resumen = reporte["summary"]
    assert resumen["negative_violations"] == 0, "un caso trajo una entidad de otro dominio"
    assert resumen["precision_at_k_labeled_types"] >= 0.5, resumen
    assert resumen["evidence_coverage"] == 1.0
    assert resumen["opportunities_only_existing_ids"] is True
