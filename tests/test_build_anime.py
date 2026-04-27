from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from media_offline_database.bootstrap import load_bootstrap_entities
from media_offline_database.build_anime import build_manami_anime_artifact
from media_offline_database.cli import app
from media_offline_database.enrich_anilist_metadata import AniListResolvedMetadata
from media_offline_database.enrich_anilist_relations import AniListResolvedRelation
from media_offline_database.ingest_normalization import (
    load_adapter_rejection_summary,
    load_provider_runs,
    load_source_snapshots,
)

runner = CliRunner()


def test_build_manami_anime_artifact_runs_full_pipeline(tmp_path: Path) -> None:
    release_path = tmp_path / "manami-release.json"
    release_path.write_text(
        json.dumps(
            {
                "repository": "https://github.com/manami-project/anime-offline-database",
                "lastUpdate": "2026-04-25",
                "data": [
                    {
                        "sources": [
                            "https://anidb.net/anime/12681",
                            "https://anilist.co/anime/97986",
                        ],
                        "title": "Made in Abyss",
                        "type": "TV",
                        "episodes": 13,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SUMMER", "year": 2017},
                        "synonyms": ["Made in Abyss", "メイドインアビス"],
                        "relatedAnime": [
                            "https://anidb.net/anime/14177",
                            "https://anilist.co/anime/109911",
                        ],
                        "tags": ["Adventure"],
                    },
                    {
                        "sources": [
                            "https://anidb.net/anime/14177",
                            "https://anilist.co/anime/109911",
                        ],
                        "title": "Made in Abyss Movie 3: Fukaki Tamashii no Reimei",
                        "type": "MOVIE",
                        "episodes": 1,
                        "status": "FINISHED",
                        "animeSeason": {"season": "WINTER", "year": 2020},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": ["Adventure"],
                    },
                    {
                        "sources": ["https://animecountdown.com/644821"],
                        "title": "Unsupported Source Anime",
                        "type": "TV",
                        "episodes": 1,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SPRING", "year": 2026},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    relation_fetch_calls: list[int] = []
    metadata_fetch_calls: list[int] = []

    def fake_relation_fetcher(anilist_id: int) -> list[AniListResolvedRelation]:
        relation_fetch_calls.append(anilist_id)
        if anilist_id != 97986:
            return []

        return [
            AniListResolvedRelation(
                target_anilist_id=109911,
                relation_type="SEQUEL",
                target_format="MOVIE",
            )
        ]

    def fake_metadata_fetcher(anilist_id: int) -> AniListResolvedMetadata:
        metadata_fetch_calls.append(anilist_id)
        metadata_by_id = {
            97986: AniListResolvedMetadata(
                genres=["Adventure", "Drama"],
                studios=["Kinema Citrus"],
                creators=["Akihito Tsukushi"],
            ),
            109911: AniListResolvedMetadata(
                genres=["Adventure", "Mystery"],
                studios=["Kinema Citrus"],
                creators=["Akihito Tsukushi"],
            ),
        }
        return metadata_by_id[anilist_id]

    result = build_manami_anime_artifact(
        release_path=release_path,
        output_dir=tmp_path / "out",
        fetch_relations=fake_relation_fetcher,
        fetch_metadata=fake_metadata_fetcher,
    )

    normalized_entities = load_bootstrap_entities(result.normalized_seed_path)
    relation_entities = load_bootstrap_entities(result.relation_enriched_seed_path)
    metadata_entities = load_bootstrap_entities(result.metadata_enriched_seed_path)
    source_snapshots = load_source_snapshots(result.source_snapshot_path)
    provider_runs = load_provider_runs(result.provider_run_path)
    rejection_summary = load_adapter_rejection_summary(result.rejection_summary_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert relation_fetch_calls == [97986, 109911]
    assert metadata_fetch_calls == [97986, 109911]
    assert result.snapshot_id == "2026-04-25"
    assert result.start_offset == 0
    assert result.end_offset == 3
    assert result.next_offset == 3
    assert result.total_candidates == 3
    assert result.selected_candidate_count == 3
    assert result.normalized_record_count == 2
    assert result.skipped_candidate_count == 1
    assert result.rejection_reasons == {"unsupported_source_url": 1}
    assert result.last_completed_item_key == "anime:manami:anidb:14177"
    assert source_snapshots[0].source_snapshot_id == "manami:2026-04-25"
    assert source_snapshots[0].record_count == 2
    assert provider_runs[0].source_snapshot_id == source_snapshots[0].source_snapshot_id
    assert provider_runs[0].secret_refs == ()
    assert (
        "Selected candidates: 3; normalized records: 2; skipped candidates: 1"
        in (provider_runs[0].notes or "")
    )
    assert rejection_summary.selected_candidate_count == 3
    assert rejection_summary.normalized_record_count == 2
    assert rejection_summary.skipped_candidate_count == 1
    assert rejection_summary.rejection_reasons == {"unsupported_source_url": 1}
    assert rejection_summary.rejections[0].candidate_index == 2
    assert rejection_summary.rejections[0].detail == "sources"

    assert normalized_entities[0].related[0].relationship == "related_anime"
    assert len(relation_entities[0].related) == 1
    assert relation_entities[0].related[0].relationship == "sequel"
    assert relation_entities[0].related[0].target == "anime:manami:anidb:14177"
    assert relation_entities[0].related[0].supporting_urls == [
        "https://anidb.net/anime/14177",
        "https://anilist.co/anime/109911",
        "https://anilist.co/anime/97986",
    ]

    assert metadata_entities[0].genres == ["Adventure", "Drama"]
    assert metadata_entities[0].studios == ["Kinema Citrus"]
    assert metadata_entities[0].creators == ["Akihito Tsukushi"]
    assert metadata_entities[0].field_sources["genres"] == [
        "https://anilist.co/anime/97986"
    ]
    assert metadata_entities[1].genres == ["Adventure", "Mystery"]

    assert result.manifest_path.parent == tmp_path / "out" / "compiled"
    assert manifest["row_count"] == 2
    assert manifest["relationship_row_count"] == 1
    assert manifest["domains"] == ["anime"]


def test_build_manami_anime_artifact_passes_title_filter_to_pipeline(tmp_path: Path) -> None:
    release_path = tmp_path / "manami-release.json"
    release_path.write_text(
        json.dumps(
            {
                "repository": "https://github.com/manami-project/anime-offline-database",
                "lastUpdate": "2026-04-25",
                "data": [
                    {
                        "sources": [
                            "https://anidb.net/anime/12681",
                            "https://anilist.co/anime/97986",
                        ],
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
                        "sources": [
                            "https://anidb.net/anime/23",
                            "https://anilist.co/anime/23",
                        ],
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

    relation_fetch_calls: list[int] = []
    metadata_fetch_calls: list[int] = []

    result = build_manami_anime_artifact(
        release_path=release_path,
        output_dir=tmp_path / "out",
        title_contains="abyss",
        fetch_relations=lambda anilist_id: relation_fetch_calls.append(anilist_id) or [],
        fetch_metadata=lambda anilist_id: (
            metadata_fetch_calls.append(anilist_id)
            or AniListResolvedMetadata(
                genres=["Adventure"],
                studios=["Kinema Citrus"],
                creators=["Akihito Tsukushi"],
            )
        ),
    )

    metadata_entities = load_bootstrap_entities(result.metadata_enriched_seed_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert [entity.title for entity in metadata_entities] == ["Made in Abyss"]
    assert relation_fetch_calls == [97986]
    assert metadata_fetch_calls == [97986]
    assert result.total_candidates == 1
    assert manifest["row_count"] == 1
    assert manifest["relationship_row_count"] == 0


def test_build_manami_anime_artifact_supports_batch_offsets(tmp_path: Path) -> None:
    release_path = tmp_path / "manami-release.json"
    release_path.write_text(
        json.dumps(
            {
                "repository": "https://github.com/manami-project/anime-offline-database",
                "lastUpdate": "2026-04-25",
                "data": [
                    {
                        "sources": [
                            "https://anidb.net/anime/12681",
                            "https://anilist.co/anime/97986",
                        ],
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
                        "sources": [
                            "https://anidb.net/anime/23",
                            "https://anilist.co/anime/1",
                        ],
                        "title": "Cowboy Bebop",
                        "type": "TV",
                        "episodes": 26,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SPRING", "year": 1998},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                    {
                        "sources": [
                            "https://anidb.net/anime/14177",
                            "https://anilist.co/anime/109911",
                        ],
                        "title": "Made in Abyss Movie 3: Fukaki Tamashii no Reimei",
                        "type": "MOVIE",
                        "episodes": 1,
                        "status": "FINISHED",
                        "animeSeason": {"season": "WINTER", "year": 2020},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = build_manami_anime_artifact(
        release_path=release_path,
        output_dir=tmp_path / "out",
        start_offset=1,
        batch_size=1,
        fetch_relations=lambda _anilist_id: [],
        fetch_metadata=lambda _anilist_id: AniListResolvedMetadata(
            genres=["Adventure"],
            studios=["Bones"],
            creators=["Someone"],
        ),
    )

    metadata_entities = load_bootstrap_entities(result.metadata_enriched_seed_path)

    assert [entity.title for entity in metadata_entities] == ["Cowboy Bebop"]
    assert result.start_offset == 1
    assert result.end_offset == 2
    assert result.next_offset == 2
    assert result.total_candidates == 3


def test_anime_build_cli_rejects_missing_release_path() -> None:
    result = runner.invoke(
        app,
        [
            "anime-build",
            "--input-path",
            "does-not-exist.json",
        ],
    )

    assert result.exit_code != 0
    assert result.exception is not None
