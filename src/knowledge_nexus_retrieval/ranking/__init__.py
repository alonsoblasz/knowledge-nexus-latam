"""Ranking explicable: señales, pesos, penalizaciones y desglose visible."""

from .features import FeatureContext, ComponentScore
from .scorer import ExplainableRanker, ScoredConnection

__all__ = ["ComponentScore", "ExplainableRanker", "FeatureContext", "ScoredConnection"]
