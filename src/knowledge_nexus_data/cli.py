"""CLI del frente de datos y grafo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .exporter import export_contracts
from .graph_builder import GraphDatasetBuilder
from .graph_repository import GraphRepository
from .neo4j_loader import Neo4jConfig, Neo4jLoader
from .repository import DatasetRepository, discover_data_root
from .validator import validate_dataset


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return
    load_dotenv()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="knowledge-nexus-data",
        description="Validación, contratos y carga Neo4j de Knowledge Nexus Data V1.0.",
    )
    root.add_argument("--data-root", type=Path, help="Raíz explícita de Data V1.0")
    commands = root.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="Valida estructura e integridad referencial")
    validate.add_argument("--json", action="store_true", help="Imprime el reporte como JSON")

    export = commands.add_parser("export", help="Exporta contratos JSONL para el equipo")
    export.add_argument(
        "--output", type=Path, default=Path("artifacts/generated"), help="Directorio de salida"
    )

    commands.add_parser("neo4j-test", help="Comprueba credenciales y conectividad")
    initialize = commands.add_parser("neo4j-init", help="Crea restricciones e índices")
    initialize.add_argument(
        "--embedding-dimension",
        type=int,
        help="Crea además el índice vectorial con esta dimensión, por ejemplo 1024",
    )
    load = commands.add_parser("neo4j-load", help="Carga nodos y relaciones de forma idempotente")
    load.add_argument("--batch-size", type=int, default=500)
    commands.add_parser("neo4j-stats", help="Muestra conteos cargados en Neo4j")
    commands.add_parser(
        "neo4j-contract-demo",
        help="Ejecuta los cuatro métodos de lectura con el caso de demostración",
    )
    return root


def repository_from_args(data_root: Path | None) -> DatasetRepository:
    root = data_root.resolve() if data_root else discover_data_root()
    return DatasetRepository(root)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv_if_available()
    args = parser().parse_args(argv)

    if args.command == "neo4j-contract-demo":
        with GraphRepository.from_env() as graph:
            entity = graph.get_entity("InstitutionalNeed", "NEED-001")
            neighbors = graph.get_neighbors(
                    "PRJ-002",
                    ["PARTICIPATED_IN_PROJECT", "EXECUTED_BY_GROUP"],
                )
            evidence = graph.get_evidence("PRJ-002")
            related = graph.find_related_entities("PRJ-002", "Researcher")
            result = {
                "get_entity": {
                    "ok": entity is not None,
                    "result": _brief_entity(entity),
                },
                "get_neighbors": {
                    "ok": bool(neighbors),
                    "count": len(neighbors),
                    "results": [
                        {
                            "relationship": item["relationship"],
                            "direction": item["direction"],
                            "relation_origin": item["relation_origin"],
                            "target": _brief_entity(item["target"]),
                            "provenance": item["provenance"],
                        }
                        for item in neighbors
                    ],
                },
                "get_evidence": {
                    "ok": evidence is not None,
                    "entity_id": evidence["entity_id"] if evidence else None,
                    "source": evidence["source"] if evidence else None,
                    "documents": [
                        _brief_entity(document)
                        for document in (evidence["documents"] if evidence else [])
                    ],
                    "relation_evidence": (
                        evidence["relation_evidence"] if evidence else []
                    ),
                },
                "find_related_entities": {
                    "ok": bool(related),
                    "count": len(related),
                    "results": [
                        {
                            "target": _brief_entity(item["target"]),
                            "hops": item["hops"],
                            "relationships": [
                                relationship["relationship"]
                                for relationship in item["path"]
                            ],
                        }
                        for item in related
                    ],
                },
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command.startswith("neo4j-") and args.command in {
        "neo4j-test",
        "neo4j-init",
        "neo4j-stats",
    }:
        loader = Neo4jLoader(Neo4jConfig.from_env())
        if args.command == "neo4j-test":
            print(json.dumps(loader.verify_connectivity(), ensure_ascii=False, indent=2))
        elif args.command == "neo4j-init":
            loader.initialize_schema(args.embedding_dimension)
            print("Restricciones e índices creados correctamente.")
        else:
            print(json.dumps(loader.stats(), ensure_ascii=False, indent=2))
        return 0

    repository = repository_from_args(args.data_root)
    report = validate_dataset(repository)
    if args.command == "validate":
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            summary = report.to_dict()["summary"]
            print(f"Dataset: {repository.data_root}")
            print(f"Registros comprobados: {summary['records']}")
            print(f"Errores: {summary['errors']} | Advertencias: {summary['warnings']}")
            for issue in report.issues:
                location = issue.file or "dataset"
                if issue.row:
                    location += f":{issue.row}"
                print(f"[{issue.severity}] {issue.code} {location} - {issue.message}")
        return 0 if report.valid else 1

    if not report.valid:
        print("La operación se canceló porque el dataset tiene errores de integridad.", file=sys.stderr)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    if args.command == "export":
        manifest = export_contracts(repository, report, args.output.resolve())
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.command == "neo4j-load":
        builder = GraphDatasetBuilder(repository)
        loader = Neo4jLoader(Neo4jConfig.from_env())
        loader.load(builder.build_nodes(), builder.build_edges(), args.batch_size)
        print(json.dumps(loader.stats(), ensure_ascii=False, indent=2))
        return 0

    raise AssertionError(f"Comando no manejado: {args.command}")


def _brief_entity(entity: dict[str, object] | None) -> dict[str, object] | None:
    if entity is None:
        return None
    return {
        "id": entity["id"],
        "entity_type": entity["entity_type"],
        "title": entity["title"],
        "source": entity["source"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
