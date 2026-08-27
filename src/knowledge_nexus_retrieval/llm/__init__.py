"""Adaptador opcional de LLM, restringido por el paquete de evidencia."""

from .provider import GuardedNarrator, TemplateNarrator, build_narrator

__all__ = ["GuardedNarrator", "TemplateNarrator", "build_narrator"]
