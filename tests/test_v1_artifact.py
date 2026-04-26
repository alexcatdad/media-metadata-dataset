from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from media_offline_database.bootstrap import BootstrapEntity, BootstrapRelatedEdge
from media_offline_database.cli import app
from media_offline_database.contracts import CORE_TABLE_CONTRACTS, PROFILE_TABLE_CONTRACTS
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

    manifest_path = write_v1_core_artifact(input_paths=[seed_path], output_dir=tmp_path / "out")
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
        "source_records",
        "anime_profile",
        "tv_profile",
        "movie_profile",
    }
    assert set(files) == expected_tables
    assert {entry["table_name"] for entry in manifest["tables"]} == expected_tables
    assert manifest["domains"] == ["anime", "movie", "tv"]
    assert "PUBLIC_PARQUET" in manifest["publishability"]["validated_uses"]

    contracts = {**CORE_TABLE_CONTRACTS, **PROFILE_TABLE_CONTRACTS}
    for table_name in expected_tables:
        frame = pl.read_parquet(manifest_path.parent / files[table_name]["path"])
        expected_columns = [column.name for column in contracts[table_name].columns]
        assert frame.columns == expected_columns


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
