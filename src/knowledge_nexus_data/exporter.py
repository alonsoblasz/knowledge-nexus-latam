"""Exporta contratos estables para los frentes de búsqueda e interfaz."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .graph_builder import GraphDatasetBuilder, select_fixture
from .models import GraphEdge, GraphNode
from .repository import DatasetRepository
from .validator import ValidationReport


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")


def export_contracts(
    repository: DatasetRepository,
    report: ValidationReport,
    output_directory: Path,
) -> dict[str, Any]:
    builder = GraphDatasetBuilder(repository)
    nodes = builder.build_nodes()
    edges = builder.build_edges()

    output_directory.mkdir(parents=True, exist_ok=True)
    write_json(output_directory / "data_quality_report.json", report.to_dict())
    write_jsonl(output_directory / "graph_nodes.jsonl", [node.to_dict() for node in nodes])
    write_jsonl(output_directory / "graph_edges.jsonl", [edge.to_dict() for edge in edges])
    write_jsonl(
        output_directory / "semantic_documents.jsonl",
        [semantic_contract(node) for node in nodes if node.semantic_text],
    )

    fixture_nodes, fixture_edges = select_fixture(
        nodes,
        edges,
        {"NEED-001", "PRJ-002", "THS-002", "INV-112", "CAP-002", "SUB-083"},
        hops=1,
    )
    write_json(
        output_directory / "team_fixture_graph.json",
        {
            "description": "Subgrafo real para desarrollo paralelo; no representa ranking oficial.",
            "nodes": [node.to_dict() for node in fixture_nodes],
            "edges": [edge.to_dict() for edge in fixture_edges],
        },
    )
    write_json(
        output_directory / "team_fixture_search_response.json",
        build_search_fixture(nodes),
    )

    manifest = {
        "dataset_root": str(repository.data_root),
        "validation_valid": report.valid,
        "nodes": len(nodes),
        "edges": len(edges),
        "semantic_documents": sum(1 for node in nodes if node.semantic_text),
        "nodes_by_label": dict(sorted(Counter(node.label for node in nodes).items())),
        "edges_by_type": dict(sorted(Counter(edge.relationship for edge in edges).items())),
        "files": {
            "nodes": "graph_nodes.jsonl",
            "edges": "graph_edges.jsonl",
            "semantic_documents": "semantic_documents.jsonl",
            "quality_report": "data_quality_report.json",
            "team_fixture_graph": "team_fixture_graph.json",
            "team_fixture_search_response": "team_fixture_search_response.json",
        },
    }
    write_json(output_directory / "manifest.json", manifest)
    return manifest


def semantic_contract(node: GraphNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "entity_type": node.label,
        "title": node.title,
        "text": node.semantic_text,
        "source": {
            "file": node.source_file,
            "row": node.source_row,
            "path": node.properties.get("source_path"),
        },
        "metadata": {
            key: node.properties.get(key)
            for key in (
                "status",
                "active",
                "priority",
                "disciplinary_area",
                "application_context",
                "application_domains",
                "methodology",
                "keywords",
                "faculty_id",
                "program_id",
                "group_id",
            )
            if key in node.properties
        },
    }


def build_search_fixture(nodes: list[GraphNode]) -> dict[str, Any]:
    by_id = {node.id: node for node in nodes}
    need = by_id["NEED-001"]
    project = by_id["PRJ-002"]
    researcher = by_id["INV-112"]
    capability = by_id["CAP-002"]
    subject = by_id["SUB-083"]
    return {
        "contract_version": "1.0",
        "fixture_only": True,
        "warning": "Scores ilustrativos para desarrollar la interfaz; no son salida de un modelo.",
        "query_entity": {
            "id": need.id,
            "type": need.label,
            "title": need.title,
        },
        "connections": [
            {
                "connection_id": "FIXTURE-CONN-001",
                "source": {"id": need.id, "type": need.label, "title": need.title},
                "target": {
                    "id": project.id,
                    "type": project.label,
                    "title": project.title,
                },
                "relation": "RELEVANT_ANTECEDENT",
                "relation_origin": "INFERRED_FIXTURE",
                "relevance": {
                    "total": 0.88,
                    "semantic": 0.92,
                    "domain": 0.90,
                    "method": 0.75,
                    "graph": 0.80,
                    "evidence": 0.95,
                },
                "explanation": (
                    "El proyecto estudia riesgo académico y student attrition mediante "
                    "analítica educativa, por lo que constituye un antecedente potencial."
                ),
                "evidence": [
                    {
                        "file": project.source_file,
                        "row": project.source_row,
                        "record_id": project.id,
                        "field": "problem_statement",
                        "excerpt": project.properties.get("problem_statement"),
                    },
                    {
                        "file": project.source_file,
                        "row": project.source_row,
                        "record_id": project.id,
                        "field": "methodology",
                        "excerpt": project.properties.get("methodology"),
                    },
                ],
            }
        ],
        "opportunities": [
            {
                "opportunity_id": "FIXTURE-OPP-001",
                "type": "RESEARCH_CONTINUITY",
                "title": "Sistema explicable de alerta temprana de riesgo académico",
                "reason": (
                    "Continuar antecedentes institucionales y articular experiencia, capacidad "
                    "computacional y formación existente."
                ),
                "priority": "HIGH",
                "related_entities": [
                    {"id": need.id, "type": need.label, "title": need.title},
                    {"id": project.id, "type": project.label, "title": project.title},
                    {
                        "id": researcher.id,
                        "type": researcher.label,
                        "title": researcher.title,
                    },
                    {
                        "id": capability.id,
                        "type": capability.label,
                        "title": capability.title,
                    },
                    {"id": subject.id, "type": subject.label, "title": subject.title},
                ],
            }
        ],
    }

