"""Utilidades compartidas por las pruebas."""

from __future__ import annotations

import copy

from knowledge_nexus_retrieval.engine import KnowledgeNexusEngine
from knowledge_nexus_retrieval.settings import EngineConfig

DEMO_QUERY = "¿Qué nueva investigación puede ayudar a prevenir la deserción estudiantil?"


def engine_with_config(engine: KnowledgeNexusEngine, **ranking_overrides) -> KnowledgeNexusEngine:
    """Clona un motor cambiando solo la configuración del ranking."""

    config = EngineConfig(
        ranking=copy.deepcopy(engine._config.ranking),  # noqa: SLF001
        entity_profiles=engine._config.entity_profiles,  # noqa: SLF001
        relation_rules=copy.deepcopy(engine._config.relation_rules),  # noqa: SLF001
        lexicon=engine._config.lexicon,  # noqa: SLF001
    )
    for section, values in ranking_overrides.items():
        config.ranking.setdefault(section, {}).update(values)
    return KnowledgeNexusEngine(
        engine._settings,  # noqa: SLF001
        config,
        engine._corpus,  # noqa: SLF001
        engine._graph,  # noqa: SLF001
        engine._store,  # noqa: SLF001
        engine._provider,  # noqa: SLF001
    )
