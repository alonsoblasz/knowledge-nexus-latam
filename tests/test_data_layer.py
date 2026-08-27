"""El grafo local debe respetar el mismo contrato que el repositorio de Aura."""

from __future__ import annotations

import inspect

import pytest

from knowledge_nexus_data.graph_repository import GraphRepository
from knowledge_nexus_retrieval.data.graph_port import GraphNavigator
from knowledge_nexus_retrieval.data.jsonl_graph import JsonlGraphRepository


CONTRACT_METHODS = ("get_entity", "get_neighbors", "get_evidence", "find_related_entities")


@pytest.fixture(scope="module")
def graph(settings) -> JsonlGraphRepository:
    return JsonlGraphRepository.from_jsonl(settings.graph_nodes_path, settings.graph_edges_path)


def test_misma_firma_que_el_repositorio_de_neo4j():
    for name in CONTRACT_METHODS:
        local = inspect.signature(getattr(JsonlGraphRepository, name))
        remoto = inspect.signature(getattr(GraphRepository, name))
        assert list(local.parameters) == list(remoto.parameters), name


def test_entidad_incluye_procedencia(graph):
    entidad = graph.get_entity("Project", "PRJ-002")
    assert entidad is not None
    assert entidad["source"] == {
        "file": "projects.csv",
        "row": 3,
        "path": "03_knowledge_needs/projects.csv",
    }
    assert entidad["properties"]["status"] == "COMPLETED"


def test_tipo_incorrecto_no_devuelve_entidad(graph):
    assert graph.get_entity("Thesis", "PRJ-002") is None
    assert graph.get_entity("Project", "PRJ-999") is None


def test_vecinos_y_evidencia_de_relaciones(graph):
    vecinos = graph.get_neighbors("PRJ-002", ["EXECUTED_BY_GROUP"])
    assert vecinos and all(item["relationship"] == "EXECUTED_BY_GROUP" for item in vecinos)
    assert all(item["relation_origin"] == "EXPLICIT" for item in vecinos)

    evidencia = graph.get_evidence("PRJ-002")
    assert evidencia["entity_id"] == "PRJ-002"
    assert evidencia["documents"], "el proyecto debe tener documento asociado"
    assert evidencia["relation_evidence"], "las relaciones deben traer procedencia"


def test_relacionadas_prefieren_un_salto(graph):
    relacionadas = graph.find_related_entities("PRJ-002", "Researcher")
    assert relacionadas
    assert {item["hops"] for item in relacionadas} == {1}
    assert "INV-112" in {item["target"]["id"] for item in relacionadas}


def test_relacionadas_usan_dos_saltos_si_no_hay_directas(graph):
    relacionadas = graph.find_related_entities("NEED-001", "Project")
    assert relacionadas == [], "NEED-001 no tiene camino explícito hacia proyectos"


def test_navegador_calcula_distancias_y_grado(graph):
    navegador = GraphNavigator(graph)
    assert navegador.distance("PRJ-002", "FAC-004") == 1
    assert navegador.distance("NEED-001", "PRJ-002") is None
    assert navegador.degree("PRJ-002") == len(graph.get_neighbors("PRJ-002"))


def test_relaciones_invalidas_se_rechazan(graph):
    with pytest.raises(TypeError):
        graph.get_neighbors("PRJ-002", "EXECUTED_BY_GROUP")
    with pytest.raises(ValueError):
        graph.get_neighbors("PRJ-002", ["drop database"])
    with pytest.raises(ValueError):
        graph.get_entity("Project", "   ")
