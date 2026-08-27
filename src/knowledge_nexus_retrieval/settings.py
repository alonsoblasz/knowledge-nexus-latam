"""Configuración del motor: rutas, backend de grafo y modelo de embeddings.

Nada aquí lee ni escribe credenciales en disco: la conexión a Neo4j se resuelve
mediante variables de entorno que gestiona `knowledge_nexus_data`.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


CONFIG_MARKER = Path("config") / "ranking.yaml"


def find_project_root(start: Path | None = None) -> Path:
    """Localiza la raíz del proyecto buscando `config/ranking.yaml` hacia arriba."""

    override = os.environ.get("KNOWLEDGE_NEXUS_PROJECT_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    current = (start or Path(__file__)).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / CONFIG_MARKER).is_file():
            return candidate
    raise FileNotFoundError(
        "No se encontró config/ranking.yaml. Define KNOWLEDGE_NEXUS_PROJECT_ROOT."
    )


def _env(name: str, default: str) -> str:
    return os.environ.get(f"KNOWLEDGE_NEXUS_{name}", default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(f"KNOWLEDGE_NEXUS_{name}")
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    """Ajustes efectivos del motor de recuperación."""

    project_root: Path
    data_dir: Path
    config_dir: Path
    artifacts_dir: Path
    graph_backend: str = "jsonl"
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_device: str = "auto"
    embedding_batch_size: int = 16
    llm_provider: str = "template"
    request_timeout_seconds: int = 60
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        root = find_project_root()
        # Los exports de la capa de datos viven en `artifacts/generated/`.
        # Si no existe esa carpeta se usa la raíz, para no romper una checkout
        # con los JSONL sueltos.
        generated = root / "artifacts" / "generated"
        default_data_dir = generated if (generated / "semantic_documents.jsonl").is_file() else root
        data_dir = Path(_env("DATA_DIR", str(default_data_dir))).expanduser()
        artifacts_dir = Path(_env("ARTIFACTS_DIR", str(root / "artifacts"))).expanduser()
        return cls(
            project_root=root,
            data_dir=data_dir,
            config_dir=Path(_env("CONFIG_DIR", str(root / "config"))).expanduser(),
            artifacts_dir=artifacts_dir,
            graph_backend=_env("GRAPH_BACKEND", "jsonl").strip().lower(),
            embedding_provider=_env("EMBEDDING_PROVIDER", "sentence-transformers"),
            embedding_model=_env("EMBEDDING_MODEL", "BAAI/bge-m3"),
            embedding_dimension=_env_int("EMBEDDING_DIMENSION", 1024),
            embedding_device=_env("EMBEDDING_DEVICE", "auto"),
            embedding_batch_size=_env_int("EMBEDDING_BATCH_SIZE", 16),
            llm_provider=_env("LLM_PROVIDER", "template"),
            request_timeout_seconds=_env_int("REQUEST_TIMEOUT_SECONDS", 60),
        )

    # Rutas de artefactos ------------------------------------------------
    @property
    def semantic_documents_path(self) -> Path:
        return self.data_dir / "semantic_documents.jsonl"

    @property
    def graph_nodes_path(self) -> Path:
        return self.data_dir / "graph_nodes.jsonl"

    @property
    def graph_edges_path(self) -> Path:
        return self.data_dir / "graph_edges.jsonl"

    @property
    def dataset_manifest_path(self) -> Path:
        return self.data_dir / "manifest.json"

    @property
    def embeddings_dir(self) -> Path:
        return self.artifacts_dir / "embeddings"

    @property
    def embeddings_path(self) -> Path:
        return self.embeddings_dir / "semantic_embeddings.jsonl"

    @property
    def embeddings_manifest_path(self) -> Path:
        return self.embeddings_dir / "embeddings_manifest.json"

    @property
    def evaluation_dir(self) -> Path:
        return self.artifacts_dir / "evaluation"

    def config_path(self, name: str) -> Path:
        return self.config_dir / name


def load_yaml_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"El archivo de configuración {path} debe contener un mapeo")
    return loaded


@dataclass(frozen=True)
class EngineConfig:
    """Configuración declarativa cargada desde `config/`."""

    ranking: dict[str, Any]
    entity_profiles: dict[str, Any]
    relation_rules: dict[str, Any]
    lexicon: dict[str, Any]

    @classmethod
    def load(cls, settings: Settings) -> "EngineConfig":
        return cls(
            ranking=load_yaml_config(settings.config_path("ranking.yaml")),
            entity_profiles=load_yaml_config(settings.config_path("entity_profiles.yaml")),
            relation_rules=load_yaml_config(settings.config_path("relation_rules.yaml")),
            lexicon=load_yaml_config(settings.config_path("lexicon.yaml")),
        )

    @property
    def ranking_version(self) -> str:
        return str(self.ranking.get("version", "unknown"))

    def profile(self, entity_type: str | None) -> dict[str, Any]:
        """Perfil de un tipo de entidad, completado con los valores por defecto."""

        defaults = dict(self.entity_profiles.get("defaults", {}))
        profiles = self.entity_profiles.get("profiles", {})
        specific = dict(profiles.get(entity_type or "", {}))
        defaults.update(specific)
        return defaults

    @property
    def anchor_fields(self) -> tuple[str, ...]:
        return tuple(self.entity_profiles.get("institutional_anchor_fields", ()))


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


@functools.lru_cache(maxsize=1)
def get_engine_config() -> EngineConfig:
    return EngineConfig.load(get_settings())
