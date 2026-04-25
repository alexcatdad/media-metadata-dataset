from __future__ import annotations

from media_offline_database.bootstrap import BootstrapEntity
from media_offline_database.corpus_concept_search import search_corpus_by_concept
from media_offline_database.sources import SourceRole


def test_search_corpus_by_concept_matches_genres_and_tags() -> None:
    entities = [
        BootstrapEntity(
            entity_id="anime:test:golden-time",
            domain="anime",
            canonical_source="https://anilist.co/anime/17895",
            source_role=SourceRole.BACKBONE_SOURCE,
            record_source="test",
            title="Golden Time",
            media_type="TV",
            status="FINISHED",
            release_year=2013,
            genres=["Drama", "Romance"],
            tags=["College", "Primarily Adult Cast", "Amnesia"],
        ),
        BootstrapEntity(
            entity_id="anime:test:high-school",
            domain="anime",
            canonical_source="https://anilist.co/anime/1",
            source_role=SourceRole.LOCAL_EVIDENCE,
            record_source="test",
            title="High School Love",
            media_type="TV",
            status="FINISHED",
            release_year=2010,
            genres=["Romance"],
            tags=["School", "Love Triangle"],
        ),
    ]

    preview = search_corpus_by_concept(
        entities,
        query="romance anime where characters are in university/college",
        limit=5,
    )

    assert preview.filters.genres == ["Romance"]
    assert preview.filters.tags == ["College", "Primarily Adult Cast"]
    assert [match.title for match in preview.matches] == ["Golden Time"]
    assert preview.matches[0].matched_genres == ["Romance"]
    assert preview.matches[0].matched_tags == ["College", "Primarily Adult Cast"]
