"""Transforma Data V1.0 en contratos canónicos de nodos y aristas."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .catalog import (
    DOCUMENT_ENTITY_KEYS,
    FOREIGN_KEYS,
    NODE_SPEC_BY_KEY,
    NODE_SPECS,
    RELATION_FILE_SPECS,
)
from .models import GraphEdge, GraphNode
from .repository import DatasetRepository, normalize_value
from .semantic import build_semantic_text


class GraphDatasetBuilder:
    def __init__(self, repository: DatasetRepository):
        self.repository = repository

    def build_nodes(self) -> list[GraphNode]:
        nodes: list[GraphNode] = []
        for spec in NODE_SPECS:
            for row_number, row in enumerate(self.repository.read_nodes(spec), start=2):
                identifier = row[spec.id_field].strip()
                properties = self.repository.normalized_properties(row)
                properties["entity_type"] = spec.label
                properties["source_file"] = Path(spec.relative_path).name
                properties["source_path"] = spec.relative_path
                properties["source_row"] = row_number
                title = row.get(spec.title_field, "").strip() or identifier
                semantic_text = build_semantic_text(spec, row) if spec.semantic else None
                nodes.append(
                    GraphNode(
                        id=identifier,
                        label=spec.label,
                        title=title,
                        properties=properties,
                        source_file=Path(spec.relative_path).name,
                        source_row=row_number,
                        semantic_text=semantic_text,
                    )
                )
        nodes.extend(self._build_document_nodes())
        return nodes

    def build_edges(self) -> list[GraphEdge]:
        edges: dict[tuple[str, str, str], GraphEdge] = {}
        self._add_direct_foreign_keys(edges)
        self._add_relation_files(edges)
        self._add_document_relations(edges)
        return sorted(edges.values(), key=lambda edge: edge.key)

    def _build_document_nodes(self) -> list[GraphNode]:
        result: list[GraphNode] = []
        catalog_path = "03_knowledge_needs/document_catalog.csv"
        for row_number, row in enumerate(self.repository.read_csv(catalog_path), start=2):
            file_name = row["file_name"].strip()
            relative_path = f"03_knowledge_needs/documents/{file_name}"
            content = self.repository.path(relative_path).read_text(encoding="utf-8")
            document_id = f"DOC::{file_name}"
            properties = {
                "document_id": document_id,
                "file_name": file_name,
                "entity_type_described": row["entity_type"].strip(),
                "entity_id_described": row["entity_id"].strip(),
                "content": content,
                "source_file": file_name,
                "source_path": relative_path,
                "source_row": 1,
                "entity_type": "Document",
            }
            result.append(
                GraphNode(
                    id=document_id,
                    label="Document",
                    title=file_name,
                    properties=properties,
                    source_file=file_name,
                    source_row=1,
                    semantic_text=content,
                )
            )
        return result

    def _add_direct_foreign_keys(
        self, edges: dict[tuple[str, str, str], GraphEdge]
    ) -> None:
        for relation in FOREIGN_KEYS:
            source_spec = NODE_SPEC_BY_KEY[relation.source_key]
            target_spec = NODE_SPEC_BY_KEY[relation.target_key]
            for row_number, row in enumerate(self.repository.read_nodes(source_spec), start=2):
                own_id = row[source_spec.id_field].strip()
                foreign_id = row.get(relation.source_field, "").strip()
                if not foreign_id:
                    continue
                source_id, source_label = own_id, source_spec.label
                target_id, target_label = foreign_id, target_spec.label
                if relation.reverse:
                    source_id, target_id = target_id, source_id
                    source_label, target_label = target_label, source_label
                edge = GraphEdge(
                    source_id=source_id,
                    source_label=source_label,
                    relationship=relation.relationship,
                    target_id=target_id,
                    target_label=target_label,
                    provenance=[
                        {
                            "file": source_spec.relative_path,
                            "row": row_number,
                            "field": relation.source_field,
                        }
                    ],
                )
                self._merge_edge(edges, edge)

    def _add_relation_files(self, edges: dict[tuple[str, str, str], GraphEdge]) -> None:
        for relation in RELATION_FILE_SPECS:
            source_spec = NODE_SPEC_BY_KEY[relation.source_key]
            target_spec = NODE_SPEC_BY_KEY[relation.target_key]
            for row_number, row in enumerate(
                self.repository.read_csv(relation.relative_path), start=2
            ):
                properties = {
                    field: normalized
                    for field in relation.property_fields
                    if (normalized := normalize_value(field, row.get(field))) is not None
                }
                edge = GraphEdge(
                    source_id=row[relation.source_field].strip(),
                    source_label=source_spec.label,
                    relationship=relation.relationship,
                    target_id=row[relation.target_field].strip(),
                    target_label=target_spec.label,
                    properties=properties,
                    provenance=[
                        {
                            "file": relation.relative_path,
                            "row": row_number,
                            "fields": [relation.source_field, relation.target_field],
                        }
                    ],
                )
                self._merge_edge(edges, edge)

    def _add_document_relations(self, edges: dict[tuple[str, str, str], GraphEdge]) -> None:
        catalog_path = "03_knowledge_needs/document_catalog.csv"
        for row_number, row in enumerate(self.repository.read_csv(catalog_path), start=2):
            entity_key = DOCUMENT_ENTITY_KEYS[row["entity_type"].strip()]
            entity_spec = NODE_SPEC_BY_KEY[entity_key]
            file_name = row["file_name"].strip()
            edge = GraphEdge(
                source_id=f"DOC::{file_name}",
                source_label="Document",
                relationship="DESCRIBES",
                target_id=row["entity_id"].strip(),
                target_label=entity_spec.label,
                provenance=[
                    {
                        "file": catalog_path,
                        "row": row_number,
                        "fields": ["file_name", "entity_id"],
                    }
                ],
            )
            self._merge_edge(edges, edge)

    @staticmethod
    def _merge_edge(
        edges: dict[tuple[str, str, str], GraphEdge], incoming: GraphEdge
    ) -> None:
        existing = edges.get(incoming.key)
        if existing is None:
            edges[incoming.key] = incoming
            return
        existing.properties.update(incoming.properties)
        for provenance in incoming.provenance:
            if provenance not in existing.provenance:
                existing.provenance.append(provenance)


def select_fixture(
    nodes: Iterable[GraphNode],
    edges: Iterable[GraphEdge],
    seed_ids: set[str],
    hops: int = 1,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Extrae un subgrafo real pequeño para que otros frentes trabajen con mocks fiables."""

    node_by_id = {node.id: node for node in nodes}
    all_edges = list(edges)
    selected_ids = set(seed_ids)
    for _ in range(hops):
        expanded = set(selected_ids)
        for edge in all_edges:
            if edge.source_id in selected_ids or edge.target_id in selected_ids:
                expanded.add(edge.source_id)
                expanded.add(edge.target_id)
        selected_ids = expanded
    selected_nodes = [node_by_id[node_id] for node_id in sorted(selected_ids) if node_id in node_by_id]
    selected_edges = [
        edge
        for edge in all_edges
        if edge.source_id in selected_ids and edge.target_id in selected_ids
    ]
    return selected_nodes, selected_edges

