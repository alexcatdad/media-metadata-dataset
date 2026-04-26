from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from media_offline_database.build_tv import build_tvmaze_tv_artifact
from media_offline_database.cli import app
from media_offline_database.ingest_tvmaze import TVmazeShow, normalize_tvmaze_show

runner = CliRunner()


def _expanse_show() -> TVmazeShow:
    return TVmazeShow.model_validate(
        {
            "id": 1825,
            "url": "https://www.tvmaze.com/shows/1825/the-expanse",
            "name": "The Expanse",
            "type": "Scripted",
            "language": "English",
            "genres": ["Science-Fiction", "Thriller", "Mystery"],
            "status": "Ended",
            "runtime": None,
            "averageRuntime": 55,
            "premiered": "2015-12-14",
            "ended": "2022-01-14",
            "officialSite": "https://www.amazon.com/dp/B07YL9WK1S/",
            "network": None,
            "webChannel": {"name": "Prime Video"},
            "externals": {"imdb": "tt3230854", "thetvdb": 280619, "tvrage": 41967},
            "summary": "<p>This must not be published by the normalizer.</p>",
            "_embedded": {
                "episodes": [{"id": 1}, {"id": 2}],
                "seasons": [{"id": 1}],
            },
        }
    )


def test_normalize_tvmaze_show_excludes_summary_html() -> None:
    entity = normalize_tvmaze_show(_expanse_show())

    assert entity.entity_id == "tv:tvmaze:1825"
    assert entity.domain == "tv"
    assert entity.record_source == "tvmaze"
    assert entity.title == "The Expanse"
    assert entity.release_year == 2015
    assert entity.episodes == 2
    assert entity.genres == ["Mystery", "Science-Fiction", "Thriller"]
    assert "network:prime_video" in entity.tags
    dumped = entity.model_dump_json()
    assert "This must not be published" not in dumped


def test_build_tvmaze_tv_artifact_writes_publishable_manifest(tmp_path: Path) -> None:
    result = build_tvmaze_tv_artifact(
        show_ids=[1825],
        output_dir=tmp_path,
        fetch_show=lambda _show_id: _expanse_show(),
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    entity_file = next(file for file in manifest["files"] if file["kind"] == "entities")
    entities = pl.read_parquet(result.manifest_path.parent / entity_file["path"])

    assert result.total_candidates == 1
    assert manifest["domains"] == ["tv"]
    assert manifest["entity_row_count"] == 1
    assert manifest["relationship_row_count"] == 0
    assert "PUBLIC_PARQUET" in manifest["publishability"]["validated_uses"]
    assert entities.item(0, "entity_id") == "tv:tvmaze:1825"


def test_tvmaze_build_cli_exposes_command() -> None:
    result = runner.invoke(app, ["tvmaze-build", "--help"])

    assert result.exit_code == 0
    assert "TVmaze" in result.stdout
