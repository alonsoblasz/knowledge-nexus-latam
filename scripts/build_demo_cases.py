"""Genera los casos demostrables con salida real del motor.

Escribe `docs/CASOS_DEMOSTRABLES.md` y `artifacts/evaluation/demo_cases.json`.
Los números del documento no se escriben a mano: se recalculan ejecutando el
motor, de modo que la documentación no puede desviarse del prototipo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge_nexus_retrieval.engine import (  # noqa: E402
    KnowledgeNexusEngine,
    SearchRequest,
)

CASES = [
    {
        "id": "CASO-1",
        "titulo": "Conexión no literal entre idiomas",
        "pregunta": "¿Qué nueva investigación puede ayudar a prevenir la deserción estudiantil?",
        "necesidad": "NEED-001",
        "por_que_importa": (
            "La consulta dice «deserción estudiantil». El registro que mejor responde "
            "nunca usa esa palabra: dice «student attrition». Una búsqueda por palabras "
            "clave no los conecta."
        ),
    },
    {
        "id": "CASO-2",
        "titulo": "Consulta libre en otro dominio, sin necesidad seleccionada",
        "pregunta": "¿Cómo podemos monitorear la calidad del agua en cuencas con sensores?",
        "necesidad": None,
        "por_que_importa": (
            "Demuestra que el prototipo responde a preguntas nuevas y no a un guion "
            "precargado, y que funciona fuera del dominio educativo."
        ),
    },
    {
        "id": "CASO-3",
        "titulo": "De la necesidad a las personas y el currículo",
        "pregunta": "¿Quién y con qué capacidades puede trabajar en riesgo crediticio explicable?",
        "necesidad": "NEED-014",
        "por_que_importa": (
            "Muestra conexiones con investigación, personas y capacidades en la misma "
            "respuesta, no solo documentos parecidos."
        ),
    },
    {
        "id": "CASO-4",
        "titulo": "Prueba negativa: dominio incompatible",
        "pregunta": "¿Qué investigación existe sobre deserción estudiantil?",
        "necesidad": "NEED-009",
        "por_que_importa": (
            "La necesidad es de calidad del agua y la pregunta de educación. El motor "
            "debe priorizar el dominio de la necesidad y no arrastrar los proyectos "
            "educativos al primer puesto."
        ),
    },
    {
        "id": "CASO-5",
        "titulo": "Prueba negativa: consulta sin respuesta en el dataset",
        "pregunta": "recetas de cocina medieval italiana con fermentación natural",
        "necesidad": None,
        "por_que_importa": (
            "Ninguna entidad institucional responde a esto. El sistema debe mostrar "
            "relevancias bajas y penalizaciones en lugar de fabricar una conexión."
        ),
    },
]


def render(engine: KnowledgeNexusEngine) -> tuple[str, list[dict]]:
    lines: list[str] = [
        "# Casos demostrables",
        "",
        "> Generado por `scripts/build_demo_cases.py` con salida real del motor.",
        "> Los scores expresan **relevancia para la consulta**: no son verdad",
        "> científica ni aprobación institucional.",
        "",
        "Cada caso recorre la cadena completa que pide la evaluación:",
        "**entidad → relación → evidencia → pertinencia → oportunidad → explicación**.",
        "",
    ]
    payloads: list[dict] = []
    for case in CASES:
        response = engine.search(
            SearchRequest(
                query=case["pregunta"],
                source_entity_id=case["necesidad"],
                limit=5,
            )
        )
        payloads.append({"case": case, "response": response})
        query_entity = response["query_entity"]
        lines += [
            f"## {case['id']} — {case['titulo']}",
            "",
            f"**Consulta:** «{case['pregunta']}»",
            "",
            f"**Entidad de origen:** "
            + (
                f"`{query_entity['id']}` — {query_entity['title']}"
                if query_entity.get("id")
                else "ninguna (consulta libre)"
            ),
            "",
            f"**Por qué importa:** {case['por_que_importa']}",
            "",
        ]
        if not response["connections"]:
            lines += [
                "**Resultado:** sin conexiones con evidencia verificable.",
                "",
                f"> {response['meta'].get('reason', '')}",
                "",
                "---",
                "",
            ]
            continue

        lines += [
            "| # | Entidad | Tipo | Relación inferida | Relevancia |",
            "|---|---|---|---|---|",
        ]
        for connection in response["connections"]:
            target = connection["target"]
            lines.append(
                f"| {connection['rank']} | `{target['id']}` {target['title']} | "
                f"{target['type']} | `{connection['relation']}` | "
                f"{connection['relevance']['total']:.3f} |"
            )
        top = response["connections"][0]
        relevance = top["relevance"]
        lines += [
            "",
            f"**Desglose del primer resultado (`{top['target']['id']}`):** "
            + " · ".join(
                f"{name} {relevance[name]:.2f}"
                for name in ("semantic", "domain", "method", "graph", "evidence", "actionable")
            )
            + f" → total {relevance['total']:.3f}",
            "",
            f"**Explicación del motor:** {top['explanation']}",
            "",
            "**Evidencia (archivo, fila, campo, fragmento):**",
            "",
        ]
        for item in top["evidence"][:3]:
            lines.append(
                f"- `{item['file']}` fila {item['row']}, campo `{item['field']}` "
                f"({item['record_id']}): «{item['excerpt'][:170]}»"
            )
        if response["opportunities"]:
            opportunity = response["opportunities"][0]
            lines += [
                "",
                f"**Oportunidad generada:** `{opportunity['type']}` — "
                f"{opportunity['title']} (prioridad {opportunity['priority']})",
                "",
                f"{opportunity['reason']}",
                "",
                "Entidades referenciadas: "
                + ", ".join(f"`{item['id']}`" for item in opportunity["related_entities"]),
                "",
                "Incertidumbre declarada:",
                "",
            ]
            for note in opportunity["uncertainty"][:3]:
                lines.append(f"- {note}")
        if response.get("discarded"):
            lines += ["", "**Candidatos descartados y por qué:**", ""]
            for item in response["discarded"]:
                lines.append(
                    f"- `{item['id']}` ({item['total']:.2f}) — {item['reason']}"
                )
        lines += ["", "---", ""]
    return "\n".join(lines) + "\n", payloads


def main() -> int:
    engine = KnowledgeNexusEngine.build()
    try:
        markdown, payloads = render(engine)
    finally:
        engine.close()
    (ROOT / "docs" / "CASOS_DEMOSTRABLES.md").write_text(markdown, encoding="utf-8")
    (ROOT / "artifacts" / "evaluation" / "demo_cases.json").write_text(
        json.dumps(payloads, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(payloads)} casos escritos en docs/CASOS_DEMOSTRABLES.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
