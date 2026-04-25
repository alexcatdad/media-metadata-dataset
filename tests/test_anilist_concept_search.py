from __future__ import annotations

from media_offline_database.anilist_concept_search import (
    AniListSearchMedia,
    AniListStartDate,
    AniListTag,
    AniListTitle,
    ConceptSearchFilters,
    parse_concept_query,
    search_anime_by_concept,
)


def test_parse_concept_query_maps_romance_and_college_language() -> None:
    filters = parse_concept_query("romance anime where characters are in university/college")

    assert filters.genres == ["Romance"]
    assert filters.tags == ["College", "Primarily Adult Cast"]
    assert filters.notes


def test_search_anime_by_concept_returns_structured_matches() -> None:
    def fake_fetch(
        filters: ConceptSearchFilters,
        limit: int,
    ) -> list[AniListSearchMedia]:
        assert filters.genres == ["Romance"]
        assert filters.tags == ["College", "Primarily Adult Cast"]
        assert limit == 25
        return [
            AniListSearchMedia(
                id=17895,
                title=AniListTitle(
                    romaji="Golden Time",
                    english="Golden Time",
                    native="ゴールデンタイム",
                ),
                genres=["Drama", "Romance"],
                tags=[
                    AniListTag(name="College", rank=85),
                    AniListTag(name="Primarily Adult Cast", rank=78),
                ],
                format="TV",
                averageScore=75,
                startDate=AniListStartDate(year=2013),
                siteUrl="https://anilist.co/anime/17895",
            )
        ]

    filters, matches = search_anime_by_concept(
        "romance anime where characters are in university/college",
        limit=5,
        fetch_matches=fake_fetch,
    )

    assert filters.genres == ["Romance"]
    assert matches[0].title == "Golden Time"
    assert matches[0].matched_genres == ["Romance"]
    assert matches[0].matched_tags == ["College", "Primarily Adult Cast"]
    assert matches[0].english_title == "Golden Time"
