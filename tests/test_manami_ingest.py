from __future__ import annotations

import json
from pathlib import Path

import pytest

from media_offline_database.ingest_manami import (
    ManamiAnimeEntry,
    load_manami_release,
    normalize_manami_entry,
    normalize_manami_release,
    normalize_manami_release_batch,
    parse_manami_source_ref,
    write_normalized_manami_seed,
)


def test_normalize_manami_release_maps_bounded_subset_into_bootstrap_shape(tmp_path: Path) -> None:
    fixture_path = tmp_path / "manami-release.json"
    fixture_path.write_text(
        json.dumps(
            {
                "repository": "https://github.com/manami-project/anime-offline-database",
                "lastUpdate": "2026-04-02",
                "data": [
                    {
                        "sources": [
                            "https://anidb.net/anime/12681",
                            "https://anilist.co/anime/97986",
                            "https://myanimelist.net/anime/34599",
                        ],
                        "title": "Made in Abyss",
                        "type": "TV",
                        "episodes": 13,
                        "status": "FINISHED",
                        "animeSeason": {
                            "season": "SUMMER",
                            "year": 2017,
                        },
                        "synonyms": [
                            "メイドインアビス",
                            "Made in Abyss",
                        ],
                        "relatedAnime": [
                            "https://anidb.net/anime/13612",
                            "https://anilist.co/anime/101343",
                        ],
                        "tags": ["adventure", "fantasy", "adventure"],
                    },
                    {
                        "sources": [
                            "https://anilist.co/anime/101343",
                            "https://myanimelist.net/anime/36862",
                        ],
                        "title": "Made in Abyss: Tabidachi no Yoake",
                        "type": "MOVIE",
                        "episodes": 1,
                        "status": "FINISHED",
                        "animeSeason": {
                            "season": "WINTER",
                            "year": 2019,
                        },
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": ["adventure"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    release = load_manami_release(fixture_path)
    entities = normalize_manami_release(release)

    assert len(entities) == 2

    made_in_abyss = entities[0]
    assert made_in_abyss.entity_id == "anime:manami:anidb:12681"
    assert made_in_abyss.canonical_source == "https://anidb.net/anime/12681"
    assert made_in_abyss.record_source == "manami-project/anime-offline-database release 2026-04-02"
    assert made_in_abyss.original_title == "メイドインアビス"
    assert made_in_abyss.synonyms == ["メイドインアビス", "Made in Abyss"]
    assert made_in_abyss.tags == ["adventure", "fantasy"]
    assert [edge.target for edge in made_in_abyss.related] == [
        "anime:manami:anidb:13612",
        "anime:manami:anilist:101343",
    ]
    assert all(edge.relationship == "related_anime" for edge in made_in_abyss.related)
    assert [edge.supporting_urls for edge in made_in_abyss.related] == [
        ["https://anidb.net/anime/13612"],
        ["https://anilist.co/anime/101343"],
    ]
    assert made_in_abyss.field_sources == {
        "title": ["https://anidb.net/anime/12681"],
        "episodes": ["https://anidb.net/anime/12681"],
        "status": ["https://anidb.net/anime/12681"],
        "release_year": ["https://anidb.net/anime/12681"],
    }

    recap_movie = entities[1]
    assert recap_movie.entity_id == "anime:manami:anilist:101343"
    assert recap_movie.canonical_source == "https://anilist.co/anime/101343"
    assert recap_movie.release_year == 2019


def test_parse_manami_source_ref_supports_multiple_provider_urls() -> None:
    assert parse_manami_source_ref("https://anidb.net/anime/12681").entity_id == "anime:manami:anidb:12681"
    assert parse_manami_source_ref("https://anilist.co/anime/97986").entity_id == "anime:manami:anilist:97986"
    assert (
        parse_manami_source_ref("https://myanimelist.net/anime/34599/Made_in_Abyss").entity_id
        == "anime:manami:myanimelist:34599"
    )


def test_normalize_manami_release_can_filter_by_title(tmp_path: Path) -> None:
    fixture_path = tmp_path / "manami-release.json"
    fixture_path.write_text(
        json.dumps(
            {
                "repository": "https://github.com/manami-project/anime-offline-database",
                "lastUpdate": "2026-04-02",
                "data": [
                    {
                        "sources": ["https://anidb.net/anime/12681"],
                        "title": "Made in Abyss",
                        "type": "TV",
                        "episodes": 13,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SUMMER", "year": 2017},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                    {
                        "sources": ["https://anidb.net/anime/23"],
                        "title": "Cowboy Bebop",
                        "type": "TV",
                        "episodes": 26,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SPRING", "year": 1998},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    release = load_manami_release(fixture_path)

    entities = normalize_manami_release(release, title_contains="abyss")

    assert [entity.title for entity in entities] == ["Made in Abyss"]


def test_write_normalized_manami_seed_emits_jsonl_subset(tmp_path: Path) -> None:
    fixture_path = tmp_path / "manami-release.json"
    fixture_path.write_text(
        json.dumps(
            {
                "repository": "https://github.com/manami-project/anime-offline-database",
                "lastUpdate": "2026-04-02",
                "data": [
                    {
                        "sources": ["https://anidb.net/anime/12681"],
                        "title": "Made in Abyss",
                        "type": "TV",
                        "episodes": 13,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SUMMER", "year": 2017},
                        "synonyms": ["メイドインアビス"],
                        "relatedAnime": ["https://anidb.net/anime/13612"],
                        "tags": ["adventure"],
                    },
                    {
                        "sources": ["https://anidb.net/anime/23"],
                        "title": "Cowboy Bebop",
                        "type": "TV",
                        "episodes": 26,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SPRING", "year": 1998},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "subset.jsonl"

    written_path = write_normalized_manami_seed(
        release_path=fixture_path,
        output_path=output_path,
        title_contains="made in abyss",
    )

    lines = written_path.read_text(encoding="utf-8").splitlines()

    assert written_path == output_path
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["entity_id"] == "anime:manami:anidb:12681"
    assert payload["title"] == "Made in Abyss"


def test_normalize_manami_release_skips_entries_without_supported_sources(tmp_path: Path) -> None:
    fixture_path = tmp_path / "manami-release.json"
    fixture_path.write_text(
        json.dumps(
            {
                "repository": "https://github.com/manami-project/anime-offline-database",
                "lastUpdate": "2026-04-02",
                "data": [
                    {
                        "sources": ["https://animecountdown.com/644821"],
                        "title": "Made in Abyss",
                        "type": "TV",
                        "episodes": 13,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SUMMER", "year": 2017},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                    {
                        "sources": ["https://anidb.net/anime/23"],
                        "title": "Cowboy Bebop",
                        "type": "TV",
                        "episodes": 26,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SPRING", "year": 1998},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    release = load_manami_release(fixture_path)

    entities = normalize_manami_release(release)

    assert [entity.title for entity in entities] == ["Cowboy Bebop"]


def test_normalize_manami_release_batch_accounts_for_rejected_candidates(tmp_path: Path) -> None:
    fixture_path = tmp_path / "manami-release.json"
    fixture_path.write_text(
        json.dumps(
            {
                "repository": "https://github.com/manami-project/anime-offline-database",
                "lastUpdate": "2026-04-02",
                "data": [
                    {
                        "sources": ["https://animecountdown.com/644821"],
                        "title": "Unsupported Source",
                        "type": "TV",
                        "episodes": 13,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SUMMER", "year": 2017},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                    {
                        "sources": ["https://anidb.net/anime/23"],
                        "type": "TV",
                        "episodes": 26,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SPRING", "year": 1998},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                    {
                        "sources": ["https://anidb.net/anime/12681"],
                        "title": "Missing Year",
                        "type": "TV",
                        "episodes": 13,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SUMMER", "year": None},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                    {
                        "sources": ["https://anidb.net/anime/1"],
                        "title": "Kept Anime",
                        "type": "TV",
                        "episodes": 1,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SPRING", "year": 2001},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    batch = normalize_manami_release_batch(load_manami_release(fixture_path))

    assert [entity.title for entity in batch.entities] == ["Kept Anime"]
    assert batch.selected_candidate_count == 4
    assert batch.normalized_record_count == 1
    assert batch.skipped_candidate_count == 3
    assert batch.rejection_reasons == {
        "missing_required_field": 2,
        "unsupported_source_url": 1,
    }
    assert [(rejection.candidate_index, rejection.reason, rejection.detail) for rejection in batch.rejections] == [
        (0, "unsupported_source_url", "sources"),
        (1, "missing_required_field", "title"),
        (2, "missing_required_field", "animeSeason.year"),
    ]


def test_normalize_manami_entry_ignores_unsupported_hosts_when_supported_ones_exist() -> None:
    entry = ManamiAnimeEntry.model_validate(
        {
            "sources": [
                "https://animecountdown.com/644821",
                "https://anidb.net/anime/12681",
                "https://anilist.co/anime/97986",
            ],
            "title": "Made in Abyss",
            "type": "TV",
            "episodes": 13,
            "status": "FINISHED",
            "animeSeason": {"season": "SUMMER", "year": 2017},
            "synonyms": [],
            "relatedAnime": [
                "https://animecountdown.com/740881",
                "https://anidb.net/anime/13612",
            ],
            "tags": [],
        }
    )

    entity = normalize_manami_entry(
        entry,
        record_source="unused",
    )

    assert entity.sources == [
        "https://anidb.net/anime/12681",
        "https://anilist.co/anime/97986",
    ]
    assert [edge.target for edge in entity.related] == ["anime:manami:anidb:13612"]
    assert entity.related[0].supporting_urls == ["https://anidb.net/anime/13612"]


def test_normalize_manami_entry_requires_release_year(tmp_path: Path) -> None:
    fixture_path = tmp_path / "missing-year.json"
    fixture_path.write_text(
        json.dumps(
            {
                "repository": "https://github.com/manami-project/anime-offline-database",
                "lastUpdate": "2026-04-02",
                "data": [
                    {
                        "sources": ["https://anidb.net/anime/23"],
                        "title": "Cowboy Bebop",
                        "type": "TV",
                        "episodes": 26,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SPRING", "year": None},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"missing animeSeason\.year"):
        normalize_manami_entry(
            ManamiAnimeEntry.model_validate(load_manami_release(fixture_path).data[0]),
            record_source="manami-project/anime-offline-database release 2026-04-02",
        )


def test_parse_manami_source_ref_rejects_unknown_hosts() -> None:
    with pytest.raises(ValueError, match="unsupported manami source url"):
        parse_manami_source_ref("https://example.com/anime/42")
