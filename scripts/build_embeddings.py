"""Genera el artefacto de embeddings semánticos con la configuración activa."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from knowledge_nexus_retrieval.data import SemanticCorpus  # noqa: E402
from knowledge_nexus_retrieval.embeddings import EmbeddingPipeline, build_provider  # noqa: E402
from knowledge_nexus_retrieval.settings import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    corpus = SemanticCorpus.from_jsonl(settings.semantic_documents_path)
    provider = build_provider(settings)
    pipeline = EmbeddingPipeline(
        provider,
        settings.embeddings_path,
        settings.embeddings_manifest_path,
        batch_size=settings.embedding_batch_size,
    )

    def progress(done: int, total: int) -> None:
        if done % 320 == 0 or done == total:
            print(f"  {done}/{total}", flush=True)

    print(f"Modelo: {provider.name} ({provider.dimension}d) — {len(corpus)} documentos", flush=True)
    result = pipeline.run(corpus, source_path=settings.semantic_documents_path, progress=progress)
    print(
        f"Generados {result.generated}, reutilizados {result.reused}, "
        f"{result.duration_seconds}s -> {result.output_path}",
        flush=True,
    )
    for warning in result.warnings:
        print(f"Aviso: {warning}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
