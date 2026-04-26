from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from media_offline_database.contracts import (
    CORE_SCHEMA_VERSION,
    CORE_TABLE_CONTRACTS,
    PROFILE_TABLE_CONTRACTS,
    TableContract,
)
from media_offline_database.publishability import validate_current_manifest_publishability
from media_offline_database.sources import SourceRole
from media_offline_database.v1_artifact import V1_ARTIFACT

ReleaseReadinessSeverity = Literal["error", "warning"]

REQUIRED_V1_TABLES = {
    "entities",
    "titles",
    "external_ids",
    "relationships",
    "relationship_evidence",
    "facets",
    "provenance",
    "source_records",
    "anime_profile",
    "tv_profile",
    "movie_profile",
}
REQUIRED_V1_DOMAINS = {"anime", "tv", "movie"}
REQUIRED_V1_SOURCES = {"manami", "tvmaze", "wikidata"}
REQUIRED_NON_EMPTY_TABLES = {
    "entities",
    "titles",
    "external_ids",
    "provenance",
    "source_records",
    "anime_profile",
    "tv_profile",
    "movie_profile",
}
PUBLIC_RELEASE_SOURCE_ROLES = {
    SourceRole.BACKBONE_SOURCE.value,
    SourceRole.ID_SOURCE.value,
}


class ReleaseReadinessFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: ReleaseReadinessSeverity
    code: str
    message: str
    table: str | None = None


def _empty_findings() -> list[ReleaseReadinessFinding]:
    return []


class ReleaseReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_path: str
    artifact: str | None
    ready: bool
    findings: list[ReleaseReadinessFinding] = Field(default_factory=_empty_findings)


class ReleaseReadinessError(ValueError):
    """Raised when an artifact bundle is not ready for release materialization."""


def validate_release_readiness(manifest_path: Path) -> ReleaseReadinessReport:
    manifest = _load_manifest(manifest_path)
    artifact = _string_value(manifest.get("artifact"))
    findings: list[ReleaseReadinessFinding] = []

    if artifact == V1_ARTIFACT:
        findings.extend(_validate_v1_release_readiness(manifest_path, manifest))

    return ReleaseReadinessReport(
        manifest_path=str(manifest_path),
        artifact=artifact,
        ready=not any(finding.severity == "error" for finding in findings),
        findings=findings,
    )


def assert_release_readiness_if_applicable(manifest_path: Path) -> None:
    report = validate_release_readiness(manifest_path)
    if report.ready:
        return

    errors = [finding for finding in report.findings if finding.severity == "error"]
    message = "; ".join(f"{finding.code}: {finding.message}" for finding in errors)
    raise ReleaseReadinessError(message)


def _load_manifest(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _validate_v1_release_readiness(
    manifest_path: Path,
    manifest: Mapping[str, Any],
) -> list[ReleaseReadinessFinding]:
    findings: list[ReleaseReadinessFinding] = []
    try:
        validate_current_manifest_publishability(manifest)
    except ValueError as error:
        findings.append(
            _error(
                "publishability_invalid",
                f"Manifest is not validated with current publishability policy: {error}",
            )
        )

    findings.extend(_validate_v1_identity(manifest))
    table_entries = _entries_by_name(manifest.get("tables"), key_name="table_name")
    file_entries = _entries_by_name(manifest.get("files"), key_name="path")
    findings.extend(_validate_required_tables(table_entries))
    findings.extend(_validate_source_coverage(manifest))

    contracts = {**CORE_TABLE_CONTRACTS, **PROFILE_TABLE_CONTRACTS}
    frames: dict[str, pl.DataFrame] = {}
    for table_name in sorted(REQUIRED_V1_TABLES & set(table_entries)):
        contract = contracts[table_name]
        table_entry = table_entries[table_name]
        findings.extend(
            _validate_table_entry(
                manifest_path=manifest_path,
                table_name=table_name,
                table_entry=table_entry,
                file_entries=file_entries,
                contract=contract,
                frames=frames,
            )
        )

    findings.extend(_validate_cross_domain_rows(frames))
    return findings


def _validate_v1_identity(manifest: Mapping[str, Any]) -> list[ReleaseReadinessFinding]:
    findings: list[ReleaseReadinessFinding] = []
    if manifest.get("artifact") != V1_ARTIFACT:
        findings.append(_error("artifact_mismatch", "Manifest artifact is not media-metadata-v1."))
    if manifest.get("dataset_line") != V1_ARTIFACT:
        findings.append(
            _error("dataset_line_mismatch", "Manifest dataset_line is not media-metadata-v1.")
        )
    if manifest.get("core_schema_version") != CORE_SCHEMA_VERSION:
        findings.append(
            _error("core_schema_version_mismatch", "Manifest core schema version is not current.")
        )
    if not isinstance(manifest.get("dataset_version"), str) or not manifest["dataset_version"]:
        findings.append(_error("dataset_version_missing", "Manifest dataset_version is missing."))

    domains = _string_set(manifest.get("domains"))
    missing_domains = REQUIRED_V1_DOMAINS - domains
    if missing_domains:
        findings.append(
            _error(
                "required_domains_missing",
                f"Manifest domains are missing: {', '.join(sorted(missing_domains))}.",
            )
        )
    return findings


def _validate_required_tables(
    table_entries: Mapping[str, Mapping[str, Any]],
) -> list[ReleaseReadinessFinding]:
    missing = REQUIRED_V1_TABLES - set(table_entries)
    if not missing:
        return []
    return [
        _error(
            "required_tables_missing",
            f"Manifest tables are missing: {', '.join(sorted(missing))}.",
        )
    ]


def _validate_source_coverage(manifest: Mapping[str, Any]) -> list[ReleaseReadinessFinding]:
    findings: list[ReleaseReadinessFinding] = []
    raw_coverage = manifest.get("source_coverage")
    if not isinstance(raw_coverage, list):
        return [_error("source_coverage_missing", "Manifest source_coverage is missing.")]

    source_ids: set[str] = set()
    for raw_entry in cast(list[object], raw_coverage):
        if not isinstance(raw_entry, dict):
            findings.append(_error("source_coverage_invalid", "Source coverage entry is not an object."))
            continue
        entry = cast(dict[str, Any], raw_entry)
        source_id = _string_value(entry.get("source_id"))
        if source_id is None:
            findings.append(_error("source_coverage_invalid", "Source coverage entry lacks source_id."))
            continue
        source_ids.add(source_id)
        snapshot_id = _string_value(entry.get("source_snapshot_id"))
        if snapshot_id is None or snapshot_id.endswith(":unspecified"):
            findings.append(
                _error(
                    "source_snapshot_unspecified",
                    f"Source {source_id} has no release-grade source_snapshot_id.",
                )
            )
        source_role = _string_value(entry.get("source_role"))
        if source_role not in PUBLIC_RELEASE_SOURCE_ROLES:
            findings.append(
                _error(
                    "source_role_not_public",
                    f"Source {source_id} has non-public release role {source_role}.",
                )
            )

    missing_sources = REQUIRED_V1_SOURCES - source_ids
    if missing_sources:
        findings.append(
            _error(
                "required_sources_missing",
                f"Source coverage is missing: {', '.join(sorted(missing_sources))}.",
            )
        )
    return findings


def _validate_table_entry(
    *,
    manifest_path: Path,
    table_name: str,
    table_entry: Mapping[str, Any],
    file_entries: Mapping[str, Mapping[str, Any]],
    contract: TableContract,
    frames: dict[str, pl.DataFrame],
) -> list[ReleaseReadinessFinding]:
    findings: list[ReleaseReadinessFinding] = []
    table_path_value = _string_value(table_entry.get("path"))
    if table_path_value is None:
        return [_error("table_path_missing", "Manifest table entry has no path.", table_name)]

    if table_path_value not in file_entries:
        findings.append(
            _error(
                "table_file_missing_from_manifest",
                "Manifest table path has no matching files[] entry.",
                table_name,
            )
        )

    path_error = _path_error(table_path_value)
    if path_error is not None:
        return [_error("table_path_invalid", path_error, table_name)]

    table_path = manifest_path.parent / table_path_value
    if not table_path.exists():
        return [_error("table_file_missing", f"Parquet file does not exist: {table_path_value}.", table_name)]

    if table_entry.get("schema_version") != contract.schema_version:
        findings.append(
            _error("schema_version_mismatch", "Manifest table schema version mismatches contract.", table_name)
        )
    if table_entry.get("compatibility_tier") != contract.compatibility_tier.value:
        findings.append(
            _error("compatibility_tier_mismatch", "Manifest table tier mismatches contract.", table_name)
        )

    try:
        frame = pl.read_parquet(table_path)
    except Exception as error:
        return [_error("parquet_read_failed", f"Could not read table parquet: {error}", table_name)]

    frames[table_name] = frame
    expected_columns = [column.name for column in contract.columns]
    if frame.columns != expected_columns:
        findings.append(
            _error(
                "columns_mismatch",
                "Parquet columns do not exactly match the table contract.",
                table_name,
            )
        )

    row_count = table_entry.get("row_count")
    if not isinstance(row_count, int) or row_count != frame.height:
        findings.append(
            _error("row_count_mismatch", "Manifest row_count does not match Parquet rows.", table_name)
        )
    if table_name in REQUIRED_NON_EMPTY_TABLES and frame.height == 0:
        findings.append(_error("table_empty", "Required v1 release table is empty.", table_name))

    for column in contract.columns:
        if column.nullable or column.name not in frame.columns:
            continue
        if frame.get_column(column.name).null_count() > 0:
            findings.append(
                _error(
                    "required_column_null",
                    f"Required column {column.name} contains null values.",
                    table_name,
                )
            )
    return findings


def _validate_cross_domain_rows(frames: Mapping[str, pl.DataFrame]) -> list[ReleaseReadinessFinding]:
    required_frames = {
        "entities",
        "titles",
        "external_ids",
        "source_records",
        "anime_profile",
        "tv_profile",
        "movie_profile",
    }
    if not required_frames.issubset(frames):
        return []

    findings: list[ReleaseReadinessFinding] = []
    entities = frames["entities"]
    titles = frames["titles"]
    external_ids = frames["external_ids"]
    source_records = frames["source_records"]
    profile_frames = {
        "anime": frames["anime_profile"],
        "tv": frames["tv_profile"],
        "movie": frames["movie_profile"],
    }

    for domain in sorted(REQUIRED_V1_DOMAINS):
        domain_entity_ids = set(
            entities.filter(pl.col("domain") == domain)
            .get_column("entity_id")
            .cast(pl.String)
            .to_list()
        )
        if not domain_entity_ids:
            findings.append(_error("domain_entities_missing", f"No {domain} entities exist."))
            continue

        if not domain_entity_ids & _entity_id_set(titles):
            findings.append(_error("domain_titles_missing", f"No {domain} title rows exist."))
        if not domain_entity_ids & _entity_id_set(external_ids):
            findings.append(_error("domain_external_ids_missing", f"No {domain} external ID rows exist."))
        if not domain_entity_ids & _entity_id_set(source_records):
            findings.append(_error("domain_source_records_missing", f"No {domain} source record rows exist."))
        profile_table = f"{domain}_profile"
        if not domain_entity_ids & _entity_id_set(profile_frames[domain]):
            findings.append(
                _error("domain_profile_missing", f"No {domain} profile rows exist.", profile_table)
            )
    return findings


def _entity_id_set(frame: pl.DataFrame) -> set[str]:
    if "entity_id" not in frame.columns:
        return set()
    return {str(value) for value in frame.get_column("entity_id").to_list()}


def _entries_by_name(raw_entries: object, *, key_name: str) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_entries, list):
        return {}

    entries: dict[str, dict[str, Any]] = {}
    for raw_entry in cast(list[object], raw_entries):
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[str, Any], raw_entry)
        key = _string_value(entry.get(key_name))
        if key is not None:
            entries[key] = entry
    return entries


def _path_error(value: str) -> str | None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        return "Artifact table paths must be relative POSIX paths without parent traversal."
    if path.suffix != ".parquet":
        return "Artifact table paths must point to parquet files."
    return None


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in cast(list[object], value) if isinstance(item, str)}


def _error(
    code: str,
    message: str,
    table: str | None = None,
) -> ReleaseReadinessFinding:
    return ReleaseReadinessFinding(
        severity="error",
        code=code,
        message=message,
        table=table,
    )
