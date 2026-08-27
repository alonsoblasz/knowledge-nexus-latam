"""Lectura tipada y reproducible del dataset oficial."""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from .catalog import BOOLEAN_FIELDS, INTEGER_FIELDS, LIST_FIELDS, NODE_SPECS, NodeSpec


DEFAULT_DATASET_DIRECTORY = "KNOWLEDGE_NEXUS_LATAM_DATA_V1_RC2_PARTICIPANTS"


def discover_data_root(start: Path | None = None) -> Path:
    """Localiza el directorio que contiene los tres bloques de Data V1.0."""

    env_value = os.getenv("KNOWLEDGE_NEXUS_DATA_ROOT", "").strip()
    if env_value:
        candidate = Path(env_value).expanduser().resolve()
        _assert_data_root(candidate)
        return candidate

    base = (start or Path.cwd()).resolve()
    direct = base / DEFAULT_DATASET_DIRECTORY
    if direct.is_dir():
        _assert_data_root(direct)
        return direct

    matches = [
        path
        for path in base.glob("**/KNOWLEDGE_NEXUS_LATAM_DATA_V1_RC2_PARTICIPANTS")
        if path.is_dir()
    ]
    if len(matches) == 1:
        candidate = matches[0].resolve()
        _assert_data_root(candidate)
        return candidate
    if not matches:
        raise FileNotFoundError(
            "No se encontró Data V1.0. Define KNOWLEDGE_NEXUS_DATA_ROOT o ejecuta "
            "el comando desde el repositorio que contiene el dataset."
        )
    raise RuntimeError(
        "Se encontraron varias copias del dataset. Define KNOWLEDGE_NEXUS_DATA_ROOT "
        "para seleccionar una de forma explícita."
    )


def _assert_data_root(path: Path) -> None:
    required = ("01_institution", "02_people_curriculum", "03_knowledge_needs")
    missing = [name for name in required if not (path / name).is_dir()]
    if missing:
        raise ValueError(f"La ruta no es una raíz válida de Data V1.0; faltan: {missing}")


def normalize_value(field: str, value: str | None) -> Any:
    """Convierte texto CSV a propiedades compatibles con Neo4j."""

    if value is None:
        return None
    cleaned = value.strip()
    if cleaned == "":
        return None
    if field in BOOLEAN_FIELDS:
        lowered = cleaned.lower()
        if lowered in {"true", "1", "yes", "sí", "si"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
        return cleaned
    if field in INTEGER_FIELDS:
        try:
            return int(cleaned)
        except ValueError:
            return cleaned
    if field in LIST_FIELDS:
        return [item.strip() for item in cleaned.split(";") if item.strip()]
    return cleaned


class DatasetRepository:
    """Acceso de solo lectura a Data V1.0."""

    def __init__(self, data_root: Path):
        self.data_root = data_root.resolve()
        _assert_data_root(self.data_root)
        self._cache: dict[str, list[dict[str, str]]] = {}

    @classmethod
    def discover(cls, start: Path | None = None) -> "DatasetRepository":
        return cls(discover_data_root(start))

    def path(self, relative_path: str) -> Path:
        return self.data_root / Path(relative_path)

    def read_csv(self, relative_path: str) -> list[dict[str, str]]:
        if relative_path not in self._cache:
            file_path = self.path(relative_path)
            with file_path.open("r", encoding="utf-8-sig", newline="") as stream:
                self._cache[relative_path] = [dict(row) for row in csv.DictReader(stream)]
        return self._cache[relative_path]

    def read_nodes(self, spec: NodeSpec) -> list[dict[str, str]]:
        return self.read_csv(spec.relative_path)

    def normalized_properties(self, row: Mapping[str, str]) -> dict[str, Any]:
        return {
            field: normalized
            for field, raw_value in row.items()
            if (normalized := normalize_value(field, raw_value)) is not None
        }

    def iter_all_node_rows(self) -> Iterator[tuple[NodeSpec, int, dict[str, str]]]:
        for spec in NODE_SPECS:
            for row_number, row in enumerate(self.read_nodes(spec), start=2):
                yield spec, row_number, row

    def manifests(self) -> Iterable[tuple[Path, dict[str, Any]]]:
        for path in sorted(self.data_root.glob("**/dataset_manifest*.json")):
            with path.open("r", encoding="utf-8") as stream:
                yield path, json.load(stream)

