"""Ranking explicable: pesos, desglose, penalizaciones y determinismo."""

from __future__ import annotations

import pytest

from knowledge_nexus_retrieval.engine import SearchRequest
from knowledge_nexus_retrieval.ranking.scorer import COMPONENT_ORDER

from helpers import DEMO_QUERY, engine_with_config

FIXTURE_COMPONENTS = ("semantic", "domain", "method", "graph", "evidence")


@pytest.fixture(scope="module")
def respuesta(offline_engine):
    return offline_engine.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )


def test_los_pesos_suman_uno(offline_engine):
    pesos = offline_engine._ranker.weights  # noqa: SLF001
    assert set(pesos) == set(COMPONENT_ORDER)
    assert round(sum(pesos.values()), 6) == 1.0


def test_desglose_visible_y_consistente(respuesta):
    for conexion in respuesta["connections"]:
        relevancia = conexion["relevance"]
        for componente in FIXTURE_COMPONENTS:
            assert 0.0 <= relevancia[componente] <= 1.0
        esperado = sum(
            relevancia["weights"][nombre] * relevancia[nombre] for nombre in COMPONENT_ORDER
        )
        assert relevancia["base_total"] == pytest.approx(esperado, abs=1e-3)
        assert relevancia["total"] == pytest.approx(
            max(0.0, relevancia["base_total"] - relevancia["penalty_total"]), abs=1e-3
        )
        assert relevancia["ranking_version"]
        assert "relevancia" in relevancia["interpretation"].lower()


def test_orden_descendente_y_explicable(respuesta):
    totales = [item["relevance"]["total"] for item in respuesta["connections"]]
    assert totales == sorted(totales, reverse=True)
    for conexion in respuesta["connections"]:
        assert conexion["explanation"]
        assert conexion["target"]["id"] in conexion["explanation"]
        assert "señal que más aporta" in conexion["explanation"]


def test_cada_componente_expone_su_detalle(respuesta):
    for conexion in respuesta["connections"]:
        detalle = conexion["components_detail"]
        assert set(detalle) == set(COMPONENT_ORDER)
        assert "vector_similarity" in detalle["semantic"]
        assert "calibration" in detalle["semantic"]
        assert "subsignals" in detalle["domain"]
        assert "mode" in detalle["method"]
        assert "degree" in detalle["graph"]
        assert "fields_expected" in detalle["evidence"]


def test_relaciones_calculadas_se_marcan_como_inferidas(respuesta):
    for conexion in respuesta["connections"]:
        assert conexion["relation_origin"] == "INFERRED"
        assert conexion["relation"] in {
            "RELEVANT_ANTECEDENT",
            "SEMANTICALLY_RELATED",
            "METHODOLOGICALLY_COMPATIBLE",
            "COMPLEMENTS",
            "CAN_SUPPORT",
            "CURRICULAR_ALIGNMENT",
            "POTENTIAL_COLLABORATOR",
        }


def test_antecedente_exige_trabajo_terminado(respuesta, offline_engine):
    for conexion in respuesta["connections"]:
        if conexion["relation"] != "RELEVANT_ANTECEDENT":
            continue
        entidad = offline_engine._graph.get_entity(  # noqa: SLF001
            conexion["target"]["type"], conexion["target"]["id"]
        )
        estado = str(entidad["properties"].get("status") or "").upper()
        assert conexion["target"]["type"] == "Publication" or estado in {
            "COMPLETED",
            "APPROVED",
            "PUBLISHED",
            "CLOSED",
            "DEFENDED",
        }


def test_penalizacion_por_evidencia_insuficiente(offline_engine):
    motor = engine_with_config(
        offline_engine, thresholds={"missing_evidence_below": 0.99}
    )
    respuesta = motor.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )
    nombres = {
        penalizacion["name"]
        for conexion in respuesta["connections"]
        for penalizacion in conexion["relevance"]["penalties"]
    }
    assert "missing_evidence" in nombres


def test_los_pesos_cambian_el_orden(offline_engine):
    solo_semantica = engine_with_config(
        offline_engine,
        weights={
            "semantic": 1.0,
            "domain": 0.0,
            "method": 0.0,
            "graph": 0.0,
            "evidence": 0.0,
            "actionable": 0.0,
        },
    )
    base = offline_engine.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )
    variante = solo_semantica.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )
    assert [item["target"]["id"] for item in base["connections"]] != [
        item["target"]["id"] for item in variante["connections"]
    ]


def test_resultado_determinista(offline_engine):
    primera = offline_engine.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )
    segunda = offline_engine.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )
    assert [item["target"]["id"] for item in primera["connections"]] == [
        item["target"]["id"] for item in segunda["connections"]
    ]
    assert [item["relevance"]["total"] for item in primera["connections"]] == [
        item["relevance"]["total"] for item in segunda["connections"]
    ]


def test_diversificacion_por_tipo(offline_engine):
    respuesta = offline_engine.search(
        SearchRequest(
            query=DEMO_QUERY,
            source_entity_id="NEED-001",
            target_types=["Project", "Thesis", "Researcher", "Capability", "Subject"],
            limit=6,
        )
    )
    tipos = [item["target"]["type"] for item in respuesta["connections"]]
    assert len(set(tipos)) >= 3
    assert max(tipos.count(tipo) for tipo in set(tipos)) <= 2
