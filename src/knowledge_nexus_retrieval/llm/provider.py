"""Redacción opcional con LLM, siempre subordinada a la evidencia recuperada.

El modelo de lenguaje puede reescribir un texto ya construido por el sistema.
No puede crear IDs, personas, proyectos, capacidades ni fuentes: cualquier
identificador que no esté en el paquete recuperado invalida su respuesta y el
motor conserva el texto determinista.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

from ..evidence.assembler import IdentifierGuard
from ..settings import Settings

_ID_PATTERN = re.compile(r"\b[A-Z]{2,6}-\d{2,5}\b")


@runtime_checkable
class Narrator(Protocol):
    """Reescribe un texto a partir de hechos ya verificados."""

    @property
    def name(self) -> str: ...

    def rewrite(self, deterministic_text: str, facts: dict[str, Any]) -> str | None: ...


class TemplateNarrator:
    """Redacción por plantilla: no llama a ningún servicio externo."""

    @property
    def name(self) -> str:
        return "template"

    def rewrite(self, deterministic_text: str, facts: dict[str, Any]) -> str | None:
        return None


class GuardedNarrator:
    """Envoltura que valida la salida del LLM contra el paquete de evidencia."""

    def __init__(self, narrator: Narrator, guard: IdentifierGuard):
        self._narrator = narrator
        self._guard = guard
        self.rejections: list[str] = []

    @property
    def name(self) -> str:
        return self._narrator.name

    def rewrite(self, deterministic_text: str, facts: dict[str, Any]) -> str:
        try:
            candidate = self._narrator.rewrite(deterministic_text, facts)
        except Exception as error:  # pragma: no cover - depende del proveedor
            self.rejections.append(f"El proveedor falló: {type(error).__name__}")
            return deterministic_text
        if not candidate:
            return deterministic_text
        invented = sorted(
            {
                identifier
                for identifier in _ID_PATTERN.findall(candidate)
                if not self._guard.contains(identifier)
            }
        )
        if invented:
            self.rejections.append(
                f"Texto descartado por citar IDs inexistentes: {', '.join(invented)}"
            )
            return deterministic_text
        return candidate


def build_narrator(settings: Settings) -> Narrator:
    """Devuelve el narrador configurado. Por defecto, plantillas deterministas."""

    provider = settings.llm_provider.strip().lower()
    if provider in {"", "none", "template", "off"}:
        return TemplateNarrator()
    raise ValueError(
        f"Proveedor de LLM no soportado en el MVP: {settings.llm_provider!r}. "
        "Usa 'template'; la recuperación, el ranking y la evidencia no dependen del LLM."
    )
