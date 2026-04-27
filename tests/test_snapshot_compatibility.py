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


def test_snapshot_compatibility_prefers_table_metadata_for_v1_manifests(
    tmp_path: Path,
) -> None:
    previous = tmp_path / "previous-v1.json"
    previous.write_text(
        json.dumps(
            {
                "artifact": "media-metadata-v1",
                "artifact_version": 1,
                "files": [{"path": "entities.parquet", "kind": "entities"}],
                "tables": [
                    {
                        "table_name": "entities",
                        "path": "entities.parquet",
                        "schema_version": "1.0.0",
                        "compatibility_tier": "core",
                    },
                    {
                        "table_name": "source_snapshots",
                        "path": "source_snapshots.parquet",
                        "schema_version": "1.0.0",
                        "compatibility_tier": "core",
                    },
                    {
                        "table_name": "provider_runs",
                        "path": "provider_runs.parquet",
                        "schema_version": "1.0.0",
                        "compatibility_tier": "core",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    current = tmp_path / "current-v1.json"
    current.write_text(
        json.dumps(
            {
                "artifact": "media-metadata-v1",
                "artifact_version": 1,
                "files": [],
                "tables": [],
            }
        ),
        encoding="utf-8",
    )

    report = validate_snapshot_compatibility(
        previous_manifest_path=previous,
        current_manifest_path=current,
    )

    assert not report.compatible
    assert {finding.table for finding in report.findings} == {
        "entities",
        "source_snapshots",
        "provider_runs",
    }
    assert {finding.code for finding in report.findings} == {"table_removed"}
    assert {finding.tier for finding in report.findings} == {"core"}


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


def test_snapshot_compatibility_classifies_underscore_llm_kinds_as_derived(
    tmp_path: Path,
) -> None:
    previous = _write_manifest(
        tmp_path / "previous.json",
        [
            {
                "path": "llm-materialized-relationships.parquet",
                "kind": "llm_materialized_relationships",
                "recipe_version": "recipe-v1",
            },
        ],
    )
    current = _write_manifest(
        tmp_path / "current.json",
        [
            {
                "path": "llm-materialized-relationships.parquet",
                "kind": "llm_materialized_relationships",
                "recipe_version": "recipe-v2",
            },
        ],
    )

    report = validate_snapshot_compatibility(
        previous_manifest_path=previous,
        current_manifest_path=current,
    )

    assert report.compatible
    assert len(report.findings) == 1
    assert report.findings[0].tier == "derived"
    assert report.findings[0].code == "recipe_version_changed"


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
