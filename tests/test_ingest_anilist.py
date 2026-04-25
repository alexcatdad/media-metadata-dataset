from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch

import media_offline_database.ingest_anilist as ingest_anilist


def test_normalize_anilist_search_result_builds_bootstrap_entity(
    monkeypatch: MonkeyPatch,
) -> None:
    def fake_fetch(search: str):
        assert search == "Golden Time"
        return [
            ingest_anilist.AniListSearchMedia(
                id=17895,
                title=ingest_anilist.AniListTitle(
                    romaji="Golden Time",
                    english="Golden Time",
                    native="ゴールデンタイム",
                ),
                synonyms=["Golden Time"],
                genres=["Drama", "Romance"],
                tags=[
                    ingest_anilist.AniListTag(name="College", rank=85),
                    ingest_anilist.AniListTag(name="Primarily Adult Cast", rank=78),
                ],
                format="TV",
                status="FINISHED",
                episodes=24,
                startDate=ingest_anilist.AniListStartDate(year=2013),
                siteUrl="https://anilist.co/anime/17895",
                studios=ingest_anilist.AniListStudiosPayload(
                    edges=[
                        ingest_anilist.AniListStudioEdge(
                            isMain=True,
                            node=ingest_anilist.AniListStudioNode(name="J.C.STAFF"),
                        )
                    ]
                ),
                staff=ingest_anilist.AniListStaffPayload(
                    edges=[
                        ingest_anilist.AniListStaffEdge(
                            role="Original Creator",
                            node=ingest_anilist.AniListStaffNode(
                                name=ingest_anilist.AniListStaffName(full="Yuyuko Tokemiya")
                            ),
                        )
                    ]
                ),
            )
        ]

    monkeypatch.setattr(ingest_anilist, "fetch_anilist_search_results", fake_fetch)
    entity = ingest_anilist.normalize_anilist_search_result("Golden Time")

    assert entity.entity_id == "anime:local:anilist:17895"
    assert entity.title == "Golden Time"
    assert entity.genres == ["Drama", "Romance"]
    assert entity.studios == ["J.C.STAFF"]
    assert entity.creators == ["Yuyuko Tokemiya"]
    assert "College" in entity.tags


def test_write_anilist_search_seed_writes_jsonl(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def fake_normalize(search: str) -> ingest_anilist.BootstrapEntity:
        return ingest_anilist.BootstrapEntity(
            entity_id="anime:local:anilist:17895",
            domain="anime",
            canonical_source="https://anilist.co/anime/17895",
            source_role=ingest_anilist.SourceRole.LOCAL_EVIDENCE,
            record_source="test",
            title=search,
            media_type="TV",
            status="FINISHED",
            release_year=2013,
        )

    monkeypatch.setattr(
        ingest_anilist,
        "normalize_anilist_search_result",
        fake_normalize,
    )
    output_path = tmp_path / "golden-time.jsonl"

    written_path = ingest_anilist.write_anilist_search_seed(
        search="Golden Time",
        output_path=output_path,
    )

    payload = json.loads(written_path.read_text(encoding="utf-8").strip())
    assert written_path == output_path
    assert payload["title"] == "Golden Time"
