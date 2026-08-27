"""Pipeline reproducible y reanudable de embeddings semánticos."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..data.corpus import SemanticCorpus, SemanticDocument
from .providers import EmbeddingProvider, calibration_for


def text_sha256(text: str) -> str:
    """Hash del texto exactamente como se indexa."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EmbeddingModelMismatchError(RuntimeError):
    """El artefacto existente pertenece a otro modelo o dimensión."""


@dataclass
class EmbeddingPipelineResult:
    total_documents: int
    generated: int
    reused: int
    model: str
    dimension: int
    output_path: str
    manifest_path: str
    duration_seconds: float
    batches: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EmbeddingPipeline:
    """Genera `semantic_embeddings.jsonl` por lotes, sin repetir trabajo previo."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        output_path: Path,
        manifest_path: Path,
        batch_size: int = 16,
    ):
        self._provider = provider
        self._output_path = output_path
        self._manifest_path = manifest_path
        self._batch_size = max(1, batch_size)

    # Lectura del artefacto previo ---------------------------------------
    def _load_existing(self) -> dict[str, dict[str, Any]]:
        if not self._output_path.is_file():
            return {}
        existing: dict[str, dict[str, Any]] = {}
        with self._output_path.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    # Una línea truncada por una interrupción se descarta y se
                    # vuelve a calcular; el resto del trabajo se conserva.
                    continue
                identifier = str(record.get("id", ""))
                if not identifier:
                    continue
                if record.get("model") != self._provider.name:
                    raise EmbeddingModelMismatchError(
                        f"{self._output_path}:{number} fue generado con "
                        f"{record.get('model')!r} y el proveedor actual es "
                        f"{self._provider.name!r}. No se pueden mezclar modelos."
                    )
                if int(record.get("dimension", -1)) != self._provider.dimension:
                    raise EmbeddingModelMismatchError(
                        f"{self._output_path}:{number} tiene dimensión "
                        f"{record.get('dimension')} y el modelo actual usa "
                        f"{self._provider.dimension}."
                    )
                existing[identifier] = record
        return existing

    # Generación ----------------------------------------------------------
    def run(
        self,
        corpus: SemanticCorpus,
        source_path: Path | None = None,
        resume: bool = True,
        document_ids: Sequence[str] | None = None,
        progress: Any | None = None,
    ) -> EmbeddingPipelineResult:
        started = time.perf_counter()
        self._output_path.parent.mkdir(parents=True, exist_ok=True)

        selected: list[SemanticDocument] = (
            [corpus.require(identifier) for identifier in document_ids]
            if document_ids is not None
            else list(corpus)
        )
        existing = self._load_existing() if resume else {}
        reusable: dict[str, dict[str, Any]] = {}
        pending: list[SemanticDocument] = []
        for document in selected:
            record = existing.get(document.id)
            if record is not None and record.get("text_sha256") == text_sha256(document.text):
                reusable[document.id] = record
            else:
                pending.append(document)

        batches = 0
        if pending:
            # Se escribe por lotes en modo adición: una interrupción conserva
            # todo lo calculado hasta ese punto y la siguiente ejecución sigue.
            with self._output_path.open("a", encoding="utf-8") as handle:
                for start in range(0, len(pending), self._batch_size):
                    chunk = pending[start : start + self._batch_size]
                    vectors = self._provider.encode_documents(
                        [document.text for document in chunk], batch_size=self._batch_size
                    )
                    if vectors.shape[0] != len(chunk):
                        raise RuntimeError(
                            "El proveedor devolvió un número de vectores distinto al lote"
                        )
                    for document, vector in zip(chunk, vectors, strict=True):
                        record = self._build_record(document, vector)
                        reusable[document.id] = record
                        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                    batches += 1
                    if progress is not None:
                        progress(min(start + len(chunk), len(pending)), len(pending))

        ordered = [reusable[document.id] for document in selected]
        self._validate(ordered, selected)
        self._rewrite(ordered)
        warnings = self._write_manifest(ordered, corpus, source_path, len(selected))
        return EmbeddingPipelineResult(
            total_documents=len(selected),
            generated=len(pending),
            reused=len(selected) - len(pending),
            model=self._provider.name,
            dimension=self._provider.dimension,
            output_path=str(self._output_path),
            manifest_path=str(self._manifest_path),
            duration_seconds=round(time.perf_counter() - started, 3),
            batches=batches,
            warnings=warnings,
        )

    def _build_record(self, document: SemanticDocument, vector: np.ndarray) -> dict[str, Any]:
        if vector.shape[0] != self._provider.dimension:
            raise ValueError(
                f"{document.id}: dimensión {vector.shape[0]} distinta de "
                f"{self._provider.dimension}"
            )
        return {
            "id": document.id,
            "entity_type": document.entity_type,
            "model": self._provider.name,
            "dimension": int(self._provider.dimension),
            "text_sha256": text_sha256(document.text),
            "embedding": [round(float(value), 6) for value in vector.tolist()],
        }

    def _validate(
        self, records: Sequence[dict[str, Any]], documents: Sequence[SemanticDocument]
    ) -> None:
        if len(records) != len(documents):
            raise RuntimeError("Cobertura incompleta: faltan embeddings por documento")
        seen: set[str] = set()
        for record in records:
            identifier = str(record["id"])
            if identifier in seen:
                raise ValueError(f"ID duplicado en el artefacto de embeddings: {identifier}")
            seen.add(identifier)
            if len(record["embedding"]) != self._provider.dimension:
                raise ValueError(
                    f"{identifier}: el vector no tiene dimensión {self._provider.dimension}"
                )
        expected = {document.id for document in documents}
        if seen != expected:
            missing = sorted(expected - seen)[:5]
            raise RuntimeError(f"Faltan embeddings para: {missing}")

    def _rewrite(self, records: Iterable[dict[str, Any]]) -> None:
        """Reescribe el artefacto en orden estable y de forma atómica."""

        temporary = self._output_path.with_suffix(".jsonl.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self._output_path)

    def _write_manifest(
        self,
        records: Sequence[dict[str, Any]],
        corpus: SemanticCorpus,
        source_path: Path | None,
        processed: int,
    ) -> list[str]:
        warnings: list[str] = []
        if processed != len(corpus):
            warnings.append(
                f"Se procesaron {processed} de {len(corpus)} documentos del corpus"
            )
        counts: dict[str, int] = {}
        for record in records:
            counts[str(record.get("entity_type", "Unknown"))] = (
                counts.get(str(record.get("entity_type", "Unknown")), 0) + 1
            )
        description = self._provider.describe()
        manifest = {
            "artifact": "semantic_embeddings",
            "artifact_version": "1.0",
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": self._provider.name,
            "dimension": int(self._provider.dimension),
            "normalized": True,
            "provider": description.get("provider"),
            "device": description.get("device"),
            "prefixes": description.get("prefixes", {}),
            "cosine_calibration": calibration_for(
                self._provider.name, {"cosine_floor": 0.25, "cosine_ceiling": 0.85}
            ),
            "documents_processed": processed,
            "documents_in_corpus": len(corpus),
            "documents_by_type": dict(sorted(counts.items())),
            "batch_size": self._batch_size,
            "output_file": self._output_path.name,
            "source_file": source_path.name if source_path else None,
            "source_sha256": file_sha256(source_path) if source_path else None,
            "warnings": warnings,
            "notes": (
                "Artefacto derivado y reproducible. No contiene credenciales ni "
                "texto fuente: solo ID, modelo, dimensión, hash del texto y vector."
            ),
        }
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return warnings
