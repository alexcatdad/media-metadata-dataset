from __future__ import annotations

import json
from pathlib import Path

import duckdb

from media_offline_database import __version__
from media_offline_database.artifacts import (
    ARTIFACT_MANIFEST_SCHEMA,
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ARTIFACT_VERSION,
)
from media_offline_database.bootstrap import (
    bootstrap_entities_frame,
    bootstrap_relationships_frame,
    load_bootstrap_entities,
    write_bootstrap_corpus_artifact,
)

BOOTSTRAP_SEED_PATH = Path("corpus/bootstrap-screen-v1.jsonl")


def test_bootstrap_seed_loads_into_typed_entities() -> None:
    entities = load_bootstrap_entities(BOOTSTRAP_SEED_PATH)

    assert len(entities) == 18
    assert entities[0].entity_id == "anime:manami:anidb:23"
    assert entities[0].source_role.value == "BACKBONE_SOURCE"
    assert entities[0].related[0].relationship == "movie_related"
    assert entities[0].related[0].supporting_urls == []
    the_mentalist = next(entity for entity in entities if entity.entity_id == "tv:tvmaze:116")
    assert the_mentalist.title == "The Mentalist"
    assert the_mentalist.domain == "tv"
    assert the_mentalist.episodes == 151
    made_in_abyss = next(entity for entity in entities if entity.entity_id == "anime:manami:anidb:12681")
    assert made_in_abyss.title == "Made in Abyss"
    assert len(made_in_abyss.related) == 3


def test_bootstrap_artifact_round_trips_through_duckdb(tmp_path: Path) -> None:
    manifest_path = write_bootstrap_corpus_artifact(
        input_path=BOOTSTRAP_SEED_PATH,
        output_dir=tmp_path,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entity_file = next(file for file in manifest["files"] if file["kind"] == "entities")
    relationship_file = next(file for file in manifest["files"] if file["kind"] == "relationships")
    entities_path = tmp_path / entity_file["path"]
    relationships_path = tmp_path / relationship_file["path"]

    entity_row_count = duckdb.sql(
        "select count(*) from read_parquet(?)",
        params=[str(entities_path)],
    ).fetchone()
    relationship_row_count = duckdb.sql(
        "select count(*) from read_parquet(?)",
        params=[str(relationships_path)],
    ).fetchone()
    titles = duckdb.sql(
        "select title from read_parquet(?) order by title",
        params=[str(entities_path)],
    ).fetchall()
    relationship_sample = duckdb.sql(
        """
        select source_entity_id, relationship, target_entity_id, supporting_urls,
               supporting_source_count, supporting_provider_count, relationship_confidence
        from read_parquet(?)
        order by source_entity_id, relationship, target_entity_id
        limit 3
        """,
        params=[str(relationships_path)],
    ).fetchall()

    assert manifest["artifact"] == "bootstrap-corpus"
    assert manifest["artifact_version"] == ARTIFACT_VERSION
    assert manifest["build_stage"] == "bootstrap"
    assert manifest["generator_version"] == __version__
    assert manifest["manifest_schema"] == ARTIFACT_MANIFEST_SCHEMA
    assert manifest["manifest_schema_version"] == ARTIFACT_MANIFEST_SCHEMA_VERSION
    assert manifest["row_count"] == 18
    assert manifest["entity_row_count"] == 18
    assert manifest["relationship_row_count"] == 21
    assert manifest["domains"] == ["anime", "tv"]
    assert entity_row_count == (18,)
    assert relationship_row_count == (21,)
    assert titles == [
        ("Berserk",),
        ("Berserk 2",),
        ("Berserk of Gluttony",),
        ("Cowboy Bebop",),
        ("Cowboy Bebop: Tengoku no Tobira",),
        ("Cowboy Bebop: Yose Atsume Blues",),
        ("Dororo",),
        ("Dororo",),
        ("Fullmetal Alchemist",),
        ("Fullmetal Alchemist: Brotherhood",),
        ("Hellsing",),
        ("Hellsing Ultimate",),
        ("Made in Abyss",),
        ("Made in Abyss Movie 3: Fukaki Tamashii no Reimei",),
        ("Made in Abyss: Hourou Suru Tasogare",),
        ("Made in Abyss: Retsujitsu no Ougonkyou",),
        ("Made in Abyss: Tabidachi no Yoake",),
        ("The Mentalist",),
    ]
    assert relationship_sample == [
        (
            "anime:manami:anidb:12681",
            "movie_related",
            "anime:manami:anilist:101343",
            ["https://anilist.co/anime/101343"],
            1,
            1,
            0.72,
        ),
        (
            "anime:manami:anidb:12681",
            "movie_related",
            "anime:manami:anilist:101344",
            ["https://anilist.co/anime/101344"],
            1,
            1,
            0.72,
        ),
        (
            "anime:manami:anidb:12681",
            "sequel_prequel",
            "anime:manami:anidb:13612",
            ["https://anidb.net/anime/13612"],
            1,
            1,
            0.78,
        ),
    ]
    assert entities_path.exists()
    assert entities_path.stat().st_size > 0
    assert relationships_path.exists()
    assert relationships_path.stat().st_size > 0


def test_bootstrap_frames_split_entities_and_relationships() -> None:
    entities = load_bootstrap_entities(BOOTSTRAP_SEED_PATH)
    entity_frame = bootstrap_entities_frame(entities)
    relationship_frame = bootstrap_relationships_frame(entities)

    assert "related" not in entity_frame.columns
    assert "field_sources_json" in entity_frame.columns
    assert "genres" in entity_frame.columns
    assert "studios" in entity_frame.columns
    assert "creators" in entity_frame.columns
    assert entity_frame.height == 18
    assert relationship_frame.columns == [
        "source_entity_id",
        "target_entity_id",
        "relationship",
        "target_url",
        "supporting_urls",
        "supporting_source_count",
        "supporting_provider_count",
        "relationship_confidence",
    ]
    assert relationship_frame.height == 21
