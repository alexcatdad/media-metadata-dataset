from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from media_offline_database.bootstrap import BootstrapEntity, write_bootstrap_corpus_artifact
from media_offline_database.cli import app
from media_offline_database.query import build_query_preview, load_query_entities
from media_offline_database.sources import SourceRole

BOOTSTRAP_SEED_PATH = Path("corpus/bootstrap-screen-v1.jsonl")
runner = CliRunner()


def test_build_query_preview_from_seed_for_made_in_abyss() -> None:
    entities = load_query_entities(input_path=BOOTSTRAP_SEED_PATH)

    preview = build_query_preview(
        entities,
        query="Made in Abyss",
        match_limit=3,
        tag_limit=3,
    )

    assert preview.selected_entity_id == "anime:manami:anidb:12681"
    assert [match.entity_id for match in preview.matches] == [
        "anime:manami:anidb:12681",
        "anime:manami:anilist:101344",
        "anime:manami:anilist:101343",
    ]
    assert preview.canonical_entity.title == "Made in Abyss"
    assert preview.family_graph.node_count == 5
    assert preview.family_graph.edge_count == 9
    assert [card.title for card in preview.related_sections["movie_related"]] == [
        "Made in Abyss: Hourou Suru Tasogare",
        "Made in Abyss: Tabidachi no Yoake",
    ]
    assert [card.title for card in preview.related_sections["sequel_prequel"]] == [
        "Made in Abyss Movie 3: Fukaki Tamashii no Reimei"
    ]
    assert {
        node.title for node in preview.family_graph.nodes
    } == {
        "Made in Abyss",
        "Made in Abyss: Tabidachi no Yoake",
        "Made in Abyss: Hourou Suru Tasogare",
        "Made in Abyss Movie 3: Fukaki Tamashii no Reimei",
        "Made in Abyss: Retsujitsu no Ougonkyou",
    }
    assert all(neighbor.entity_id not in {node.entity_id for node in preview.family_graph.nodes} for neighbor in preview.tag_neighbors)


def test_build_query_preview_from_manifest_for_made_in_abyss(tmp_path: Path) -> None:
    manifest_path = write_bootstrap_corpus_artifact(
        input_path=BOOTSTRAP_SEED_PATH,
        output_dir=tmp_path,
    )
    entities = load_query_entities(manifest_path=manifest_path)

    preview = build_query_preview(entities, query="Made in Abyss")

    assert preview.selected_entity_id == "anime:manami:anidb:12681"
    assert preview.family_graph.node_count == 5
    assert {
        tuple(card.supporting_urls) for card in preview.related_sections["movie_related"]
    } == {
        ("https://anilist.co/anime/101343",),
        ("https://anilist.co/anime/101344",),
    }
    assert preview.related_sections["sequel_prequel"][0].supporting_provider_count == 1


def test_query_preview_cli_prints_structured_json() -> None:
    result = runner.invoke(
        app,
        ["query-preview", "Made in Abyss", "--match-limit", "3", "--tag-limit", "2"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["selected_entity_id"] == "anime:manami:anidb:12681"
    assert payload["canonical_entity"]["title"] == "Made in Abyss"
    assert payload["family_graph"]["node_count"] == 5
    assert set(payload["related_sections"]) == {"movie_related", "sequel_prequel"}


def test_build_query_preview_adds_same_studio_and_same_creator_sections() -> None:
    entities = [
        BootstrapEntity(
            entity_id="anime:manami:anidb:12681",
            domain="anime",
            canonical_source="https://anidb.net/anime/12681",
            source_role=SourceRole.BACKBONE_SOURCE,
            record_source="test",
            title="Made in Abyss",
            media_type="TV",
            status="FINISHED",
            release_year=2017,
            studios=["Kinema Citrus"],
            creators=["Akihito Tsukushi"],
            tags=["adventure", "dark fantasy"],
        ),
        BootstrapEntity(
            entity_id="anime:local:1",
            domain="anime",
            canonical_source="https://anilist.co/anime/1",
            source_role=SourceRole.LOCAL_EVIDENCE,
            record_source="test",
            title="Tower Show",
            media_type="TV",
            status="FINISHED",
            release_year=2020,
            studios=["Kinema Citrus"],
            creators=["Somebody Else"],
        ),
        BootstrapEntity(
            entity_id="anime:local:2",
            domain="anime",
            canonical_source="https://anilist.co/anime/2",
            source_role=SourceRole.LOCAL_EVIDENCE,
            record_source="test",
            title="Author Match Show",
            media_type="TV",
            status="FINISHED",
            release_year=2021,
            studios=["Another Studio"],
            creators=["Akihito Tsukushi"],
        ),
    ]

    preview = build_query_preview(entities, query="Made in Abyss")

    assert [card.title for card in preview.related_sections["same_studio"]] == ["Tower Show"]
    assert [card.title for card in preview.related_sections["same_creator"]] == ["Author Match Show"]
