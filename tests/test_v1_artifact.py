from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from media_offline_database.bootstrap import BootstrapEntity, BootstrapRelatedEdge
from media_offline_database.cli import app
from media_offline_database.contracts import CORE_TABLE_CONTRACTS, PROFILE_TABLE_CONTRACTS
from media_offline_database.ingest_normalization import (
    ProviderRun,
    SourceSnapshot,
    write_provider_runs,
    write_source_snapshots,
)
from media_offline_database.publishability import PublishabilityError
from media_offline_database.sources import SourceRole
from media_offline_database.v1_artifact import write_v1_core_artifact

runner = CliRunner()


def _seed_entities() -> list[BootstrapEntity]:
    return [
        BootstrapEntity(
            entity_id="anime:manami:anidb:12681",
            domain="anime",
            canonical_source="https://anidb.net/anime/12681",
            source_role=SourceRole.BACKBONE_SOURCE,
            record_source="manami",
            title="Made in Abyss",
            original_title="メイドインアビス",
            media_type="TV",
            status="FINISHED",
            release_year=2017,
            episodes=13,
            synonyms=["MIA"],
            sources=["https://anidb.net/anime/12681"],
            genres=["Adventure"],
            studios=["Kinema Citrus"],
            creators=["Akihito Tsukushi"],
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
            synonyms=["Batman: The Dark Knight"],
            sources=["https://www.wikidata.org/wiki/Q163872"],
            genres=["superhero film"],
            creators=["Christopher Nolan"],
            tags=["franchise:the_dark_knight_trilogy"],
        ),
    ]


def _write_seed(path: Path, entities: list[BootstrapEntity]) -> Path:
    path.write_text(
        "\n".join(entity.model_dump_json() for entity in entities) + "\n",
        encoding="utf-8",
    )
    return path


def test_v1_core_artifact_emits_contract_tables(tmp_path: Path) -> None:
    seed_path = _write_seed(tmp_path / "seed.jsonl", _seed_entities())

    manifest_path = write_v1_core_artifact(
        input_paths=[seed_path],
        output_dir=tmp_path / "out",
        source_snapshot_ids={
            "manami": "manami:2026-04-02",
            "tvmaze": "tvmaze:2026-04-26",
            "wikidata": "wikidata:2026-04-26",
        },
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = {file["kind"]: file for file in manifest["files"]}

    expected_tables = {
        "entities",
        "titles",
        "external_ids",
        "relationships",
        "relationship_evidence",
        "facets",
        "provenance",
        "source_snapshots",
        "provider_runs",
        "source_records",
        "anime_profile",
        "tv_profile",
        "movie_profile",
    }
    assert set(files) == expected_tables
    assert {entry["table_name"] for entry in manifest["tables"]} == expected_tables
    assert manifest["domains"] == ["anime", "movie", "tv"]
    assert "PUBLIC_PARQUET" in manifest["publishability"]["validated_uses"]
    assert {
        entry["source_snapshot_id"] for entry in manifest["source_coverage"]
    } == {"manami:2026-04-02", "tvmaze:2026-04-26", "wikidata:2026-04-26"}

    contracts = {**CORE_TABLE_CONTRACTS, **PROFILE_TABLE_CONTRACTS}
    for table_name in expected_tables:
        frame = pl.read_parquet(manifest_path.parent / files[table_name]["path"])
        expected_columns = [column.name for column in contracts[table_name].columns]
        assert frame.columns == expected_columns

    source_records = pl.read_parquet(manifest_path.parent / files["source_records"]["path"])
    provenance = pl.read_parquet(manifest_path.parent / files["provenance"]["path"])
    source_snapshots = pl.read_parquet(manifest_path.parent / files["source_snapshots"]["path"])
    provider_runs = pl.read_parquet(manifest_path.parent / files["provider_runs"]["path"])
    snapshot_ids = set(source_snapshots.get_column("source_snapshot_id").to_list())
    provider_run_ids = set(provider_runs.get_column("provider_run_id").to_list())
    assert set(source_records.get_column("source_snapshot_id").to_list()) <= snapshot_ids
    assert set(provenance.get_column("source_snapshot_id").to_list()) <= snapshot_ids
    assert set(source_records.get_column("provider_run_id").to_list()) <= provider_run_ids
    assert set(provenance.get_column("provider_run_id").to_list()) <= provider_run_ids
    assert provider_runs.get_column("secret_refs").to_list() == [[], [], []]


def test_v1_core_artifact_expands_titles_profiles_and_evidence(tmp_path: Path) -> None:
    seed_path = _write_seed(tmp_path / "seed.jsonl", _seed_entities())

    manifest_path = write_v1_core_artifact(input_paths=[seed_path], output_dir=tmp_path / "out")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = {file["kind"]: file for file in manifest["files"]}

    titles = pl.read_parquet(manifest_path.parent / files["titles"]["path"])
    relationships = pl.read_parquet(manifest_path.parent / files["relationships"]["path"])
    relationship_evidence = pl.read_parquet(
        manifest_path.parent / files["relationship_evidence"]["path"]
    )
    anime_profile = pl.read_parquet(manifest_path.parent / files["anime_profile"]["path"])
    tv_profile = pl.read_parquet(manifest_path.parent / files["tv_profile"]["path"])
    movie_profile = pl.read_parquet(manifest_path.parent / files["movie_profile"]["path"])

    assert set(titles.get_column("title_type")) == {"alias", "canonical", "original"}
    assert anime_profile.height == 1
    assert tv_profile.item(0, "network_or_platform") == "prime_video"
    assert movie_profile.item(0, "franchise_hint") == "the_dark_knight_trilogy"
    assert relationships.height == 1
    assert relationship_evidence.height == relationships.height
    assert relationship_evidence.item(0, "relationship_id") == relationships.item(
        0, "relationship_id"
    )


def test_v1_core_artifact_consumes_source_metadata_sidecars(tmp_path: Path) -> None:
    seed_path = _write_seed(tmp_path / "seed.jsonl", [_seed_entities()[1]])
    source_snapshot_path = write_source_snapshots(
        tmp_path / "source-snapshots.jsonl",
        [
            SourceSnapshot(
                source_snapshot_id="tvmaze:sidecar",
                source_id="tvmaze",
                source_role=SourceRole.BACKBONE_SOURCE,
                snapshot_kind="api_fetch_window",
                fetched_at=datetime(2026, 4, 26, tzinfo=UTC),
                policy_version="source-policy-v1",
                publishable_field_policy_version="source-field-policy-v1",
                artifact_policy_version="artifact-policy-v1",
                record_count=1,
            )
        ],
    )
    provider_run_path = write_provider_runs(
        tmp_path / "provider-runs.jsonl",
        [
            ProviderRun(
                provider_run_id="provider-run:tvmaze:sidecar",
                source_id="tvmaze",
                source_snapshot_id="tvmaze:sidecar",
                adapter_name="tvmaze-show-normalizer",
                adapter_version="tvmaze-bootstrap-v1",
                started_at=datetime(2026, 4, 26, tzinfo=UTC),
                finished_at=datetime(2026, 4, 26, tzinfo=UTC),
                request_count=1,
                status="completed",
                auth_shape="none",
            )
        ],
    )

    manifest_path = write_v1_core_artifact(
        input_paths=[seed_path],
        output_dir=tmp_path / "out",
        source_snapshot_paths=[source_snapshot_path],
        provider_run_paths=[provider_run_path],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = {file["kind"]: file for file in manifest["files"]}
    source_records = pl.read_parquet(manifest_path.parent / files["source_records"]["path"])

    assert manifest["source_coverage"][0]["source_snapshot_id"] == "tvmaze:sidecar"
    assert source_records.item(0, "provider_run_id") == "provider-run:tvmaze:sidecar"


def test_v1_core_artifact_rejects_local_evidence_public_rows(tmp_path: Path) -> None:
    local_entity = BootstrapEntity(
        entity_id="movie:tmdb:1",
        domain="movie",
        canonical_source="https://www.themoviedb.org/movie/1",
        source_role=SourceRole.LOCAL_EVIDENCE,
        record_source="tmdb_api",
        title="Runtime Only",
        media_type="MOVIE",
        status="RELEASED",
        release_year=2000,
    )
    seed_path = _write_seed(tmp_path / "seed.jsonl", [local_entity])

    with pytest.raises(PublishabilityError):
        write_v1_core_artifact(input_paths=[seed_path], output_dir=tmp_path / "out")


def test_v1_core_artifact_cli_exposes_command() -> None:
    result = runner.invoke(app, ["v1-core-artifact", "--help"])

    assert result.exit_code == 0
    assert "v1 shared core" in result.stdout
    assert "--source-snapshot-id" in result.stdout
    assert "--source-snapshot-path" in result.stdout
    assert "--provider-run-path" in result.stdout
