"""Evidencia verificable y oportunidades que solo usan entidades existentes."""

from __future__ import annotations

import pytest

from knowledge_nexus_retrieval.data.graph_port import entity_fields
from knowledge_nexus_retrieval.engine import SearchRequest
from knowledge_nexus_retrieval.evidence.assembler import IdentifierGuard
from knowledge_nexus_retrieval.llm.provider import GuardedNarrator
from knowledge_nexus_retrieval.opportunities.generator import VALID_TYPES

from helpers import DEMO_QUERY

CAMPOS_OBLIGATORIOS = ("file", "row", "record_id", "field", "excerpt")


@pytest.fixture(scope="module")
def respuesta(offline_engine):
    return offline_engine.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )


def test_toda_conexion_mostrada_tiene_evidencia(respuesta):
    assert respuesta["connections"]
    for conexion in respuesta["connections"]:
        assert conexion["evidence"], conexion["target"]["id"]
        for elemento in conexion["evidence"]:
            for campo in CAMPOS_OBLIGATORIOS:
                assert elemento.get(campo) not in (None, ""), (campo, elemento)


def test_la_evidencia_apunta_al_registro_correcto(respuesta, offline_engine):
    for conexion in respuesta["connections"]:
        entidad = offline_engine._graph.get_entity(  # noqa: SLF001
            conexion["target"]["type"], conexion["target"]["id"]
        )
        for elemento in conexion["evidence"]:
            if elemento["origin"] != "entity_field":
                continue
            assert elemento["record_id"] == conexion["target"]["id"]
            assert elemento["file"] == entidad["source"]["file"]
            assert elemento["row"] == entidad["source"]["row"]
            assert elemento["field"] in entity_fields(entidad)


def test_el_fragmento_procede_del_campo_citado(respuesta, offline_engine):
    for conexion in respuesta["connections"]:
        entidad = offline_engine._graph.get_entity(  # noqa: SLF001
            conexion["target"]["type"], conexion["target"]["id"]
        )
        for elemento in conexion["evidence"]:
            if elemento["origin"] != "entity_field":
                continue
            valor = entity_fields(entidad)[elemento["field"]]
            texto = "; ".join(str(item) for item in valor) if isinstance(valor, list) else str(valor)
            recorte = elemento["excerpt"].rstrip("…")
            assert recorte[:60] in " ".join(texto.split())


def test_prj_002_cita_los_campos_de_su_fila_real(real_engine):
    respuesta = real_engine.search(
        SearchRequest(query=DEMO_QUERY, source_entity_id="NEED-001", limit=5)
    )
    conexion = next(
        item for item in respuesta["connections"] if item["target"]["id"] == "PRJ-002"
    )
    archivos = {elemento["file"] for elemento in conexion["evidence"]}
    filas = {elemento["row"] for elemento in conexion["evidence"]}
    assert archivos == {"projects.csv"}
    assert filas == {3}


def test_oportunidades_validas_y_trazables(respuesta):
    assert respuesta["opportunities"]
    conocidos = {item["target"]["id"] for item in respuesta["connections"]}
    conocidos.add(respuesta["query_entity"]["id"])
    for oportunidad in respuesta["opportunities"]:
        assert oportunidad["type"] in VALID_TYPES
        assert oportunidad["related_entities"]
        assert oportunidad["uncertainty"]
        assert oportunidad["relation_origin"] == "INFERRED"
        assert "no representa una decisión" in oportunidad["disclaimer"]
        for entidad in oportunidad["related_entities"]:
            assert entidad["id"] in conocidos, entidad


def test_la_oportunidad_responde_a_una_necesidad(respuesta):
    for oportunidad in respuesta["opportunities"]:
        assert "NEED-001" in {item["id"] for item in oportunidad["related_entities"]}
        assert "NEED-001" in oportunidad["reason"]


def test_se_rechaza_una_oportunidad_con_id_inexistente(offline_engine):
    guard = IdentifierGuard({"NEED-001", "PRJ-002"})
    with pytest.raises(ValueError, match="IDs que no están"):
        guard.validate(["NEED-001", "PRJ-999"], "oportunidad de prueba")


def test_el_narrador_descarta_textos_con_ids_inventados():
    class NarradorInventor:
        name = "prueba"

        def rewrite(self, deterministic_text, facts):
            return "El proyecto PRJ-999 respalda esta conexión."

    guard = IdentifierGuard({"PRJ-002"})
    narrador = GuardedNarrator(NarradorInventor(), guard)
    texto = narrador.rewrite("Texto determinista original.", {})
    assert texto == "Texto determinista original."
    assert narrador.rejections and "PRJ-999" in narrador.rejections[0]


def test_el_narrador_acepta_texto_sin_ids_nuevos():
    class NarradorFiel:
        name = "prueba"

        def rewrite(self, deterministic_text, facts):
            return "PRJ-002 aporta antecedentes verificables."

    narrador = GuardedNarrator(NarradorFiel(), IdentifierGuard({"PRJ-002"}))
    assert narrador.rewrite("original", {}) == "PRJ-002 aporta antecedentes verificables."
    assert narrador.rejections == []


def test_el_subgrafo_solo_usa_entidades_recuperadas(respuesta):
    grafo = respuesta["graph"]
    identificadores = {nodo["id"] for nodo in grafo["nodes"]}
    assert len(identificadores) <= 20
    for arista in grafo["edges"]:
        assert arista["source_id"] in identificadores
        assert arista["target_id"] in identificadores
        assert arista["relation_origin"] in {"EXPLICIT", "INFERRED"}
