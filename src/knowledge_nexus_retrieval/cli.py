"""Interfaz de línea de comandos del motor de recuperación.

Comandos reproducibles:

    knowledge-nexus embeddings   # genera o reanuda el artefacto de vectores
    knowledge-nexus search       # ejecuta una consulta y muestra el desglose
    knowledge-nexus evaluate     # mide el conjunto de validación manual
    knowledge-nexus serve        # levanta la API
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .data.corpus import SemanticCorpus
from .embeddings.pipeline import EmbeddingPipeline
from .embeddings.providers import build_provider
from .engine import KnowledgeNexusEngine, SearchRequest
from .settings import get_settings


def _command_embeddings(args: argparse.Namespace) -> int:
    settings = get_settings()
    corpus = SemanticCorpus.from_jsonl(settings.semantic_documents_path)
    provider = build_provider(settings)
    pipeline = EmbeddingPipeline(
        provider,
        settings.embeddings_path,
        settings.embeddings_manifest_path,
        batch_size=args.batch_size or settings.embedding_batch_size,
    )

    def progress(done: int, total: int) -> None:
        if args.quiet:
            return
        if done % (args.batch_size * 10 or 320) == 0 or done == total:
            print(f"  {done}/{total}", file=sys.stderr, flush=True)

    result = pipeline.run(
        corpus,
        source_path=settings.semantic_documents_path,
        resume=not args.no_resume,
        document_ids=corpus.ids[: args.limit] if args.limit else None,
        progress=progress,
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


def _command_search(args: argparse.Namespace) -> int:
    engine = KnowledgeNexusEngine.build()
    try:
        response = engine.search(
            SearchRequest(
                query=args.query,
                source_entity_id=args.source,
                target_types=args.types,
                limit=args.limit,
                include_graph=not args.no_graph,
            )
        )
    finally:
        engine.close()
    if args.json:
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0
    _print_response(response)
    return 0


def _command_evaluate(args: argparse.Namespace) -> int:
    from .evaluation.harness import EvaluationHarness

    engine = KnowledgeNexusEngine.build()
    try:
        harness = EvaluationHarness(engine)
        report = harness.run(cases_path=args.cases, limit=args.limit)
    finally:
        engine.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["failed_expectations"] == 0 else 1


def _command_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "knowledge_nexus_retrieval.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def _print_response(response: dict[str, Any]) -> None:
    query_entity = response.get("query_entity") or {}
    print(f"Consulta: {query_entity.get('id') or '—'} {query_entity.get('title') or ''}")
    print(f"Aviso: {response['warning']}\n")
    if not response["connections"]:
        print("Sin resultados con evidencia verificable.")
        print(response.get("meta", {}).get("reason", ""))
        return
    for connection in response["connections"]:
        relevance = connection["relevance"]
        print(
            f"{connection['rank']}. {connection['target']['id']} "
            f"({connection['target']['type']}) — {connection['target']['title']}"
        )
        print(
            "   total={total:.3f} semantic={semantic:.2f} domain={domain:.2f} "
            "method={method:.2f} graph={graph:.2f} evidence={evidence:.2f} "
            "actionable={actionable:.2f}".format(**relevance)
        )
        print(f"   relación: {connection['relation']} ({connection['relation_origin']})")
        print(f"   {connection['explanation']}")
        for item in connection["evidence"][:3]:
            print(
                f"     · {item['file']}:{item['row']} campo {item['field']} → "
                f"{item['excerpt'][:110]}"
            )
        print()
    for opportunity in response.get("opportunities", []):
        print(
            f"[{opportunity['type']}] {opportunity['title']} "
            f"(prioridad {opportunity['priority']})"
        )
        print(f"   {opportunity['reason']}")
        print(f"   entidades: {[item['id'] for item in opportunity['related_entities']]}")
        for note in opportunity.get("uncertainty", [])[:2]:
            print(f"   incertidumbre: {note}")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowledge-nexus",
        description="Búsqueda híbrida explicable sobre Data V1.0",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    embeddings = subparsers.add_parser("embeddings", help="Genera o reanuda los embeddings")
    embeddings.add_argument("--batch-size", type=int, default=0)
    embeddings.add_argument("--limit", type=int, default=0, help="Procesa solo los primeros N documentos")
    embeddings.add_argument("--no-resume", action="store_true")
    embeddings.add_argument("--quiet", action="store_true")
    embeddings.set_defaults(handler=_command_embeddings)

    search = subparsers.add_parser("search", help="Ejecuta una consulta")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--source", default=None, help="ID de la entidad de origen, por ejemplo NEED-001")
    search.add_argument("--types", nargs="*", default=None)
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--json", action="store_true")
    search.add_argument("--no-graph", action="store_true")
    search.set_defaults(handler=_command_search)

    evaluate = subparsers.add_parser("evaluate", help="Ejecuta el conjunto de validación manual")
    evaluate.add_argument("--cases", default=None)
    evaluate.add_argument("--limit", type=int, default=5)
    evaluate.set_defaults(handler=_command_evaluate)

    serve = subparsers.add_parser("serve", help="Levanta la API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(handler=_command_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
