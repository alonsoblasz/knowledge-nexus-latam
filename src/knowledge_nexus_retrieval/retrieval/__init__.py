"""Recuperación híbrida: canal léxico, canal vectorial y expansión de grafo."""

from .hybrid import Candidate, HybridRetriever, RetrievalResult
from .lexical import BM25Index
from .query import QueryContext, QueryContextBuilder
from .vector import VectorSearcher

__all__ = [
    "BM25Index",
    "Candidate",
    "HybridRetriever",
    "QueryContext",
    "QueryContextBuilder",
    "RetrievalResult",
    "VectorSearcher",
]
