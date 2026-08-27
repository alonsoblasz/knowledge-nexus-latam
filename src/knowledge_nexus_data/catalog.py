"""Catálogo canónico de archivos, entidades y relaciones de Data V1.0."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeSpec:
    key: str
    relative_path: str
    label: str
    id_field: str
    title_field: str
    semantic_fields: tuple[str, ...]
    semantic: bool = True


@dataclass(frozen=True)
class ForeignKeySpec:
    source_key: str
    source_field: str
    target_key: str
    relationship: str
    reverse: bool = False


@dataclass(frozen=True)
class RelationFileSpec:
    relative_path: str
    source_key: str
    source_field: str
    target_key: str
    target_field: str
    relationship: str
    property_fields: tuple[str, ...] = ()


NODE_SPECS: tuple[NodeSpec, ...] = (
    NodeSpec(
        "faculties",
        "01_institution/faculties.csv",
        "Faculty",
        "faculty_id",
        "faculty_name",
        ("faculty_name", "description", "strategic_focus"),
    ),
    NodeSpec(
        "programs",
        "01_institution/programs.csv",
        "Program",
        "program_id",
        "program_name",
        (
            "program_name",
            "description",
            "disciplinary_area",
            "graduate_profile",
            "strategic_topics",
        ),
    ),
    NodeSpec(
        "research_groups",
        "01_institution/research_groups.csv",
        "ResearchGroup",
        "group_id",
        "group_name",
        ("group_name", "description", "mission", "main_area"),
    ),
    NodeSpec(
        "research_lines",
        "01_institution/research_lines.csv",
        "ResearchLine",
        "line_id",
        "line_name",
        ("line_name", "description", "keywords"),
    ),
    NodeSpec(
        "institutional_capabilities",
        "01_institution/institutional_capabilities.csv",
        "Capability",
        "capability_id",
        "capability_name",
        (
            "capability_name",
            "capability_type",
            "description",
            "available_resources",
            "application_domains",
            "maturity_level",
        ),
    ),
    NodeSpec(
        "source_catalog",
        "01_institution/source_catalog.csv",
        "Source",
        "source_id",
        "file_name",
        ("file_name", "source_type", "institutional_unit", "description", "reliability_level"),
        semantic=False,
    ),
    NodeSpec(
        "researchers",
        "02_people_curriculum/researchers.csv",
        "Researcher",
        "researcher_id",
        "full_name",
        (
            "full_name",
            "academic_background",
            "profile_summary",
            "research_interests",
            "methodological_expertise",
            "application_domains",
        ),
    ),
    NodeSpec(
        "researcher_expertise",
        "02_people_curriculum/researcher_expertise.csv",
        "Expertise",
        "expertise_id",
        "expertise_name",
        ("expertise_name", "expertise_type", "proficiency_level", "evidence_source"),
    ),
    NodeSpec(
        "subjects",
        "02_people_curriculum/subjects.csv",
        "Subject",
        "subject_id",
        "subject_name",
        ("subject_name", "description", "purpose", "main_topics", "disciplinary_area"),
    ),
    NodeSpec(
        "competencies",
        "02_people_curriculum/competencies.csv",
        "Competency",
        "competency_id",
        "description",
        ("competency_type", "description"),
    ),
    NodeSpec(
        "learning_outcomes",
        "02_people_curriculum/learning_outcomes.csv",
        "LearningOutcome",
        "outcome_id",
        "outcome_description",
        ("outcome_description", "cognitive_level", "evidence_type"),
    ),
    NodeSpec(
        "institutional_needs",
        "03_knowledge_needs/institutional_needs.csv",
        "InstitutionalNeed",
        "need_id",
        "title",
        ("title", "description", "context", "expected_impact", "priority"),
    ),
    NodeSpec(
        "projects",
        "03_knowledge_needs/projects.csv",
        "Project",
        "project_id",
        "title",
        (
            "title",
            "problem_statement",
            "abstract",
            "general_objective",
            "methodology",
            "expected_results",
            "application_context",
            "keywords",
            "disciplinary_area",
        ),
    ),
    NodeSpec(
        "theses",
        "03_knowledge_needs/theses.csv",
        "Thesis",
        "thesis_id",
        "title",
        (
            "title",
            "abstract",
            "problem_statement",
            "general_objective",
            "methodology",
            "main_results",
            "conclusions",
            "keywords",
            "research_area",
            "application_context",
            "data_or_population",
        ),
    ),
    NodeSpec(
        "publications",
        "03_knowledge_needs/publications.csv",
        "Publication",
        "publication_id",
        "title",
        ("title", "abstract", "keywords", "publication_type", "journal_or_event"),
    ),
)

NODE_SPEC_BY_KEY = {spec.key: spec for spec in NODE_SPECS}
NODE_SPEC_BY_LABEL = {spec.label: spec for spec in NODE_SPECS}


FOREIGN_KEYS: tuple[ForeignKeySpec, ...] = (
    ForeignKeySpec("programs", "faculty_id", "faculties", "BELONGS_TO_FACULTY"),
    ForeignKeySpec("research_groups", "faculty_id", "faculties", "BELONGS_TO_FACULTY"),
    ForeignKeySpec("research_lines", "group_id", "research_groups", "BELONGS_TO_GROUP"),
    ForeignKeySpec("researchers", "faculty_id", "faculties", "BELONGS_TO_FACULTY"),
    ForeignKeySpec("researchers", "primary_program_id", "programs", "PRIMARY_PROGRAM"),
    ForeignKeySpec(
        "researcher_expertise",
        "researcher_id",
        "researchers",
        "HAS_EXPERTISE",
        reverse=True,
    ),
    ForeignKeySpec("subjects", "program_id", "programs", "BELONGS_TO_PROGRAM"),
    ForeignKeySpec("competencies", "program_id", "programs", "BELONGS_TO_PROGRAM"),
    ForeignKeySpec(
        "competencies",
        "subject_id",
        "subjects",
        "DEVELOPS_COMPETENCY",
        reverse=True,
    ),
    ForeignKeySpec(
        "learning_outcomes",
        "subject_id",
        "subjects",
        "HAS_LEARNING_OUTCOME",
        reverse=True,
    ),
    ForeignKeySpec("projects", "faculty_id", "faculties", "BELONGS_TO_FACULTY"),
    ForeignKeySpec("projects", "program_id", "programs", "BELONGS_TO_PROGRAM"),
    ForeignKeySpec("projects", "group_id", "research_groups", "EXECUTED_BY_GROUP"),
    ForeignKeySpec("theses", "program_id", "programs", "BELONGS_TO_PROGRAM"),
    ForeignKeySpec(
        "publications",
        "related_project_id",
        "projects",
        "DERIVED_FROM_PROJECT",
    ),
)


RELATION_FILE_SPECS: tuple[RelationFileSpec, ...] = (
    RelationFileSpec(
        "02_people_curriculum/researcher_group.csv",
        "researchers",
        "researcher_id",
        "research_groups",
        "group_id",
        "MEMBER_OF_GROUP",
        ("role",),
    ),
    RelationFileSpec(
        "03_knowledge_needs/researcher_project.csv",
        "researchers",
        "researcher_id",
        "projects",
        "project_id",
        "PARTICIPATED_IN_PROJECT",
        ("role",),
    ),
    RelationFileSpec(
        "03_knowledge_needs/project_group.csv",
        "projects",
        "project_id",
        "research_groups",
        "group_id",
        "EXECUTED_BY_GROUP",
        ("relation",),
    ),
    RelationFileSpec(
        "03_knowledge_needs/thesis_advisor.csv",
        "researchers",
        "researcher_id",
        "theses",
        "thesis_id",
        "ADVISED_THESIS",
        ("role",),
    ),
    RelationFileSpec(
        "03_knowledge_needs/publication_researcher.csv",
        "researchers",
        "researcher_id",
        "publications",
        "publication_id",
        "AUTHORED_PUBLICATION",
        ("role",),
    ),
    RelationFileSpec(
        "03_knowledge_needs/publication_project.csv",
        "publications",
        "publication_id",
        "projects",
        "project_id",
        "DERIVED_FROM_PROJECT",
        ("relation",),
    ),
)


INTEGER_FIELDS = {
    "creation_year",
    "start_year",
    "end_year",
    "year",
    "graduation_year",
    "update_year",
    "semester",
    "credits",
    "years_experience",
    "maturity_level",
    "proficiency_level",
}

BOOLEAN_FIELDS = {"active", "interdisciplinary"}

LIST_FIELDS = {
    "strategic_topics",
    "keywords",
    "available_resources",
    "application_domains",
    "research_interests",
    "methodological_expertise",
    "main_topics",
}


DOCUMENT_ENTITY_KEYS = {
    "NEED": "institutional_needs",
    "PROJECT": "projects",
    "THESIS": "theses",
}

