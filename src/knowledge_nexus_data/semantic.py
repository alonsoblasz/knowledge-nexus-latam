"""Construcción de documentos semánticos auditables por entidad."""

from __future__ import annotations

from collections.abc import Mapping

from .catalog import NodeSpec


FIELD_LABELS = {
    "faculty_name": "Facultad",
    "program_name": "Programa",
    "group_name": "Grupo",
    "line_name": "Línea",
    "capability_name": "Capacidad",
    "capability_type": "Tipo de capacidad",
    "full_name": "Investigador",
    "expertise_name": "Expertise",
    "expertise_type": "Tipo de expertise",
    "subject_name": "Asignatura",
    "title": "Título",
    "description": "Descripción",
    "problem_statement": "Problema",
    "abstract": "Resumen",
    "general_objective": "Objetivo",
    "methodology": "Metodología",
    "expected_results": "Resultados esperados",
    "main_results": "Resultados principales",
    "conclusions": "Conclusiones",
    "context": "Contexto",
    "expected_impact": "Impacto esperado",
    "priority": "Prioridad",
    "application_context": "Contexto de aplicación",
    "application_domains": "Dominios de aplicación",
    "disciplinary_area": "Área disciplinar",
    "research_area": "Área de investigación",
    "research_interests": "Intereses de investigación",
    "methodological_expertise": "Expertise metodológico",
    "academic_background": "Formación académica",
    "profile_summary": "Perfil",
    "graduate_profile": "Perfil de egreso",
    "strategic_topics": "Temas estratégicos",
    "main_topics": "Temas principales",
    "purpose": "Propósito",
    "keywords": "Palabras clave",
    "available_resources": "Recursos disponibles",
    "maturity_level": "Nivel de madurez",
    "competency_type": "Tipo de competencia",
    "outcome_description": "Resultado de aprendizaje",
    "cognitive_level": "Nivel cognitivo",
    "evidence_type": "Tipo de evidencia",
    "publication_type": "Tipo de publicación",
    "journal_or_event": "Revista o evento",
    "data_or_population": "Datos o población",
    "evidence_source": "Fuente de evidencia",
    "proficiency_level": "Nivel de dominio",
}


def build_semantic_text(spec: NodeSpec, row: Mapping[str, str]) -> str:
    """Genera texto etiquetado; no mezcla silenciosamente el significado de los campos."""

    parts: list[str] = []
    for field in spec.semantic_fields:
        raw_value = row.get(field)
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if not value:
            continue
        label = FIELD_LABELS.get(field, field.replace("_", " ").capitalize())
        parts.append(f"{label}: {value}")
    return "\n".join(parts)

