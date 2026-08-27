"""Normalización y análisis de texto compartidos por recuperación y ranking.

Las funciones de este módulo son deterministas: la misma entrada produce
siempre la misma salida, sin depender del reloj ni de recursos externos.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

# Etiquetas usadas por la capa de datos al construir el texto semántico.
# Permiten recorrer el camino inverso: de un fragmento de texto al campo origen.
from knowledge_nexus_data.semantic import FIELD_LABELS


LABEL_TO_FIELD: dict[str, str] = {label: field for field, label in FIELD_LABELS.items()}

_WORD_RE = re.compile(r"[0-9a-záéíóúüñ]+", re.IGNORECASE)
_SECTION_RE = re.compile(r"^([A-ZÁÉÍÓÚÑ][^:\n]{2,40}):\s*(.*)$")
_ID_RE = re.compile(r"\b([A-Z]{2,6})-(\d{2,5})\b")


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def normalize(value: object) -> str:
    """Minúsculas sin acentos ni signos, para comparar términos."""

    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(item) for item in value)
    return strip_accents(str(value)).lower().strip()


def tokenize(value: object, stopwords: frozenset[str] = frozenset()) -> list[str]:
    """Divide en tokens normalizados, descartando vacíos y palabras funcionales."""

    text = normalize(value)
    tokens = _WORD_RE.findall(text)
    return [token for token in tokens if len(token) > 2 and token not in stopwords]


def term_set(value: object, stopwords: frozenset[str] = frozenset()) -> set[str]:
    return set(tokenize(value, stopwords))


def ngrams(tokens: Sequence[str], size: int) -> list[str]:
    if size <= 1:
        return list(tokens)
    return [" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)]


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    if not intersection:
        return 0.0
    return intersection / len(left | right)


def overlap_coefficient(left: set[str], right: set[str]) -> float:
    """Solapamiento relativo al conjunto más pequeño; útil con textos desiguales."""

    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def counter_cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    if not shared:
        return 0.0
    numerator = sum(left[term] * right[term] for term in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def rescale(value: float, floor: float, ceiling: float) -> float:
    """Reescala un valor calibrando piso y techo; fuera de rango satura en 0 o 1."""

    if ceiling <= floor:
        return clamp01(value)
    return clamp01((value - floor) / (ceiling - floor))


def excerpt(value: object, max_chars: int = 320) -> str:
    """Fragmento legible de un campo, sin alterar su contenido original."""

    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        text = "; ".join(str(item) for item in value)
    elif isinstance(value, bool):
        text = "sí" if value else "no"
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def parse_labeled_sections(semantic_text: str) -> dict[str, str]:
    """Reconstruye `campo -> valor` desde el texto semántico etiquetado.

    La capa de datos escribe una línea por campo con la forma ``Etiqueta: valor``.
    Recuperar esa estructura permite citar el campo exacto como evidencia cuando
    solo se dispone del documento semántico.
    """

    sections: dict[str, str] = {}
    current_field: str | None = None
    for line in semantic_text.splitlines():
        match = _SECTION_RE.match(line.strip())
        if match:
            label, value = match.group(1).strip(), match.group(2).strip()
            field = LABEL_TO_FIELD.get(label)
            if field is None:
                field = normalize(label).replace(" ", "_")
            current_field = field
            sections[field] = value
        elif current_field and line.strip():
            sections[current_field] = f"{sections[current_field]} {line.strip()}".strip()
    return {field: value for field, value in sections.items() if value}


def extract_canonical_ids(value: object, known_ids: frozenset[str] | None = None) -> set[str]:
    """Extrae IDs canónicos (`FAC-004`, `PRG-012`) mencionados en un texto.

    Solo devuelve identificadores que existan realmente en el paquete de datos:
    el motor nunca inventa ni infiere IDs nuevos.
    """

    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        text = " ".join(str(item) for item in value)
    else:
        text = str(value)
    found = {f"{prefix}-{number}" for prefix, number in _ID_RE.findall(text)}
    if known_ids is None:
        return found
    return {identifier for identifier in found if identifier in known_ids}


@dataclass(frozen=True)
class Lexicon:
    """Léxico auxiliar configurable: sinónimos, vocabulario de método y stopwords."""

    synonym_groups: tuple[frozenset[str], ...]
    method_terms: tuple[str, ...]
    stopwords: frozenset[str]
    version: str = "unknown"
    # Forma original de cada término normalizado, para mostrarla al usuario.
    display_forms: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> "Lexicon":
        groups: list[frozenset[str]] = []
        for group in config.get("synonyms", []) or []:
            normalized = {normalize(term) for term in group if str(term).strip()}
            if len(normalized) > 1:
                groups.append(frozenset(normalized))
        raw_method_terms = [
            str(term).strip() for term in (config.get("method_terms", []) or []) if str(term).strip()
        ]
        method_terms = tuple(normalize(term) for term in raw_method_terms)
        display_forms = {normalize(term): term for term in raw_method_terms}
        stopwords = frozenset(
            normalize(word) for word in (config.get("stopwords", []) or []) if str(word).strip()
        )
        return cls(
            synonym_groups=tuple(groups),
            method_terms=method_terms,
            stopwords=stopwords,
            version=str(config.get("version", "unknown")),
            display_forms=display_forms,
        )

    def display(self, term: str) -> str:
        """Forma legible de un término normalizado."""

        return self.display_forms.get(term, term)

    def expand_terms(self, terms: Iterable[str]) -> set[str]:
        """Añade los términos equivalentes de cada grupo que aparezca en la entrada."""

        base = {normalize(term) for term in terms if str(term).strip()}
        expanded = set(base)
        joined = " ".join(sorted(base))
        for group in self.synonym_groups:
            triggered = any(
                phrase in base or (" " in phrase and phrase in joined) for phrase in group
            )
            if not triggered:
                continue
            for phrase in group:
                expanded.update(phrase.split())
                expanded.add(phrase)
        return {term for term in expanded if term}

    def method_signals(self, value: object) -> set[str]:
        """Términos metodológicos del léxico presentes en un texto."""

        text = normalize(value)
        if not text:
            return set()
        return {term for term in self.method_terms if term and term in text}


def token_counter(
    values: Iterable[object],
    stopwords: frozenset[str] = frozenset(),
    include_bigrams: bool = True,
) -> Counter[str]:
    """Vector de términos (unigramas y bigramas) de un conjunto de campos."""

    counter: Counter[str] = Counter()
    for value in values:
        tokens = tokenize(value, stopwords)
        counter.update(tokens)
        if include_bigrams:
            counter.update(ngrams(tokens, 2))
    return counter
