from __future__ import annotations

import json
from pathlib import Path

import duckdb

from media_offline_database.bootstrap import (
    load_bootstrap_entities,
    write_bootstrap_corpus_artifact,
)

DEATH_NOTE_SEED_PATH = Path("corpus/bootstrap-death-note-v1.jsonl")


def test_death_note_seed_keeps_same_title_cross_media_entries_separate() -> None:
    entities = load_bootstrap_entities(DEATH_NOTE_SEED_PATH)

    assert len(entities) == 4
    assert sorted({entity.domain for entity in entities}) == ["anime", "movie", "tv"]

    same_title_entities = [entity for entity in entities if entity.title == "Death Note"]
    assert len(same_title_entities) == 4
    assert sorted({entity.media_type for entity in same_title_entities}) == ["MOVIE", "TV"]

    anime_series = next(entity for entity in entities if entity.entity_id == "anime:manami:anidb:4563")
    assert {edge.relationship for edge in anime_series.related} == {"adaptation_related"}


def test_death_note_artifact_round_trips_with_adaptation_edges(tmp_path: Path) -> None:
    manifest_path = write_bootstrap_corpus_artifact(
        input_path=DEATH_NOTE_SEED_PATH,
        output_dir=tmp_path,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relationship_file = next(file for file in manifest["files"] if file["kind"] == "relationships")
    relationships_path = tmp_path / relationship_file["path"]

    rows = duckdb.sql(
        """
        select source_entity_id, relationship_type, target_entity_id, relationship_confidence_score
        from read_parquet(?)
        order by source_entity_id, relationship_type, target_entity_id
        """,
        params=[str(relationships_path)],
    ).fetchall()

    assert manifest["entity_row_count"] == 4
    assert manifest["relationship_row_count"] == 12
    assert (
        "anime:manami:anidb:4563",
        "adaptation_related",
        "movie:tmdb:16007",
        0.62,
    ) in rows
    assert (
        "tv:tvmaze:4712",
        "adaptation_related",
        "movie:tmdb:351460",
        0.62,
    ) in rows
