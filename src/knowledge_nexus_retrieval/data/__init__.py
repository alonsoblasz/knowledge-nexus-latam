"""Acceso de solo lectura a Data V1.0: documentos semánticos y grafo."""

from .corpus import SemanticCorpus, SemanticDocument
from .graph_port import GraphNavigator, GraphPort, build_graph_port
from .jsonl_graph import JsonlGraphRepository

__all__ = [
    "GraphNavigator",
    "GraphPort",
    "JsonlGraphRepository",
    "SemanticCorpus",
    "SemanticDocument",
    "build_graph_port",
]
