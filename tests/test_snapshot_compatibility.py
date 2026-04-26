from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from media_offline_database.cli import app
from media_offline_database.snapshot_compatibility import validate_snapshot_compatibility

runner = CliRunner()


def _write_manifest(path: Path, files: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "artifact": "bootstrap-corpus",
                "artifact_version": 1,
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_snapshot_compatibility_errors_when_core_table_disappears(tmp_path: Path) -> None:
    previous = _write_manifest(
        tmp_path / "previous.json",
        [
            {
                "path": "entities.parquet",
                "kind": "entities",
                "schema_version": "1.0.0",
                "compatibility_tier": "core",
            }
        ],
    )
    current = _write_manifest(tmp_path / "current.json", [])

    report = validate_snapshot_compatibility(
        previous_manifest_path=previous,
        current_manifest_path=current,
    )

    assert not report.compatible
    assert report.findings[0].code == "table_removed"
    assert report.findings[0].tier == "core"
    assert report.findings[0].severity == "error"


def test_snapshot_compatibility_reports_profile_derived_and_experimental(
    tmp_path: Path,
) -> None:
    previous = _write_manifest(
        tmp_path / "previous.json",
        [
            {
                "path": "anime-profile.parquet",
                "kind": "anime_profile",
                "schema_version": "1.0.0",
                "compatibility_tier": "profile",
            },
            {
                "path": "similarity.parquet",
                "kind": "similarity_candidates",
                "recipe_version": "recipe-v1",
                "compatibility_tier": "derived",
            },
        ],
    )
    current = _write_manifest(
        tmp_path / "current.json",
        [
            {
                "path": "anime-profile.parquet",
                "kind": "anime_profile",
                "schema_version": "2.0.0",
                "compatibility_tier": "profile",
            },
            {
                "path": "similarity.parquet",
                "kind": "similarity_candidates",
                "recipe_version": "recipe-v2",
                "compatibility_tier": "derived",
            },
            {
                "path": "scratch.parquet",
                "kind": "scratch",
                "compatibility_tier": "experimental",
            },
        ],
    )

    report = validate_snapshot_compatibility(
        previous_manifest_path=previous,
        current_manifest_path=current,
    )

    assert report.compatible
    assert [finding.code for finding in report.findings] == [
        "schema_major_changed",
        "recipe_version_changed",
        "experimental_surface",
    ]
    assert [finding.severity for finding in report.findings] == [
        "warning",
        "warning",
        "info",
    ]


def test_validate_snapshot_compatibility_cli_exits_nonzero_on_core_break(
    tmp_path: Path,
) -> None:
    previous = _write_manifest(
        tmp_path / "previous.json",
        [
            {
                "path": "entities.parquet",
                "kind": "entities",
                "schema_version": "1.0.0",
                "compatibility_tier": "core",
            }
        ],
    )
    current = _write_manifest(tmp_path / "current.json", [])

    result = runner.invoke(
        app,
        [
            "validate-snapshot-compatibility",
            str(previous),
            str(current),
        ],
    )

    assert result.exit_code == 1
    assert "table_removed" in result.stdout
