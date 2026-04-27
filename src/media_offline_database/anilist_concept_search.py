from __future__ import annotations

import re
from collections.abc import Callable
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from media_offline_database.anilist_http import post_anilist_graphql

_WHITESPACE_RE = re.compile(r"\s+")
_GENRE_KEYWORDS = {
    "action": "Action",
    "adventure": "Adventure",
    "comedy": "Comedy",
    "drama": "Drama",
    "fantasy": "Fantasy",
    "romance": "Romance",
    "slice of life": "Slice of Life",
}
_TAG_RULES: tuple[tuple[set[str], list[str]], ...] = (
    ({"college", "university"}, ["College", "Primarily Adult Cast"]),
    ({"adult", "adults"}, ["Primarily Adult Cast"]),
)
_SEARCH_QUERY = """
query ($genreIn: [String], $tagIn: [String], $page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    media(type: ANIME, genre_in: $genreIn, tag_in: $tagIn, sort: SCORE_DESC) {
      id
      title {
        romaji
        english
        native
      }
      genres
      tags {
        name
        rank
      }
      format
      status
      averageScore
      startDate {
        year
      }
      siteUrl
    }
  }
}
"""


class AniListTag(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    rank: int | None = None


class AniListTitle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    romaji: str | None = None
    english: str | None = None
    native: str | None = None


class AniListStartDate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    year: int | None = None


class AniListSearchMedia(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    title: AniListTitle
    genres: list[str] = Field(default_factory=list)
    tags: list[AniListTag] = Field(default_factory=lambda: cast(list[AniListTag], []))
    format: str | None = None
    status: str | None = None
    averageScore: int | None = None
    startDate: AniListStartDate = Field(default_factory=AniListStartDate)
    siteUrl: str | None = None


class AniListSearchPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    media: list[AniListSearchMedia] = Field(
        default_factory=lambda: cast(list[AniListSearchMedia], [])
    )


class AniListSearchData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    Page: AniListSearchPage


class AniListSearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: AniListSearchData | None = None


class ConceptSearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_query: str
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ConceptSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anilist_id: int
    title: str
    english_title: str | None = None
    year: int | None = None
    format: str | None = None
    average_score: int | None = None
    site_url: str | None = None
    matched_genres: list[str] = Field(default_factory=list)
    matched_tags: list[str] = Field(default_factory=list)
    matched_tag_strength: int = 0
    rationale: str


type AniListConceptFetcher = Callable[[ConceptSearchFilters, int], list[AniListSearchMedia]]


def parse_concept_query(query: str) -> ConceptSearchFilters:
    normalized = _normalize_text(query)
    genres: list[str] = []
    tags: list[str] = []
    notes: list[str] = []

    for keyword, genre in _GENRE_KEYWORDS.items():
        if keyword in normalized:
            genres.append(genre)

    token_set = set(normalized.split())
    for trigger_tokens, mapped_tags in _TAG_RULES:
        if token_set & trigger_tokens or any(token in normalized for token in trigger_tokens):
            tags.extend(mapped_tags)

    if "university" in normalized or "college" in normalized:
        notes.append("mapped university/college language to AniList College + Primarily Adult Cast tags")

    if "romance" in normalized:
        notes.append("mapped romance language to AniList Romance genre")

    return ConceptSearchFilters(
        original_query=query,
        genres=list(dict.fromkeys(genres)),
        tags=list(dict.fromkeys(tags)),
        notes=notes,
    )


def fetch_anilist_concept_matches(
    filters: ConceptSearchFilters,
    limit: int = 10,
    *,
    timeout_seconds: float = 20.0,
) -> list[AniListSearchMedia]:
    response = post_anilist_graphql(
        query=_SEARCH_QUERY,
        variables={
            "genreIn": filters.genres or None,
            "tagIn": filters.tags or None,
            "page": 1,
            "perPage": limit,
        },
        timeout_seconds=timeout_seconds,
    )
    payload = AniListSearchResponse.model_validate(response.json())
    if payload.data is None:
        return []
    media_items: list[AniListSearchMedia] = payload.data.Page.media
    return media_items


def search_anime_by_concept(
    query: str,
    *,
    limit: int = 10,
    fetch_matches: AniListConceptFetcher = fetch_anilist_concept_matches,
) -> tuple[ConceptSearchFilters, list[ConceptSearchResult]]:
    filters = parse_concept_query(query)
    fetch_limit = max(limit * 5, 25)
    matches = fetch_matches(filters, fetch_limit)
    results = [
        _concept_result(media, filters=filters)
        for media in matches
    ]
    results.sort(key=_result_sort_key, reverse=True)
    return filters, results[:limit]


def _concept_result(
    media: AniListSearchMedia,
    *,
    filters: ConceptSearchFilters,
) -> ConceptSearchResult:
    media_tags = {tag.name for tag in media.tags}
    media_tag_ranks = {tag.name: tag.rank or 0 for tag in media.tags}
    matched_genres = [genre for genre in filters.genres if genre in media.genres]
    matched_tags = [tag for tag in filters.tags if tag in media_tags]
    matched_tag_strength = sum(media_tag_ranks[tag] for tag in matched_tags)
    title = media.title.romaji or media.title.english or media.title.native or str(media.id)
    rationale_parts: list[str] = []
    if matched_genres:
        rationale_parts.append(f"genre match: {', '.join(matched_genres)}")
    if matched_tags:
        rationale_parts.append(f"tag match: {', '.join(matched_tags)}")
    if media.averageScore is not None:
        rationale_parts.append(f"AniList score {media.averageScore}")

    return ConceptSearchResult(
        anilist_id=media.id,
        title=title,
        english_title=media.title.english,
        year=media.startDate.year,
        format=media.format,
        average_score=media.averageScore,
        site_url=media.siteUrl,
        matched_genres=matched_genres,
        matched_tags=matched_tags,
        matched_tag_strength=matched_tag_strength,
        rationale="; ".join(rationale_parts) if rationale_parts else "matched AniList filters",
    )


def _result_sort_key(result: ConceptSearchResult) -> tuple[int, int, int, int]:
    return (
        len(result.matched_genres),
        len(result.matched_tags),
        result.matched_tag_strength,
        result.average_score or 0,
    )


def _normalize_text(value: str) -> str:
    normalized = value.casefold().replace("/", " ")
    return _WHITESPACE_RE.sub(" ", normalized).strip()
