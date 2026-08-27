"""Métricas del motor sobre el conjunto de revisión manual.

Advertencia metodológica: el conjunto de revisión no es un Gold Standard. Las
entidades no etiquetadas se tratan como *desconocidas*, no como irrelevantes,
por lo que `precision@k` es una cota inferior y debe leerse junto a
`expected_hit_rate@k`.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from ..engine import KnowledgeNexusEngine, SearchRequest


class EvaluationHarness:
    """Ejecuta los casos y calcula métricas de recuperación y trazabilidad."""

    def __init__(self, engine: KnowledgeNexusEngine):
        self._engine = engine

    def default_cases_path(self) -> Path:
        settings = self._engine._settings  # noqa: SLF001
        candidate = settings.evaluation_dir / "manual_review_set.json"
        if candidate.is_file():
            return candidate
        # Reserva: la copia versionada en la raíz del proyecto.
        return settings.project_root / "artifacts" / "evaluation" / "manual_review_set.json"

    def run(self, cases_path: str | Path | None = None, limit: int = 5) -> dict[str, Any]:
        path = Path(cases_path) if cases_path else self.default_cases_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"No existe el conjunto de revisión en {path}. "
                "Genéralo con `python scripts/build_review_set.py`."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases = payload.get("cases", [])

        results: list[dict[str, Any]] = []
        latencies: list[float] = []
        failed = 0
        for case in cases:
            started = time.perf_counter()
            response = self._engine.search(
                SearchRequest(
                    query=case.get("query", ""),
                    source_entity_id=case.get("source_entity_id"),
                    limit=limit,
                    include_graph=False,
                )
            )
            latencies.append((time.perf_counter() - started) * 1000)
            expected: dict[str, int] = {
                str(key): int(value) for key, value in (case.get("expected") or {}).items()
            }
            forbidden = {str(item) for item in (case.get("not_expected") or [])}
            retrieved = [str(item["target"]["id"]) for item in response["connections"]]
            # La regla de etiquetado solo cubre estos tipos; medir precisión sobre
            # tipos no etiquetados (por ejemplo Researcher) subestima el resultado.
            labeled_types = {"Project", "Thesis", "Publication", "Capability", "Subject"}
            comparable = [
                str(item["target"]["id"])
                for item in response["connections"]
                if str(item["target"]["type"]) in labeled_types
            ]

            hits = [identifier for identifier in retrieved if identifier in expected]
            precision = len(hits) / len(retrieved) if retrieved else 0.0
            comparable_hits = [item for item in comparable if item in expected]
            precision_comparable = (
                len(comparable_hits) / len(comparable) if comparable else 0.0
            )
            hit_rate = (
                len([identifier for identifier in expected if identifier in retrieved])
                / len(expected)
                if expected
                else 0.0
            )
            violations = sorted(set(retrieved) & forbidden)
            case_result = {
                "case_id": case.get("case_id"),
                "source_entity_id": case.get("source_entity_id"),
                "retrieved": retrieved,
                "labeled_hits": hits,
                "precision_at_k": round(precision, 4),
                "precision_at_k_labeled_types": round(precision_comparable, 4),
                "expected_hit_rate_at_k": round(hit_rate, 4),
                "expected_hit_rate_ceiling": round(
                    min(limit, len(expected)) / len(expected) if expected else 0.0, 4
                ),
                "ndcg_at_k": round(_ndcg(retrieved, expected), 4),
                "negative_violations": violations,
                "evidence_coverage": round(_evidence_coverage(response), 4),
                "full_traceability": round(_traceability(response), 4),
                "opportunities_valid": _opportunities_valid(response),
                "latency_ms": round(latencies[-1], 2),
            }
            if violations or not case_result["opportunities_valid"]:
                failed += 1
            results.append(case_result)

        summary = {
            "cases": len(results),
            "precision_at_k": round(_mean(item["precision_at_k"] for item in results), 4),
            "precision_at_k_labeled_types": round(
                _mean(item["precision_at_k_labeled_types"] for item in results), 4
            ),
            "expected_hit_rate_at_k": round(
                _mean(item["expected_hit_rate_at_k"] for item in results), 4
            ),
            "expected_hit_rate_ceiling": round(
                _mean(item["expected_hit_rate_ceiling"] for item in results), 4
            ),
            "ndcg_at_k": round(_mean(item["ndcg_at_k"] for item in results), 4),
            "evidence_coverage": round(_mean(item["evidence_coverage"] for item in results), 4),
            "full_traceability": round(_mean(item["full_traceability"] for item in results), 4),
            "opportunities_only_existing_ids": all(
                item["opportunities_valid"] for item in results
            ),
            "negative_violations": sum(len(item["negative_violations"]) for item in results),
            "failed_expectations": failed,
            "latency_ms_median": round(statistics.median(latencies), 2) if latencies else 0.0,
            "latency_ms_p95": round(_percentile(latencies, 95), 2) if latencies else 0.0,
        }
        return {
            "k": limit,
            "review_set_version": payload.get("review_set_version"),
            "disclaimer": payload.get("disclaimer"),
            "methodology": payload.get("methodology"),
            "metric_notes": {
                "precision_at_k": (
                    "Cota inferior: lo no etiquetado se considera desconocido, no irrelevante."
                ),
                "precision_at_k_labeled_types": (
                    "Precisión restringida a los tipos que la regla de etiquetado cubre."
                ),
                "expected_hit_rate_at_k": (
                    "Proporción de entidades etiquetadas recuperadas en el top-k; su "
                    "techo es min(k, etiquetas)/etiquetas, reportado aparte."
                ),
                "evidence_coverage": "Conexiones con al menos un elemento de evidencia.",
                "full_traceability": "Elementos de evidencia con archivo, fila, campo y fragmento.",
            },
            "engine": {
                "embedding_model": self._engine.health()["embedding_model"],
                "ranking_version": self._engine.health()["ranking_version"],
                "graph_backend": self._engine.health()["graph_backend"],
            },
            "summary": summary,
            "cases": results,
        }


def _mean(values: Any) -> float:
    collected = list(values)
    return sum(collected) / len(collected) if collected else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(math.ceil(percentile / 100 * len(ordered))) - 1)
    return ordered[max(0, index)]


def _ndcg(retrieved: list[str], expected: dict[str, int]) -> float:
    if not expected or not retrieved:
        return 0.0
    gains = [expected.get(identifier, 0) for identifier in retrieved]
    dcg = sum(
        (2**gain - 1) / math.log2(position + 2) for position, gain in enumerate(gains)
    )
    ideal_gains = sorted(expected.values(), reverse=True)[: len(retrieved)]
    idcg = sum(
        (2**gain - 1) / math.log2(position + 2) for position, gain in enumerate(ideal_gains)
    )
    return dcg / idcg if idcg else 0.0


def _evidence_coverage(response: dict[str, Any]) -> float:
    connections = response.get("connections") or []
    if not connections:
        return 0.0
    with_evidence = sum(1 for item in connections if item.get("evidence"))
    return with_evidence / len(connections)


def _traceability(response: dict[str, Any]) -> float:
    items = [item for connection in response.get("connections", []) for item in connection["evidence"]]
    if not items:
        return 0.0
    complete = sum(
        1
        for item in items
        if item.get("file") and item.get("row") is not None and item.get("field") and item.get("excerpt")
    )
    return complete / len(items)


def _opportunities_valid(response: dict[str, Any]) -> bool:
    """Toda oportunidad debe citar únicamente IDs presentes en la respuesta."""

    known = {str(item["target"]["id"]) for item in response.get("connections", [])}
    query_entity = response.get("query_entity") or {}
    if query_entity.get("id"):
        known.add(str(query_entity["id"]))
    for opportunity in response.get("opportunities", []):
        for entity in opportunity.get("related_entities", []):
            if str(entity.get("id")) not in known:
                return False
    return True
