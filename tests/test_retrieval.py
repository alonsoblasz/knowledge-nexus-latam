"""Recuperación híbrida: deduplicación, canales, caso de demostración y vacío."""

from __future__ import annotations

import pytest

from knowledge_nexus_retrieval.engine import SearchRequest
from knowledge_nexus_retrieval.retrieval.hybrid import (
    GRAPH_CHANNEL,
    LEXICAL_CHANNEL,
    VECTOR_CHANNEL,
)

from helpers import DEMO_QUERY, engine_with_config


def _retrieve(engine, query=DEMO_QUERY, source="NEED-001", types=None):
    context = engine._builder.build(query, source, types)  # noqa: SLF001
    return engine._retriever.retrieve(context)  # noqa: SLF001


def test_candidatos_deduplicados_por_id(offline_engine):
    resultado = _retrieve(offline_engine)
    identificadores = [candidate.id for candidate in resultado.candidates]
    assert len(identificadores) == len(set(identificadores))


def test_los_tres_canales_aportan_candidatos(offline_engine):
    resultado = _retrieve(offline_engine)
    canales = resultado.diagnostics["by_channel"]
    assert canales[VECTOR_CHANNEL] > 0
    assert canales[LEXICAL_CHANNEL] > 0
    assert canales[GRAPH_CHANNEL] > 0


def test_solo_se_recuperan_los_tipos_pedidos(offline_engine):
    resultado = _retrieve(offline_engine, types=["Project"])
    assert {candidate.entity_type for candidate in resultado.candidates} == {"Project"}


def test_expansion_conserva_el_camino_explicito(offline_engine):
    resultado = _retrieve(offline_engine)
    expandidos = [item for item in resultado.candidates if item.graph_hops is not None]
    assert expandidos
    for candidato in expandidos[:5]:
        assert candidato.graph_path
        assert all(step["relation_origin"] == "EXPLICIT" for step in candidato.graph_path)


def test_prj_002_en_el_top_5_con_modelo_real(real_engine):
    """Criterio de aceptación del equipo para la consulta de deserción."""

    respuesta = real_engine.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )
    recuperados = [item["target"]["id"] for item in respuesta["connections"]]
    assert "PRJ-002" in recuperados, recuperados


def test_prj_002_sin_expansion_lexica(real_engine):
    """El puente multilingüe lo aporta el modelo, no el léxico auxiliar.

    Con la expansión desactivada, PRJ-002 sigue entre los cinco proyectos mejor
    rankeados: el léxico solo reordena proyectos igualmente pertinentes
    (PRJ-001, PRJ-004 y PRJ-006 repiten literalmente las palabras de la
    necesidad), no es lo que descubre la equivalencia deserción/attrition.
    """

    motor = engine_with_config(real_engine, retrieval={"use_lexicon_expansion": False})
    respuesta = motor.search(
        SearchRequest(
            query=DEMO_QUERY,
            source_entity_id="NEED-001",
            target_types=["Project"],
            limit=5,
        )
    )
    recuperados = [item["target"]["id"] for item in respuesta["connections"]]
    assert "PRJ-002" in recuperados, recuperados
    assert respuesta["query"]["lexicon_expansion"] is False


def test_conexion_no_literal_encontrada(real_engine):
    """La consulta habla de «deserción» y el registro de «student attrition»."""

    respuesta = real_engine.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )
    objetivo = next(
        item for item in respuesta["connections"] if item["target"]["id"] == "PRJ-002"
    )
    assert "attrition" in objetivo["target"]["title"].lower()
    assert "deserción" not in objetivo["target"]["title"].lower()
    assert objetivo["relevance"]["semantic"] > 0.0


def test_consulta_sin_resultados_devuelve_respuesta_valida(offline_engine):
    motor = engine_with_config(offline_engine, retrieval={"min_total_score": 0.999})
    respuesta = motor.search(
        SearchRequest(query="receta de pan de masa madre del siglo XV", limit=5)
    )
    assert respuesta["connections"] == []
    assert respuesta["opportunities"] == []
    assert respuesta["meta"]["empty_result"] is True
    assert respuesta["meta"]["reason"]
    assert respuesta["contract_version"] == "1.0"
    assert respuesta["query_entity"]["id"] is None


def test_entidad_de_origen_inexistente(offline_engine):
    with pytest.raises(LookupError):
        offline_engine.search(SearchRequest(query="x", source_entity_id="NEED-999"))


def test_consulta_vacia_sin_origen(offline_engine):
    with pytest.raises(ValueError):
        offline_engine.search(SearchRequest(query="   "))
