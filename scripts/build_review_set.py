"""Construye el conjunto de revisión manual a partir de reglas declaradas.

No es un Gold Standard: las etiquetas se derivan de campos declarados en Data
V1.0 (`keywords`, `title`, `main_topics`) mediante una regla explícita, y se
complementan con revisiones manuales anotadas caso por caso. La metodología, el
tamaño y las limitaciones se publican junto a las métricas.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TARGET_LABELS = ("Project", "Thesis", "Publication", "Capability", "Subject")

# Casos: necesidad, término declarado que ancla el dominio y notas del revisor.
CASES = [
    ("NEED-001", "riesgo académico", "Caso multilingüe: la necesidad dice «deserción» y los registros dicen «student attrition»."),
    ("NEED-005", "cardiovascular", "Salud digital: monitoreo remoto cardiovascular."),
    ("NEED-006", "epidemiología", "Vigilancia epidemiológica y series temporales."),
    ("NEED-008", "ergonomía", "Seguridad y salud en el trabajo: carga física y ergonomía."),
    ("NEED-009", "calidad del agua", "Gestión ambiental y monitoreo hídrico."),
    ("NEED-012", "eficiencia energética", "Optimización energética institucional."),
    ("NEED-013", "fraude", "Detección de fraude financiero."),
    ("NEED-014", "riesgo crediticio", "Riesgo crediticio con IA explicable."),
    ("NEED-016", "mantenimiento predictivo", "Mantenimiento predictivo industrial."),
    ("NEED-017", "ciberseguridad", "Ciberseguridad basada en comportamiento."),
]

# Revisión manual explícita (grado 2 = claramente pertinente para la necesidad).
MANUAL_PRIMARY = {
    "NEED-001": ["PRJ-002"],
}

# Pruebas negativas: entidades de otro dominio que no deben aparecer arriba.
NEGATIVE = {
    "NEED-001": ["PRJ-065", "PRJ-121"],
    "NEED-009": ["PRJ-002", "PRJ-105"],
    "NEED-014": ["PRJ-065", "PRJ-002"],
}


def normalize(value: object) -> str:
    decomposed = unicodedata.normalize("NFD", str(value))
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn").lower()


def main() -> int:
    nodes = [json.loads(line) for line in (ROOT / "graph_nodes.jsonl").open(encoding="utf-8")]
    by_id = {node["id"]: node for node in nodes}
    cases = []
    for need_id, anchor, note in CASES:
        need = by_id[need_id]
        expected: dict[str, int] = {}
        anchor_normalized = normalize(anchor)
        for node in nodes:
            if node["label"] not in TARGET_LABELS:
                continue
            properties = node["properties"]
            declared = " ".join(
                str(properties.get(field, ""))
                for field in ("keywords", "title", "main_topics", "capability_name", "subject_name")
            )
            if anchor_normalized in normalize(declared):
                expected[node["id"]] = 1
        for identifier in MANUAL_PRIMARY.get(need_id, []):
            expected[identifier] = 2
        cases.append(
            {
                "case_id": f"CASE-{need_id}",
                "source_entity_id": need_id,
                "query": f"¿Qué investigación puede ayudar con {need['title'].lower()}?",
                "anchor_term": anchor,
                "label_source": "regla_declarada + revision_manual",
                "reviewer_note": note,
                "expected": dict(sorted(expected.items())),
                "not_expected": NEGATIVE.get(need_id, []),
            }
        )
    payload = {
        "review_set_version": "1.0.0",
        "disclaimer": (
            "Conjunto de revisión construido por el equipo; NO es un Gold Standard "
            "oficial ni una validación académica. Las etiquetas de grado 1 provienen "
            "de una regla sobre campos declarados y las de grado 2 de revisión manual."
        ),
        "methodology": (
            "Para cada necesidad se fija un término declarado del dominio y se marcan "
            "como pertinentes las entidades cuyos campos declarados lo contienen. El "
            "conjunto se congela antes de ajustar pesos. Limitaciones: cobertura "
            "parcial, sesgo hacia coincidencias literales y un solo revisor."
        ),
        "grades": {"2": "claramente pertinente", "1": "pertinente por dominio declarado", "0": "no etiquetado"},
        "cases": cases,
    }
    output = ROOT / "artifacts" / "evaluation" / "manual_review_set.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(cases)} casos escritos en {output}")
    for case in cases:
        print(f"  {case['case_id']}: {len(case['expected'])} etiquetas, término «{case['anchor_term']}»")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
