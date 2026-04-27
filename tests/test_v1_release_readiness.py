from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import polars as pl
import pytest
from typer.testing import CliRunner

from media_offline_database.bootstrap import BootstrapEntity, BootstrapRelatedEdge
from media_offline_database.cli import app
from media_offline_database.release_readiness import (
    ReleaseReadinessError,
    assert_release_readiness_if_applicable,
    validate_release_readiness,
)
from media_offline_database.sources import SourceRole
from media_offline_database.v1_artifact import write_v1_core_artifact

runner = CliRunner()

SNAPSHOT_IDS = {
    "manami": "manami:2026-04-02",
    "tvmaze": "tvmaze:2026-04-26",
    "wikidata": "wikidata:2026-04-26",
}


def _seed_entities() -> list[BootstrapEntity]:
    return [
        BootstrapEntity(
            entity_id="anime:manami:anidb:12681",
            domain="anime",
            canonical_source="https://anidb.net/anime/12681",
            source_role=SourceRole.BACKBONE_SOURCE,
            record_source="manami",
            title="Made in Abyss",
            original_title="Made in Abyss",
            media_type="TV",
            status="FINISHED",
            release_year=2017,
            episodes=13,
            sources=["https://anidb.net/anime/12681"],
            related=[
                BootstrapRelatedEdge(
                    target="anime:manami:anidb:13612",
                    relationship="sequel",
                    target_url="https://anidb.net/anime/13612",
                    supporting_urls=["https://anidb.net/anime/13612"],
                )
            ],
            tags=["dark_fantasy"],
        ),
        BootstrapEntity(
            entity_id="tv:tvmaze:1825",
            domain="tv",
            canonical_source="https://www.tvmaze.com/shows/1825/the-expanse",
            source_role=SourceRole.BACKBONE_SOURCE,
            record_source="tvmaze",
            title="The Expanse",
            media_type="Scripted",
            status="Ended",
            release_year=2015,
            episodes=62,
            sources=["https://www.tvmaze.com/shows/1825/the-expanse"],
            genres=["Science-Fiction"],
            tags=["network:prime_video"],
        ),
        BootstrapEntity(
            entity_id="movie:wikidata:Q163872",
            domain="movie",
            canonical_source="https://www.wikidata.org/wiki/Q163872",
            source_role=SourceRole.BACKBONE_SOURCE,
            record_source="wikidata",
            title="The Dark Knight",
            media_type="MOVIE",
            status="RELEASED",
            release_year=2008,
            sources=["https://www.wikidata.org/wiki/Q163872"],
            genres=["superhero film"],
            tags=["franchise:the_dark_knight_trilogy"],
        ),
    ]


def _write_seed(path: Path, entities: list[BootstrapEntity]) -> Path:
    path.write_text(
        "\n".join(entity.model_dump_json() for entity in entities) + "\n",
        encoding="utf-8",
    )
    return path


def _write_ready_artifact(tmp_path: Path) -> Path:
    seed_path = _write_seed(tmp_path / "seed.jsonl", _seed_entities())
    return write_v1_core_artifact(
        input_paths=[seed_path],
        output_dir=tmp_path / "out",
        source_snapshot_ids=SNAPSHOT_IDS,
    )


def _load_manifest(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_v1_release_readiness_passes_for_cross_domain_artifact(tmp_path: Path) -> None:
    manifest_path = _write_ready_artifact(tmp_path)

    report = validate_release_readiness(manifest_path)

    assert report.ready
    assert report.findings == []


def test_v1_release_readiness_rejects_unspecified_snapshot_ids(tmp_path: Path) -> None:
    seed_path = _write_seed(tmp_path / "seed.jsonl", _seed_entities())
    manifest_path = write_v1_core_artifact(input_paths=[seed_path], output_dir=tmp_path / "out")

    report = validate_release_readiness(manifest_path)

    assert not report.ready
    assert "source_snapshot_unspecified" in {finding.code for finding in report.findings}
    with pytest.raises(ReleaseReadinessError, match="source_snapshot_unspecified"):
        assert_release_readiness_if_applicable(manifest_path)


def test_v1_release_readiness_rejects_missing_domain(tmp_path: Path) -> None:
    seed_path = _write_seed(tmp_path / "seed.jsonl", _seed_entities()[:2])
    manifest_path = write_v1_core_artifact(
        input_paths=[seed_path],
        output_dir=tmp_path / "out",
        source_snapshot_ids=SNAPSHOT_IDS,
    )

    report = validate_release_readiness(manifest_path)

    assert not report.ready
    assert "required_domains_missing" in {finding.code for finding in report.findings}
    assert "required_sources_missing" in {finding.code for finding in report.findings}


def test_v1_release_readiness_rejects_row_count_mismatch(tmp_path: Path) -> None:
    manifest_path = _write_ready_artifact(tmp_path)
    manifest = _load_manifest(manifest_path)
    tables = manifest["tables"]
    assert isinstance(tables, list)
    for raw_table in cast(list[object], tables):
        assert isinstance(raw_table, dict)
        table = cast(dict[str, Any], raw_table)
        if table["table_name"] == "entities":
            table["row_count"] = 999
    _write_manifest(manifest_path, manifest)

    report = validate_release_readiness(manifest_path)

    assert not report.ready
    assert "row_count_mismatch" in {finding.code for finding in report.findings}


def test_v1_release_readiness_rejects_wrong_columns(tmp_path: Path) -> None:
    manifest_path = _write_ready_artifact(tmp_path)
    entities_path = manifest_path.parent / "entities.parquet"
    entities = pl.read_parquet(entities_path).drop("status")
    entities.write_parquet(entities_path)

    report = validate_release_readiness(manifest_path)

    assert not report.ready
    assert "columns_mismatch" in {finding.code for finding in report.findings}


def test_v1_release_readiness_rejects_unjoined_source_snapshot_ref(tmp_path: Path) -> None:
    manifest_path = _write_ready_artifact(tmp_path)
    source_records_path = manifest_path.parent / "source_records.parquet"
    source_records = pl.read_parquet(source_records_path).with_columns(
        pl.when(pl.col("source_id") == "tvmaze")
        .then(pl.lit("tvmaze:missing"))
        .otherwise(pl.col("source_snapshot_id"))
        .alias("source_snapshot_id")
    )
    source_records.write_parquet(source_records_path)

    report = validate_release_readiness(manifest_path)

    assert not report.ready
    assert "source_snapshot_join_missing" in {finding.code for finding in report.findings}


def test_validate_release_readiness_cli_exits_nonzero_for_unready_v1(tmp_path: Path) -> None:
    seed_path = _write_seed(tmp_path / "seed.jsonl", _seed_entities())
    manifest_path = write_v1_core_artifact(input_paths=[seed_path], output_dir=tmp_path / "out")

    result = runner.invoke(app, ["validate-release-readiness", str(manifest_path)])

    assert result.exit_code == 1
    assert "source_snapshot_unspecified" in result.stdout
