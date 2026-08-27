"""Proveedores de embeddings intercambiables.

Un índice solo puede contener vectores de un mismo modelo y dimensión: el
manifiesto registra ambos y el motor rechaza cualquier combinación distinta.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

import numpy as np

from ..settings import Settings
from ..text import ngrams, tokenize

# Prefijos exigidos por algunas familias de modelos. Registrarlos evita mezclar
# convenciones de codificación entre documentos y consultas.
MODEL_PREFIXES: dict[str, dict[str, str]] = {
    "intfloat/multilingual-e5-small": {"document": "passage: ", "query": "query: "},
    "intfloat/multilingual-e5-base": {"document": "passage: ", "query": "query: "},
    "intfloat/multilingual-e5-large": {"document": "passage: ", "query": "query: "},
}

# Calibración del coseno por modelo, usada por el ranking para reescalar la
# similitud a un rango interpretable. Es configuración, no verdad del modelo.
MODEL_CALIBRATION: dict[str, dict[str, float]] = {
    "BAAI/bge-m3": {"cosine_floor": 0.35, "cosine_ceiling": 0.62},
    "intfloat/multilingual-e5-small": {"cosine_floor": 0.70, "cosine_ceiling": 0.95},
    "hashing-ngram-v1": {"cosine_floor": 0.05, "cosine_ceiling": 0.55},
}


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Contrato mínimo de un proveedor de embeddings normalizados."""

    @property
    def name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def encode_documents(self, texts: Sequence[str], batch_size: int = 16) -> np.ndarray: ...

    def encode_query(self, text: str) -> np.ndarray: ...

    def describe(self) -> dict[str, Any]: ...


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return (matrix / norms).astype(np.float32)


class SentenceTransformerProvider:
    """Proveedor basado en `sentence-transformers` (modelo principal del MVP)."""

    def __init__(self, model_name: str, device: str = "auto", trust_remote_code: bool = False):
        self._model_name = model_name
        self._device = device
        self._trust_remote_code = trust_remote_code
        self._model: Any | None = None
        self._dimension: int | None = None

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = int(self._load().get_sentence_embedding_dimension())
        return self._dimension

    def _resolve_device(self) -> str | None:
        if self._device and self._device != "auto":
            return self._device
        try:  # pragma: no cover - depende del hardware disponible
            import torch

            if torch.backends.mps.is_available():
                return "mps"
            if torch.cuda.is_available():
                return "cuda"
        except Exception:  # pragma: no cover - torch ausente o sin backend
            return None
        return "cpu"

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self._model_name,
                device=self._resolve_device(),
                trust_remote_code=self._trust_remote_code,
            )
        return self._model

    def _prefix(self, kind: str) -> str:
        return MODEL_PREFIXES.get(self._model_name, {}).get(kind, "")

    def encode_documents(self, texts: Sequence[str], batch_size: int = 16) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        prefix = self._prefix("document")
        payload = [f"{prefix}{text}" for text in texts]
        vectors = self._load().encode(
            payload,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return _l2_normalize(np.asarray(vectors, dtype=np.float32))

    def encode_query(self, text: str) -> np.ndarray:
        prefix = self._prefix("query")
        vectors = self._load().encode(
            [f"{prefix}{text}"],
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return _l2_normalize(np.asarray(vectors, dtype=np.float32))[0]

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "sentence-transformers",
            "model": self._model_name,
            "dimension": self.dimension,
            "device": self._resolve_device(),
            "normalized": True,
            "prefixes": MODEL_PREFIXES.get(self._model_name, {}),
        }


class HashingEmbeddingProvider:
    """Proveedor determinista sin dependencias pesadas.

    Proyecta términos (unigramas y bigramas) en un espacio de dimensión fija
    mediante hashing estable. Sirve para pruebas reproducibles y para operar sin
    descargar modelos; **no captura equivalencias entre idiomas**, por lo que no
    sustituye al modelo multilingüe en la demostración.
    """

    MODEL_NAME = "hashing-ngram-v1"

    def __init__(self, dimension: int = 256):
        if dimension <= 0:
            raise ValueError("La dimensión debe ser positiva")
        self._dimension = dimension

    @property
    def name(self) -> str:
        return self.MODEL_NAME

    @property
    def dimension(self) -> int:
        return self._dimension

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self._dimension, dtype=np.float32)
        tokens = tokenize(text)
        terms = [*tokens, *ngrams(tokens, 2)]
        for term in terms:
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = float(np.linalg.norm(vector))
        if norm > 0.0:
            vector /= norm
        return vector

    def encode_documents(self, texts: Sequence[str], batch_size: int = 16) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dimension), dtype=np.float32)
        return np.vstack([self._vector(text) for text in texts]).astype(np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        return self._vector(text)

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "hashing",
            "model": self.MODEL_NAME,
            "dimension": self._dimension,
            "device": "cpu",
            "normalized": True,
            "note": "Determinista y sin descargas; no captura equivalencias multilingües.",
        }


def build_provider(settings: Settings) -> EmbeddingProvider:
    """Instancia el proveedor configurado por entorno."""

    kind = settings.embedding_provider.strip().lower()
    if kind in {"hashing", "hash", "offline"}:
        return HashingEmbeddingProvider(dimension=settings.embedding_dimension)
    if kind in {"sentence-transformers", "sentence_transformers", "st"}:
        return SentenceTransformerProvider(
            settings.embedding_model, device=settings.embedding_device
        )
    raise ValueError(
        f"Proveedor de embeddings no soportado: {settings.embedding_provider!r}. "
        "Usa 'sentence-transformers' o 'hashing'."
    )


def calibration_for(model_name: str, fallback: dict[str, float]) -> dict[str, float]:
    """Piso y techo de coseno recomendados para un modelo."""

    return {**fallback, **MODEL_CALIBRATION.get(model_name, {})}
