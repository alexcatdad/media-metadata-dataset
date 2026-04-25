from __future__ import annotations

import json
from pathlib import Path

import duckdb

from media_offline_database.bootstrap import (
    load_bootstrap_entities,
    write_bootstrap_corpus_artifact,
)

DESIGNATED_SURVIVOR_SEED_PATH = Path("corpus/bootstrap-designated-survivor-v1.jsonl")


def test_designated_survivor_seed_keeps_versions_separate() -> None:
    entities = load_bootstrap_entities(DESIGNATED_SURVIVOR_SEED_PATH)

    assert len(entities) == 2
    assert {entity.title for entity in entities} == {
        "Designated Survivor",
        "Designated Survivor: 60 Days",
    }

    us_series = next(entity for entity in entities if entity.entity_id == "tv:tvmaze:8167")
    kr_series = next(entity for entity in entities if entity.entity_id == "tv:tvmaze:41818")

    assert us_series.original_title == "Designated Survivor"
    assert kr_series.original_title == "60일, 지정생존자"
    assert us_series.related[0].relationship == "remake_reboot"
    assert kr_series.related[0].relationship == "remake_reboot"


def test_designated_survivor_artifact_round_trips_through_duckdb(tmp_path: Path) -> None:
    manifest_path = write_bootstrap_corpus_artifact(
        input_path=DESIGNATED_SURVIVOR_SEED_PATH,
        output_dir=tmp_path,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relationship_file = next(file for file in manifest["files"] if file["kind"] == "relationships")
    relationships_path = tmp_path / relationship_file["path"]

    rows = duckdb.sql(
        """
        select source_entity_id, relationship, target_entity_id, relationship_confidence
        from read_parquet(?)
        order by source_entity_id, target_entity_id
        """,
        params=[str(relationships_path)],
    ).fetchall()

    assert manifest["entity_row_count"] == 2
    assert manifest["relationship_row_count"] == 2
    assert rows == [
        ("tv:tvmaze:41818", "remake_reboot", "tv:tvmaze:8167", 0.76),
        ("tv:tvmaze:8167", "remake_reboot", "tv:tvmaze:41818", 0.76),
    ]
