from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

CompatibilityTier = Literal["core", "profile", "derived", "experimental"]
CompatibilitySeverity = Literal["info", "warning", "error"]


class CompatibilityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: CompatibilitySeverity
    tier: CompatibilityTier
    code: str
    message: str
    table: str | None = None


def _empty_findings() -> list[CompatibilityFinding]:
    return []


class SnapshotCompatibilityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_manifest_path: str
    current_manifest_path: str
    compatible: bool
    findings: list[CompatibilityFinding] = Field(default_factory=_empty_findings)


def _load_manifest(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _major(version: object) -> int | None:
    if isinstance(version, int):
        return version
    if isinstance(version, str) and version:
        head = version.split(".", maxsplit=1)[0]
        if head.isdigit():
            return int(head)
    return None


def _files_by_kind(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = cast(object, manifest.get("files"))
    if not isinstance(files, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for raw_file_entry in cast(list[object], files):
        file_entry = raw_file_entry
        if not isinstance(file_entry, dict):
            continue
        file_entry_data = cast(dict[str, Any], file_entry)
        kind = cast(object, file_entry_data.get("kind") or file_entry_data.get("path"))
        if isinstance(kind, str):
            indexed[kind] = file_entry_data
    return indexed


def _tier_for_file(file_entry: dict[str, Any]) -> CompatibilityTier:
    tier = file_entry.get("compatibility_tier")
    if tier in {"core", "profile", "derived", "experimental"}:
        return tier

    kind = str(file_entry.get("kind", ""))
    if kind.endswith("_profile") or "profile" in kind:
        return "profile"
    if kind.startswith("llm-") or kind in {"relationships", "entities"}:
        return "core"
    return "experimental"


def validate_snapshot_compatibility(
    *,
    previous_manifest_path: Path,
    current_manifest_path: Path,
) -> SnapshotCompatibilityReport:
    previous = _load_manifest(previous_manifest_path)
    current = _load_manifest(current_manifest_path)
    findings: list[CompatibilityFinding] = []

    previous_artifact_major = _major(previous.get("artifact_version"))
    current_artifact_major = _major(current.get("artifact_version"))
    if (
        previous_artifact_major is not None
        and current_artifact_major is not None
        and current_artifact_major < previous_artifact_major
    ):
        findings.append(
            CompatibilityFinding(
                severity="error",
                tier="core",
                code="artifact_major_regressed",
                message="Current artifact major version is lower than the previous manifest.",
            )
        )

    previous_files = _files_by_kind(previous)
    current_files = _files_by_kind(current)
    for kind, previous_file in previous_files.items():
        previous_tier = _tier_for_file(previous_file)
        current_file = current_files.get(kind)
        if current_file is None:
            severity: CompatibilitySeverity = "warning"
            if previous_tier == "core":
                severity = "error"
            findings.append(
                CompatibilityFinding(
                    severity=severity,
                    tier=previous_tier,
                    code="table_removed",
                    message=f"Previous {previous_tier} table is missing from the current manifest.",
                    table=kind,
                )
            )
            continue

        previous_schema_major = _major(previous_file.get("schema_version"))
        current_schema_major = _major(current_file.get("schema_version"))
        if (
            previous_schema_major is not None
            and current_schema_major is not None
            and current_schema_major > previous_schema_major
        ):
            severity = "error" if previous_tier == "core" else "warning"
            findings.append(
                CompatibilityFinding(
                    severity=severity,
                    tier=previous_tier,
                    code="schema_major_changed",
                    message=(
                        f"{previous_tier} table schema major changed from "
                        f"{previous_schema_major} to {current_schema_major}."
                    ),
                    table=kind,
                )
            )

        previous_recipe = previous_file.get("recipe_version")
        current_recipe = current_file.get("recipe_version")
        if (
            previous_recipe is not None
            and current_recipe is not None
            and previous_recipe != current_recipe
        ):
            findings.append(
                CompatibilityFinding(
                    severity="warning",
                    tier="derived",
                    code="recipe_version_changed",
                    message="Derived recipe version changed; consumers may need recomputation.",
                    table=kind,
                )
            )

    for kind, current_file in current_files.items():
        tier = _tier_for_file(current_file)
        if tier == "experimental":
            findings.append(
                CompatibilityFinding(
                    severity="info",
                    tier="experimental",
                    code="experimental_surface",
                    message="Current manifest includes an experimental surface with no compatibility guarantee.",
                    table=kind,
                )
            )

    return SnapshotCompatibilityReport(
        previous_manifest_path=str(previous_manifest_path),
        current_manifest_path=str(current_manifest_path),
        compatible=not any(finding.severity == "error" for finding in findings),
        findings=findings,
    )
