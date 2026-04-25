from __future__ import annotations

import json
from pathlib import Path

import duckdb

from media_offline_database.bootstrap import (
    load_bootstrap_entities,
    write_bootstrap_corpus_artifact,
)

GITS_SEED_PATH = Path("corpus/bootstrap-ghost-in-the-shell-v1.jsonl")


def test_ghost_in_the_shell_seed_captures_cross_media_family() -> None:
    entities = load_bootstrap_entities(GITS_SEED_PATH)

    assert len(entities) == 5
    assert sorted({entity.domain for entity in entities}) == ["anime", "movie"]

    animated_film = next(entity for entity in entities if entity.entity_id == "anime:manami:anidb:61")
    live_action = next(entity for entity in entities if entity.entity_id == "movie:tmdb:315837")

    assert animated_film.title == "Ghost in the Shell"
    assert {edge.relationship for edge in animated_film.related} == {
        "sequel_prequel",
        "franchise_related",
    }
    assert live_action.related[0].relationship == "franchise_related"


def test_ghost_in_the_shell_artifact_round_trips_with_franchise_edges(tmp_path: Path) -> None:
    manifest_path = write_bootstrap_corpus_artifact(
        input_path=GITS_SEED_PATH,
        output_dir=tmp_path,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relationship_file = next(file for file in manifest["files"] if file["kind"] == "relationships")
    relationships_path = tmp_path / relationship_file["path"]

    relationship_rows = duckdb.sql(
        """
        select source_entity_id, relationship, target_entity_id, relationship_confidence
        from read_parquet(?)
        order by source_entity_id, relationship, target_entity_id
        """,
        params=[str(relationships_path)],
    ).fetchall()

    assert manifest["entity_row_count"] == 5
    assert manifest["relationship_row_count"] == 10
    assert (
        "movie:tmdb:315837",
        "franchise_related",
        "anime:manami:anidb:61",
        0.55,
    ) in relationship_rows
    assert (
        "anime:manami:anidb:61",
        "sequel_prequel",
        "anime:manami:anidb:890",
        0.78,
    ) in relationship_rows
