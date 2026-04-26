from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from media_offline_database.build_movie import build_wikidata_movie_artifact
from media_offline_database.cli import app
from media_offline_database.ingest_wikidata_movies import (
    WikidataMovieRecord,
    normalize_wikidata_movie_records,
)

runner = CliRunner()


def _dark_knight_records() -> list[WikidataMovieRecord]:
    return [
        WikidataMovieRecord(
            qid="Q166262",
            label="Batman Begins",
            aliases=["Batman 5"],
            publication_date="2005-06-15T00:00:00Z",
            runtime_minutes=140,
            imdb_id="tt0372784",
            genres=["superhero film"],
            directors=["Christopher Nolan"],
            series=["The Dark Knight trilogy"],
        ),
        WikidataMovieRecord(
            qid="Q163872",
            label="The Dark Knight",
            publication_date="2008-07-18T00:00:00Z",
            runtime_minutes=153,
            imdb_id="tt0468569",
            genres=["superhero film"],
            directors=["Christopher Nolan"],
            series=["The Dark Knight trilogy"],
        ),
    ]


def test_normalize_wikidata_movie_records_adds_franchise_edges() -> None:
    entities = normalize_wikidata_movie_records(_dark_knight_records())

    assert [entity.entity_id for entity in entities] == [
        "movie:wikidata:Q166262",
        "movie:wikidata:Q163872",
    ]
    assert entities[0].title == "Batman Begins"
    assert entities[0].release_year == 2005
    assert entities[0].creators == ["Christopher Nolan"]
    assert entities[0].synonyms == ["Batman 5"]
    assert entities[0].related[0].relationship == "franchise_related"
    assert entities[0].related[0].target == "movie:wikidata:Q163872"


def test_build_wikidata_movie_artifact_writes_publishable_manifest(tmp_path: Path) -> None:
    result = build_wikidata_movie_artifact(
        qids=["Q166262", "Q163872"],
        output_dir=tmp_path,
        fetch_records=lambda _qids: _dark_knight_records(),
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    entity_file = next(file for file in manifest["files"] if file["kind"] == "entities")
    relationship_file = next(file for file in manifest["files"] if file["kind"] == "relationships")
    entities = pl.read_parquet(result.manifest_path.parent / entity_file["path"])
    relationships = pl.read_parquet(result.manifest_path.parent / relationship_file["path"])

    assert result.total_candidates == 2
    assert manifest["domains"] == ["movie"]
    assert manifest["entity_row_count"] == 2
    assert manifest["relationship_row_count"] == 2
    assert "PUBLIC_PARQUET" in manifest["publishability"]["validated_uses"]
    assert set(entities.get_column("entity_id")) == {
        "movie:wikidata:Q166262",
        "movie:wikidata:Q163872",
    }
    assert set(relationships.get_column("relationship_type")) == {"franchise_related"}


def test_wikidata_movie_build_cli_exposes_command() -> None:
    result = runner.invoke(app, ["wikidata-movie-build", "--help"])

    assert result.exit_code == 0
    assert "Wikidata" in result.stdout
