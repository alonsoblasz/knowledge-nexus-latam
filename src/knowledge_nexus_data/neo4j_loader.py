"""Carga idempotente del contrato canónico en Neo4j."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .models import GraphEdge, GraphNode


SAFE_NAME = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        values = {
            "uri": os.getenv("NEO4J_URI", "").strip(),
            "username": os.getenv("NEO4J_USERNAME", "neo4j").strip(),
            "password": os.getenv("NEO4J_PASSWORD", "").strip(),
            "database": os.getenv("NEO4J_DATABASE", "neo4j").strip(),
        }
        missing = [key for key in ("uri", "username", "password") if not values[key]]
        if missing:
            raise ValueError(
                "Faltan variables de conexión Neo4j: " + ", ".join(f"NEO4J_{key.upper()}" for key in missing)
            )
        return cls(**values)


def _driver(config: Neo4jConfig):  # type: ignore[no-untyped-def]
    try:
        from neo4j import GraphDatabase
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Falta el driver de Neo4j. Ejecuta: python -m pip install -r requirements.txt"
        ) from exc
    return GraphDatabase.driver(config.uri, auth=(config.username, config.password))


class Neo4jLoader:
    def __init__(self, config: Neo4jConfig):
        self.config = config

    def verify_connectivity(self) -> dict[str, Any]:
        with _driver(self.config) as driver:
            driver.verify_connectivity()
            records, _, _ = driver.execute_query(
                "CALL dbms.components() YIELD name, versions, edition "
                "RETURN name, versions[0] AS version, edition",
                database_=self.config.database,
            )
            return dict(records[0]) if records else {"status": "connected"}

    def initialize_schema(self, embedding_dimension: int | None = None) -> None:
        statements = [
            "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS "
            "FOR (n:Entity) REQUIRE n.id IS UNIQUE",
            "CREATE INDEX entity_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.entity_type)",
            "CREATE INDEX entity_source_file_idx IF NOT EXISTS FOR (n:Entity) ON (n.source_file)",
            "CREATE FULLTEXT INDEX semantic_text_fulltext IF NOT EXISTS "
            "FOR (n:SemanticEntity) ON EACH [n.title, n.semantic_text]",
        ]
        if embedding_dimension is not None:
            if embedding_dimension <= 0:
                raise ValueError("embedding_dimension debe ser positivo")
            statements.append(
                "CREATE VECTOR INDEX semantic_embedding IF NOT EXISTS "
                "FOR (n:SemanticEntity) ON n.embedding "
                "OPTIONS {indexConfig: {"
                f"`vector.dimensions`: {embedding_dimension}, "
                "`vector.similarity_function`: 'cosine'}}"
            )
        with _driver(self.config) as driver:
            for statement in statements:
                driver.execute_query(statement, database_=self.config.database)

    def load(self, nodes: list[GraphNode], edges: list[GraphEdge], batch_size: int = 500) -> None:
        with _driver(self.config) as driver:
            self._load_nodes(driver, nodes, batch_size)
            self._load_edges(driver, edges, batch_size)

    def _load_nodes(self, driver: Any, nodes: list[GraphNode], batch_size: int) -> None:
        groups: dict[tuple[str, bool], list[dict[str, Any]]] = defaultdict(list)
        for node in nodes:
            _assert_safe_name(node.label)
            groups[(node.label, bool(node.semantic_text))].append(
                {
                    "id": node.id,
                    "title": node.title,
                    "semantic_text": node.semantic_text,
                    "properties": node.properties,
                }
            )
        for (label, semantic), rows in groups.items():
            semantic_label = ":SemanticEntity" if semantic else ""
            query = (
                f"UNWIND $rows AS row MERGE (n:Entity{semantic_label}:{label} {{id: row.id}}) "
                "SET n.title = row.title, n.semantic_text = row.semantic_text, n += row.properties"
            )
            for batch in _batches(rows, batch_size):
                driver.execute_query(query, rows=batch, database_=self.config.database)

    def _load_edges(self, driver: Any, edges: list[GraphEdge], batch_size: int) -> None:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            _assert_safe_name(edge.relationship)
            properties = dict(edge.properties)
            properties["relation_origin"] = edge.relation_origin
            properties["provenance_json"] = json.dumps(edge.provenance, ensure_ascii=False)
            groups[edge.relationship].append(
                {
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "properties": properties,
                }
            )
        for relationship, rows in groups.items():
            query = (
                "UNWIND $rows AS row "
                "MATCH (source:Entity {id: row.source_id}) "
                "MATCH (target:Entity {id: row.target_id}) "
                f"MERGE (source)-[r:{relationship}]->(target) "
                "SET r += row.properties"
            )
            for batch in _batches(rows, batch_size):
                driver.execute_query(query, rows=batch, database_=self.config.database)

    def stats(self) -> dict[str, Any]:
        with _driver(self.config) as driver:
            node_records, _, _ = driver.execute_query(
                "MATCH (n:Entity) RETURN n.entity_type AS label, count(*) AS count ORDER BY label",
                database_=self.config.database,
            )
            edge_records, _, _ = driver.execute_query(
                "MATCH ()-[r]->() RETURN type(r) AS relationship, count(*) AS count "
                "ORDER BY relationship",
                database_=self.config.database,
            )
            return {
                "nodes": [dict(record) for record in node_records],
                "edges": [dict(record) for record in edge_records],
            }


def _assert_safe_name(name: str) -> None:
    if not SAFE_NAME.fullmatch(name):
        raise ValueError(f"Nombre Cypher no permitido: {name}")


def _batches(rows: list[dict[str, Any]], batch_size: int):  # type: ignore[no-untyped-def]
    if batch_size <= 0:
        raise ValueError("batch_size debe ser positivo")
    for index in range(0, len(rows), batch_size):
        yield rows[index : index + batch_size]

