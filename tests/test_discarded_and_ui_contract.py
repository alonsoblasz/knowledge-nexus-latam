"""Explicación de los descartados y contrato que consume la interfaz."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_nexus_retrieval.engine import SearchRequest

from helpers import DEMO_QUERY

UI_APP = Path(__file__).resolve().parents[1] / "ui" / "app.py"


@pytest.fixture(scope="module")
def respuesta(offline_engine):
    return offline_engine.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )


def test_se_explica_por_que_una_conexion_no_aparece(respuesta):
    descartados = respuesta["discarded"]
    assert descartados, "debe informarse al menos un candidato descartado"
    mostrados = {item["target"]["id"] for item in respuesta["connections"]}
    for item in descartados:
        assert item["id"] not in mostrados
        assert item["reason"], item
        assert item["kind"] in {"quedo_cerca", "descartado_claramente"}
        assert set(item["relevance"]) == {
            "semantic",
            "domain",
            "method",
            "graph",
            "evidence",
            "actionable",
        }


def test_el_descartado_claro_puntua_menos_que_los_mostrados(respuesta):
    claros = [item for item in respuesta["discarded"] if item["kind"] == "descartado_claramente"]
    assert claros, "se espera un ejemplo del extremo bajo del ranking"
    peor = claros[0]["total"]
    minimo_mostrado = min(item["relevance"]["total"] for item in respuesta["connections"])
    assert peor < minimo_mostrado


def test_se_pueden_desactivar_los_descartados(offline_engine):
    respuesta = offline_engine.search(
        SearchRequest(
            query=DEMO_QUERY, source_entity_id="NEED-001", limit=5, include_discarded=False
        )
    )
    assert "discarded" not in respuesta


def test_la_interfaz_solo_usa_claves_que_la_api_devuelve(respuesta):
    """Guarda contra el error que ya ocurrió: una UI atada a un contrato inventado."""

    codigo = UI_APP.read_text(encoding="utf-8")
    for clave in ("connections", "query_entity", "opportunities", "discarded", "graph", "meta"):
        assert f'"{clave}"' in codigo, f"la interfaz debería leer {clave}"
    # Claves del contrato antiguo que ya no deben aparecer.
    for obsoleta in ('"results"', '"source_entity"', '"priority_score"', '"nature"'):
        assert obsoleta not in codigo, f"la interfaz aún usa la clave obsoleta {obsoleta}"


def test_la_interfaz_no_contiene_credenciales():
    codigo = UI_APP.read_text(encoding="utf-8")
    for prohibido in ("NEO4J_PASSWORD", "NEO4J_URI", "password"):
        assert prohibido not in codigo


def test_la_interfaz_puede_leer_el_fixture(settings):
    """El modo `fixture` debe seguir funcionando sin el motor levantado."""

    fixture = json.loads(
        (settings.data_dir / "team_fixture_search_response.json").read_text(encoding="utf-8")
    )
    assert fixture["connections"][0]["target"]["id"] == "PRJ-002"
    assert fixture["fixture_only"] is True
    grafo = json.loads(
        (settings.data_dir / "team_fixture_graph.json").read_text(encoding="utf-8")
    )
    assert grafo["nodes"] and grafo["edges"]


def test_la_respuesta_declara_su_nivel_de_confianza(respuesta):
    confianza = respuesta["confidence"]
    assert confianza["level"] in {"alta", "media", "baja", "sin_resultados"}
    assert confianza["message"]


def test_una_consulta_sin_respuesta_se_marca_como_poco_fiable(offline_engine):
    respuesta = offline_engine.search(
        SearchRequest(query="recetas de cocina medieval italiana con fermentación", limit=5)
    )
    assert respuesta["confidence"]["level"] == "baja"
    assert "no responde" in respuesta["confidence"]["message"].lower() or (
        "coincidencias más cercanas" in respuesta["confidence"]["message"]
    )
