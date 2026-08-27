"""Puerto único de acceso al grafo y navegación derivada.

`GraphPort` es el contrato de cuatro métodos que ya expone la capa de datos.
El motor nunca escribe Cypher: cualquier recorrido adicional se construye sobre
esos cuatro métodos, de modo que funciona igual con JSONL local y con Aura.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..settings import Settings
from .jsonl_graph import JsonlGraphRepository


@runtime_checkable
class GraphPort(Protocol):
    """Contrato de lectura compartido con `knowledge_nexus_data.GraphRepository`."""

    def get_entity(self, entity_type: str, entity_id: str) -> dict[str, Any] | None: ...

    def get_neighbors(
        self, entity_id: str, relation_types: Sequence[str] | None = None
    ) -> list[dict[str, Any]]: ...

    def get_evidence(self, entity_id: str) -> dict[str, Any] | None: ...

    def find_related_entities(self, entity_id: str, target_type: str) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...


def build_graph_port(settings: Settings) -> GraphPort:
    """Crea el backend de grafo configurado (`jsonl` por defecto, `neo4j` opcional)."""

    backend = settings.graph_backend
    if backend == "jsonl":
        return JsonlGraphRepository.from_jsonl(
            settings.graph_nodes_path, settings.graph_edges_path
        )
    if backend == "neo4j":
        # La conexión y las credenciales las resuelve la capa de datos a partir
        # del entorno; este módulo nunca las lee ni las registra.
        from knowledge_nexus_data.graph_repository import GraphRepository

        return GraphRepository.from_env()
    raise ValueError(f"Backend de grafo no soportado: {backend!r}. Usa 'jsonl' o 'neo4j'.")


class GraphNavigator:
    """Recorridos memorizados sobre el puerto de grafo.

    Mantiene un presupuesto de visitas para que una expansión no recorra el
    grafo completo durante una consulta interactiva.
    """

    def __init__(self, graph: GraphPort, max_depth: int = 3, visit_budget: int = 4000):
        self._graph = graph
        self._max_depth = max_depth
        self._visit_budget = visit_budget
        self._neighbor_cache: dict[str, list[dict[str, Any]]] = {}
        self._distance_cache: dict[str, dict[str, int]] = {}

    def neighbors(self, entity_id: str) -> list[dict[str, Any]]:
        cached = self._neighbor_cache.get(entity_id)
        if cached is None:
            cached = self._graph.get_neighbors(entity_id)
            self._neighbor_cache[entity_id] = cached
        return cached

    def degree(self, entity_id: str) -> int:
        return len(self.neighbors(entity_id))

    def neighbor_ids(self, entity_id: str) -> set[str]:
        return {str(item["target"]["id"]) for item in self.neighbors(entity_id)}

    def distances(self, entity_id: str) -> dict[str, int]:
        """Distancia en saltos explícitos desde una entidad, hasta `max_depth`."""

        cached = self._distance_cache.get(entity_id)
        if cached is not None:
            return cached
        distances: dict[str, int] = {entity_id: 0}
        queue: deque[tuple[str, int]] = deque([(entity_id, 0)])
        visits = 0
        while queue and visits < self._visit_budget:
            current, depth = queue.popleft()
            if depth >= self._max_depth:
                continue
            for neighbor in self.neighbors(current):
                visits += 1
                target_id = str(neighbor["target"]["id"])
                if target_id in distances:
                    continue
                distances[target_id] = depth + 1
                queue.append((target_id, depth + 1))
            if visits >= self._visit_budget:
                break
        self._distance_cache[entity_id] = distances
        return distances

    def distance(self, source_id: str, target_id: str) -> int | None:
        return self.distances(source_id).get(target_id)

    def expand(
        self,
        seed_ids: Iterable[str],
        max_hops: int = 2,
        allowed_types: frozenset[str] | None = None,
        per_seed_limit: int = 60,
    ) -> dict[str, dict[str, Any]]:
        """Expande vecinos explícitos de las semillas y conserva el camino usado.

        Devuelve `id -> {hops, seed_id, path}` con el camino más corto conocido.
        La expansión solo recorre relaciones explícitas de Data V1.0: no crea
        aristas nuevas ni combina entidades que el grafo no relacione.
        """

        found: dict[str, dict[str, Any]] = {}
        for seed_id in seed_ids:
            frontier: list[tuple[str, list[dict[str, Any]]]] = [(seed_id, [])]
            visited: set[str] = {seed_id}
            collected = 0
            for depth in range(1, max_hops + 1):
                next_frontier: list[tuple[str, list[dict[str, Any]]]] = []
                for current, path in frontier:
                    for neighbor in self.neighbors(current):
                        target = neighbor["target"]
                        target_id = str(target["id"])
                        step = {
                            "relationship": neighbor["relationship"],
                            "direction": neighbor["direction"],
                            "relation_origin": neighbor["relation_origin"],
                            "provenance": neighbor["provenance"],
                            "from_id": current,
                            "to_id": target_id,
                        }
                        extended = [*path, step]
                        if target_id not in visited:
                            visited.add(target_id)
                            next_frontier.append((target_id, extended))
                        entity_type = target.get("entity_type")
                        if allowed_types is not None and entity_type not in allowed_types:
                            continue
                        previous = found.get(target_id)
                        if previous is None or depth < previous["hops"]:
                            found[target_id] = {
                                "hops": depth,
                                "seed_id": seed_id,
                                "path": extended,
                                "entity": target,
                            }
                            collected += 1
                    if collected >= per_seed_limit:
                        break
                frontier = next_frontier
                if collected >= per_seed_limit:
                    break
        return found


def entity_fields(entity: dict[str, Any]) -> dict[str, Any]:
    """Campos citables de una entidad.

    `title` viaja fuera de `properties` en la carga útil del repositorio, pero es
    una columna real de Data V1.0 (`projects.csv`, `theses.csv`, ...). Se
    reincorpora para que la cobertura y la evidencia lo reconozcan.
    """

    fields = dict(entity.get("properties") or {})
    title = entity.get("title")
    if title and "title" not in fields:
        fields["title"] = title
    return fields


def resolve_data_paths(settings: Settings) -> dict[str, Path]:
    """Rutas efectivas de los artefactos de datos, útil para diagnósticos."""

    return {
        "semantic_documents": settings.semantic_documents_path,
        "graph_nodes": settings.graph_nodes_path,
        "graph_edges": settings.graph_edges_path,
        "embeddings": settings.embeddings_path,
    }


class EntityResolver:
    """Resuelve una entidad por ID sin conocer de antemano su etiqueta.

    Usa el corpus semántico como catálogo de tipos y consulta el grafo una sola
    vez por entidad. Si un ID no existe, devuelve ``None``: el motor nunca
    fabrica entidades para completar una respuesta.
    """

    def __init__(self, graph: GraphPort, types_by_id: dict[str, str]):
        self._graph = graph
        self._types_by_id = types_by_id
        self._cache: dict[str, dict[str, Any] | None] = {}

    def type_of(self, identifier: str) -> str | None:
        return self._types_by_id.get(identifier)

    def resolve(self, identifier: str) -> dict[str, Any] | None:
        if identifier in self._cache:
            return self._cache[identifier]
        entity_type = self._types_by_id.get(identifier)
        entity: dict[str, Any] | None = None
        if entity_type:
            entity = self._graph.get_entity(entity_type, identifier)
        if entity is None:
            for candidate_type in sorted(set(self._types_by_id.values())):
                entity = self._graph.get_entity(candidate_type, identifier)
                if entity is not None:
                    break
        self._cache[identifier] = entity
        return entity

    def exists(self, identifier: str) -> bool:
        return self.resolve(identifier) is not None

    @property
    def known_ids(self) -> frozenset[str]:
        return frozenset(self._types_by_id)
