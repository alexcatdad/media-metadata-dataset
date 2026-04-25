from __future__ import annotations

import json
from pathlib import Path

from media_offline_database.bootstrap import BootstrapEntity
from media_offline_database.enrich_anilist_metadata import (
    AniListResolvedMetadata,
    enrich_bootstrap_entities_with_anilist_metadata,
    write_anilist_metadata_enriched_seed,
)
from media_offline_database.sources import SourceRole


def test_enrich_bootstrap_entities_with_anilist_metadata_adds_genres_studios_and_creators() -> None:
    entities = [
        _bootstrap_entity(
            entity_id="anime:manami:anidb:12681",
            title="Made in Abyss",
            sources=[
                "https://anidb.net/anime/12681",
                "https://anilist.co/anime/97986",
            ],
        ),
        _bootstrap_entity(
            entity_id="tv:tvmaze:116",
            domain="tv",
            title="The Mentalist",
            sources=["https://www.tvmaze.com/shows/116/the-mentalist"],
        ),
    ]

    fetch_calls: list[int] = []

    def fake_fetcher(anilist_id: int) -> AniListResolvedMetadata:
        fetch_calls.append(anilist_id)
        return AniListResolvedMetadata(
            genres=["Drama", "Romance"],
            studios=["Kinema Citrus"],
            creators=["Akihito Tsukushi"],
        )

    enriched = enrich_bootstrap_entities_with_anilist_metadata(
        entities,
        fetch_metadata=fake_fetcher,
    )

    assert fetch_calls == [97986]
    assert enriched[0].genres == ["Drama", "Romance"]
    assert enriched[0].studios == ["Kinema Citrus"]
    assert enriched[0].creators == ["Akihito Tsukushi"]
    assert enriched[0].field_sources["genres"] == ["https://anilist.co/anime/97986"]
    assert enriched[0].field_sources["studios"] == ["https://anilist.co/anime/97986"]
    assert enriched[0].field_sources["creators"] == ["https://anilist.co/anime/97986"]
    assert enriched[1].genres == []
    assert enriched[1].studios == []
    assert enriched[1].creators == []


def test_enrich_bootstrap_entities_with_anilist_metadata_preserves_existing_field_sources() -> None:
    entities = [
        _bootstrap_entity(
            entity_id="anime:manami:anidb:12681",
            title="Made in Abyss",
            sources=[
                "https://anidb.net/anime/12681",
                "https://anilist.co/anime/97986",
            ],
            field_sources={"studios": ["https://anidb.net/anime/12681"]},
        )
    ]

    enriched = enrich_bootstrap_entities_with_anilist_metadata(
        entities,
        fetch_metadata=lambda _: AniListResolvedMetadata(
            genres=[],
            studios=["Kinema Citrus"],
            creators=[],
        ),
    )

    assert enriched[0].field_sources["studios"] == [
        "https://anidb.net/anime/12681",
        "https://anilist.co/anime/97986",
    ]
    assert "genres" not in enriched[0].field_sources
    assert "creators" not in enriched[0].field_sources


def test_enrich_bootstrap_entities_with_anilist_metadata_keeps_existing_fields_when_fetch_is_empty() -> None:
    entities = [
        _bootstrap_entity(
            entity_id="anime:manami:anidb:12681",
            title="Made in Abyss",
            sources=[
                "https://anidb.net/anime/12681",
                "https://anilist.co/anime/97986",
            ],
        ).model_copy(update={"studios": ["Kinema Citrus"], "creators": ["Akihito Tsukushi"]})
    ]

    enriched = enrich_bootstrap_entities_with_anilist_metadata(
        entities,
        fetch_metadata=lambda _: AniListResolvedMetadata(genres=[], studios=[], creators=[]),
    )

    assert enriched[0].studios == ["Kinema Citrus"]
    assert enriched[0].creators == ["Akihito Tsukushi"]


def test_write_anilist_metadata_enriched_seed_writes_jsonl(tmp_path: Path) -> None:
    input_path = tmp_path / "normalized.jsonl"
    input_path.write_text(
        _bootstrap_entity(
            entity_id="anime:manami:anidb:12681",
            title="Made in Abyss",
            sources=[
                "https://anidb.net/anime/12681",
                "https://anilist.co/anime/97986",
            ],
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "enriched.jsonl"

    written_path = write_anilist_metadata_enriched_seed(
        input_path=input_path,
        output_path=output_path,
        fetch_metadata=lambda _: AniListResolvedMetadata(
            genres=["Drama", "Romance"],
            studios=["Kinema Citrus"],
            creators=["Akihito Tsukushi"],
        ),
    )

    payload = [
        json.loads(line)
        for line in written_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert written_path == output_path
    assert payload[0]["genres"] == ["Drama", "Romance"]
    assert payload[0]["studios"] == ["Kinema Citrus"]
    assert payload[0]["creators"] == ["Akihito Tsukushi"]
    assert payload[0]["field_sources"]["genres"] == ["https://anilist.co/anime/97986"]
    assert payload[0]["field_sources"]["studios"] == ["https://anilist.co/anime/97986"]
    assert payload[0]["field_sources"]["creators"] == ["https://anilist.co/anime/97986"]


def _bootstrap_entity(
    *,
    entity_id: str,
    title: str,
    sources: list[str],
    domain: str = "anime",
    field_sources: dict[str, list[str]] | None = None,
) -> BootstrapEntity:
    return BootstrapEntity(
        entity_id=entity_id,
        domain=domain,
        canonical_source=sources[0],
        source_role=SourceRole.BACKBONE_SOURCE,
        record_source="test",
        title=title,
        media_type="TV",
        status="FINISHED",
        release_year=2000,
        sources=sources,
        field_sources=field_sources or {},
    )
