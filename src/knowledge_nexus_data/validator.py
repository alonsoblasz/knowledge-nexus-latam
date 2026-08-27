"""Validación de estructura, conteos e integridad referencial de Data V1.0."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .catalog import (
    DOCUMENT_ENTITY_KEYS,
    FOREIGN_KEYS,
    NODE_SPEC_BY_KEY,
    NODE_SPECS,
    RELATION_FILE_SPECS,
)
from .repository import DatasetRepository


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    file: str | None = None
    row: int | None = None


@dataclass
class ValidationReport:
    data_root: str
    counts: dict[str, int] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "ERROR"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "WARNING"]

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_root": self.data_root,
            "valid": self.valid,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "files": len(self.counts),
                "records": sum(self.counts.values()),
            },
            "counts": self.counts,
            "issues": [asdict(issue) for issue in self.issues],
        }


def validate_dataset(repository: DatasetRepository) -> ValidationReport:
    report = ValidationReport(data_root=str(repository.data_root))
    ids_by_key: dict[str, set[str]] = {}

    for spec in NODE_SPECS:
        path = repository.path(spec.relative_path)
        if not path.is_file():
            report.issues.append(
                ValidationIssue("ERROR", "MISSING_FILE", "Archivo requerido ausente", spec.relative_path)
            )
            ids_by_key[spec.key] = set()
            continue

        rows = repository.read_nodes(spec)
        report.counts[spec.key] = len(rows)
        if not rows:
            report.issues.append(
                ValidationIssue("ERROR", "EMPTY_FILE", "El archivo no contiene registros", spec.relative_path)
            )
            ids_by_key[spec.key] = set()
            continue

        headers = set(rows[0])
        required = {spec.id_field, spec.title_field, *spec.semantic_fields}
        missing_headers = sorted(required - headers)
        if missing_headers:
            report.issues.append(
                ValidationIssue(
                    "ERROR",
                    "MISSING_COLUMNS",
                    f"Faltan columnas requeridas: {missing_headers}",
                    spec.relative_path,
                )
            )

        seen: set[str] = set()
        for row_number, row in enumerate(rows, start=2):
            identifier = row.get(spec.id_field, "").strip()
            if not identifier:
                report.issues.append(
                    ValidationIssue(
                        "ERROR",
                        "MISSING_ID",
                        f"{spec.id_field} está vacío",
                        spec.relative_path,
                        row_number,
                    )
                )
                continue
            if identifier in seen:
                report.issues.append(
                    ValidationIssue(
                        "ERROR",
                        "DUPLICATE_ID",
                        f"ID duplicado: {identifier}",
                        spec.relative_path,
                        row_number,
                    )
                )
            seen.add(identifier)
        ids_by_key[spec.key] = seen

    _validate_manifest_counts(repository, report)
    _validate_direct_foreign_keys(repository, report, ids_by_key)
    _validate_relation_files(repository, report, ids_by_key)
    _validate_documents(repository, report, ids_by_key)
    return report


def _validate_manifest_counts(repository: DatasetRepository, report: ValidationReport) -> None:
    for manifest_path, manifest in repository.manifests():
        for key, expected in manifest.get("record_counts", {}).items():
            if key == "documents":
                actual = len(
                    repository.read_csv("03_knowledge_needs/document_catalog.csv")
                )
            elif key in report.counts:
                actual = report.counts[key]
            else:
                relation = next(
                    (
                        spec
                        for spec in RELATION_FILE_SPECS
                        if Path(spec.relative_path).stem == key
                    ),
                    None,
                )
                actual = len(repository.read_csv(relation.relative_path)) if relation else None
            if actual is None:
                report.issues.append(
                    ValidationIssue(
                        "WARNING",
                        "UNMAPPED_MANIFEST_COUNT",
                        f"No se pudo comprobar el conteo declarado para {key}",
                        str(manifest_path.relative_to(repository.data_root)),
                    )
                )
            elif actual != expected:
                report.issues.append(
                    ValidationIssue(
                        "ERROR",
                        "COUNT_MISMATCH",
                        f"{key}: manifiesto={expected}, archivo={actual}",
                        str(manifest_path.relative_to(repository.data_root)),
                    )
                )


def _validate_direct_foreign_keys(
    repository: DatasetRepository,
    report: ValidationReport,
    ids_by_key: dict[str, set[str]],
) -> None:
    for foreign_key in FOREIGN_KEYS:
        source_spec = NODE_SPEC_BY_KEY[foreign_key.source_key]
        valid_targets = ids_by_key[foreign_key.target_key]
        for row_number, row in enumerate(repository.read_nodes(source_spec), start=2):
            target_id = row.get(foreign_key.source_field, "").strip()
            if not target_id:
                continue
            if target_id not in valid_targets:
                report.issues.append(
                    ValidationIssue(
                        "ERROR",
                        "BROKEN_FOREIGN_KEY",
                        f"{foreign_key.source_field}={target_id} no existe en {foreign_key.target_key}",
                        source_spec.relative_path,
                        row_number,
                    )
                )


def _validate_relation_files(
    repository: DatasetRepository,
    report: ValidationReport,
    ids_by_key: dict[str, set[str]],
) -> None:
    for spec in RELATION_FILE_SPECS:
        path = repository.path(spec.relative_path)
        if not path.is_file():
            report.issues.append(
                ValidationIssue("ERROR", "MISSING_FILE", "Archivo de relación ausente", spec.relative_path)
            )
            continue
        rows = repository.read_csv(spec.relative_path)
        report.counts[Path(spec.relative_path).stem] = len(rows)
        seen: set[tuple[str, str]] = set()
        for row_number, row in enumerate(rows, start=2):
            source_id = row.get(spec.source_field, "").strip()
            target_id = row.get(spec.target_field, "").strip()
            pair = (source_id, target_id)
            if pair in seen:
                report.issues.append(
                    ValidationIssue(
                        "WARNING",
                        "DUPLICATE_RELATION",
                        f"Relación repetida: {source_id} -> {target_id}",
                        spec.relative_path,
                        row_number,
                    )
                )
            seen.add(pair)
            if source_id not in ids_by_key[spec.source_key]:
                report.issues.append(
                    ValidationIssue(
                        "ERROR",
                        "BROKEN_RELATION_SOURCE",
                        f"Origen inexistente: {source_id}",
                        spec.relative_path,
                        row_number,
                    )
                )
            if target_id not in ids_by_key[spec.target_key]:
                report.issues.append(
                    ValidationIssue(
                        "ERROR",
                        "BROKEN_RELATION_TARGET",
                        f"Destino inexistente: {target_id}",
                        spec.relative_path,
                        row_number,
                    )
                )


def _validate_documents(
    repository: DatasetRepository,
    report: ValidationReport,
    ids_by_key: dict[str, set[str]],
) -> None:
    relative_path = "03_knowledge_needs/document_catalog.csv"
    rows = repository.read_csv(relative_path)
    report.counts["documents"] = len(rows)
    for row_number, row in enumerate(rows, start=2):
        entity_type = row.get("entity_type", "").strip()
        entity_key = DOCUMENT_ENTITY_KEYS.get(entity_type)
        if entity_key is None:
            report.issues.append(
                ValidationIssue(
                    "ERROR",
                    "UNKNOWN_DOCUMENT_ENTITY_TYPE",
                    f"Tipo documental desconocido: {entity_type}",
                    relative_path,
                    row_number,
                )
            )
            continue
        entity_id = row.get("entity_id", "").strip()
        if entity_id not in ids_by_key[entity_key]:
            report.issues.append(
                ValidationIssue(
                    "ERROR",
                    "BROKEN_DOCUMENT_ENTITY",
                    f"Entidad documental inexistente: {entity_id}",
                    relative_path,
                    row_number,
                )
            )
        document_path = repository.path(
            f"03_knowledge_needs/documents/{row.get('file_name', '').strip()}"
        )
        if not document_path.is_file():
            report.issues.append(
                ValidationIssue(
                    "ERROR",
                    "MISSING_DOCUMENT",
                    f"Documento ausente: {document_path.name}",
                    relative_path,
                    row_number,
                )
            )

