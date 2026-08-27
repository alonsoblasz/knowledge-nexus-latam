"""La API debe poder sustituir al fixture cambiando solo la URL del servicio."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from knowledge_nexus_retrieval.api.main import create_app

from helpers import DEMO_QUERY


@pytest.fixture(scope="module")
def client(offline_engine) -> TestClient:
    return TestClient(create_app(offline_engine))


@pytest.fixture(scope="module")
def busqueda(client) -> dict:
    respuesta = client.post(
        "/v1/search",
        json={
            "query": DEMO_QUERY,
            "source_entity_id": "NEED-001",
            "target_types": ["Project", "Thesis", "Researcher", "Capability", "Subject"],
            "limit": 5,
        },
    )
    assert respuesta.status_code == 200
    return respuesta.json()


def _claves_presentes(esperado, real, ruta=""):
    """Toda clave del fixture debe existir en la respuesta real."""

    if isinstance(esperado, dict):
        assert isinstance(real, dict), ruta
        for clave, valor in esperado.items():
            assert clave in real, f"falta {ruta}.{clave}"
            _claves_presentes(valor, real[clave], f"{ruta}.{clave}")
    elif isinstance(esperado, list) and esperado:
        assert isinstance(real, list) and real, ruta
        _claves_presentes(esperado[0], real[0], f"{ruta}[0]")


def test_la_respuesta_conserva_la_forma_del_fixture(busqueda, fixture_contract):
    _claves_presentes(fixture_contract, busqueda)
    assert busqueda["contract_version"] == fixture_contract["contract_version"]
    assert busqueda["fixture_only"] is False


def test_los_tipos_coinciden_con_el_fixture(busqueda, fixture_contract):
    conexion_fixture = fixture_contract["connections"][0]
    conexion = busqueda["connections"][0]
    assert isinstance(conexion["connection_id"], str)
    assert set(conexion["source"]) >= set(conexion_fixture["source"])
    assert set(conexion["target"]) >= set(conexion_fixture["target"])
    assert set(conexion["relevance"]) >= set(conexion_fixture["relevance"])
    assert set(conexion["evidence"][0]) >= set(conexion_fixture["evidence"][0])
    oportunidad_fixture = fixture_contract["opportunities"][0]
    oportunidad = busqueda["opportunities"][0]
    assert set(oportunidad) >= set(oportunidad_fixture)
    assert set(oportunidad["related_entities"][0]) >= set(
        oportunidad_fixture["related_entities"][0]
    )


def test_el_aviso_distingue_datos_reales_de_simulados(busqueda):
    assert "relevancia" in busqueda["warning"].lower()
    assert "no son" in busqueda["warning"].lower()
    assert busqueda["meta"]["ranking_version"]
    assert busqueda["meta"]["embedding_model"]


def test_health_expone_modelo_y_version(client):
    payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["embedding_dimension"] > 0
    assert payload["documents_indexed"] == 3292
    assert payload["contract_version"] == "1.0"
    assert "password" not in str(payload).lower()


def test_endpoint_de_oportunidades(client):
    respuesta = client.post(
        "/v1/opportunities",
        json={"query": DEMO_QUERY, "source_entity_id": "NEED-001", "max_opportunities": 2},
    )
    assert respuesta.status_code == 200
    payload = respuesta.json()
    assert payload["opportunities"]
    assert len(payload["opportunities"]) <= 2
    assert payload["supporting_connections"]


def test_endpoint_de_entidad(client):
    respuesta = client.get("/v1/entities/Project/PRJ-002")
    assert respuesta.status_code == 200
    payload = respuesta.json()
    assert payload["entity"]["id"] == "PRJ-002"
    assert payload["neighbors"]
    assert payload["evidence"]["source"]["file"] == "projects.csv"


def test_entidad_inexistente_devuelve_404(client):
    assert client.get("/v1/entities/Project/PRJ-999").status_code == 404


def test_tipo_no_permitido_devuelve_422(client):
    assert client.get("/v1/entities/Secreto/PRJ-002").status_code == 422
    respuesta = client.post("/v1/search", json={"query": "x", "target_types": ["Secreto"]})
    assert respuesta.status_code == 422


def test_origen_inexistente_devuelve_404(client):
    respuesta = client.post("/v1/search", json={"query": "x", "source_entity_id": "NEED-999"})
    assert respuesta.status_code == 404


def test_solicitud_sin_consulta_ni_origen_es_invalida(client):
    assert client.post("/v1/search", json={}).status_code == 422
    assert client.post("/v1/search", json={"query": "  "}).status_code == 422


def test_campos_desconocidos_se_rechazan(client):
    respuesta = client.post("/v1/search", json={"query": "x", "cypher": "MATCH (n) DETACH DELETE n"})
    assert respuesta.status_code == 422


def test_listado_de_necesidades(client):
    payload = client.get("/v1/needs?limit=5").json()
    assert len(payload["needs"]) == 5
    assert payload["needs"][0]["id"] == "NEED-001"
