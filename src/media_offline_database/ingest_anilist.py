from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

from media_offline_database.bootstrap import BootstrapEntity
from media_offline_database.sources import SourceRole

_ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
_ANILIST_SEARCH_QUERY = """
query ($search: String!) {
  Page(page: 1, perPage: 10) {
    media(search: $search, type: ANIME) {
      id
      title {
        romaji
        english
        native
      }
      synonyms
      genres
      tags {
        name
        rank
      }
      format
      status
      episodes
      startDate {
        year
      }
      siteUrl
      studios {
        edges {
          isMain
          node {
            name
          }
        }
      }
      staff(sort: [RELEVANCE, ROLE, ID]) {
        edges {
          role
          node {
            name {
              full
              native
            }
          }
        }
      }
    }
  }
}
"""
_CREATOR_ROLE_ALLOWLIST = {
    "creator",
    "original creator",
    "original story",
    "original work",
}


class AniListTitle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    romaji: str | None = None
    english: str | None = None
    native: str | None = None


class AniListTag(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    rank: int | None = None


class AniListStudioNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str


class AniListStudioEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    isMain: bool = False
    node: AniListStudioNode


class AniListStudiosPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    edges: list[AniListStudioEdge] = Field(
        default_factory=lambda: cast(list[AniListStudioEdge], [])
    )


class AniListStaffName(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full: str | None = None
    native: str | None = None


class AniListStaffNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: AniListStaffName


class AniListStaffEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str | None = None
    node: AniListStaffNode


class AniListStaffPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    edges: list[AniListStaffEdge] = Field(
        default_factory=lambda: cast(list[AniListStaffEdge], [])
    )


class AniListStartDate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    year: int | None = None


class AniListSearchMedia(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    title: AniListTitle
    synonyms: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    tags: list[AniListTag] = Field(default_factory=lambda: cast(list[AniListTag], []))
    format: str | None = None
    status: str | None = None
    episodes: int | None = None
    startDate: AniListStartDate = Field(default_factory=AniListStartDate)
    siteUrl: str | None = None
    studios: AniListStudiosPayload = Field(default_factory=AniListStudiosPayload)
    staff: AniListStaffPayload = Field(default_factory=AniListStaffPayload)


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


def fetch_anilist_search_results(
    search: str,
    *,
    timeout_seconds: float = 20.0,
) -> list[AniListSearchMedia]:
    response = httpx.post(
        _ANILIST_GRAPHQL_URL,
        json={
            "query": _ANILIST_SEARCH_QUERY,
            "variables": {"search": search},
        },
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "codex-media-metadata-dataset/1.0",
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = AniListSearchResponse.model_validate(response.json())
    if payload.data is None:
        return []
    return payload.data.Page.media


def normalize_anilist_search_result(search: str) -> BootstrapEntity:
    results = fetch_anilist_search_results(search)
    if not results:
        raise ValueError(f"no AniList anime results found for search: {search}")

    selected = _select_best_match(results, search)
    title = (
        selected.title.english
        or selected.title.romaji
        or selected.title.native
        or search
    )
    if selected.startDate.year is None:
        raise ValueError(f"AniList result missing start year for search: {search}")
    if selected.siteUrl is None:
        raise ValueError(f"AniList result missing siteUrl for search: {search}")

    return BootstrapEntity(
        entity_id=f"anime:local:anilist:{selected.id}",
        domain="anime",
        canonical_source=selected.siteUrl,
        source_role=SourceRole.LOCAL_EVIDENCE,
        record_source=f"AniList title search snapshot {datetime.now(UTC).date().isoformat()}",
        title=title,
        original_title=selected.title.native,
        media_type=selected.format or "UNKNOWN",
        status=selected.status or "UNKNOWN",
        release_year=selected.startDate.year,
        episodes=selected.episodes,
        synonyms=_dedupe_strings(
            [
                value
                for value in [
                    selected.title.romaji,
                    selected.title.english,
                    selected.title.native,
                    *selected.synonyms,
                ]
                if value
            ]
        ),
        sources=[selected.siteUrl],
        genres=_dedupe_strings(selected.genres),
        studios=_main_or_all_studios(selected),
        creators=_creator_names(selected),
        tags=_dedupe_strings([tag.name for tag in selected.tags]),
        field_sources={
            "title": [selected.siteUrl],
            "release_year": [selected.siteUrl],
            "genres": [selected.siteUrl],
            "studios": [selected.siteUrl],
            "creators": [selected.siteUrl],
            "tags": [selected.siteUrl],
        },
    )


def write_anilist_search_seed(
    *,
    search: str,
    output_path: Path,
) -> Path:
    entity = normalize_anilist_search_result(search)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(entity.model_dump_json() + "\n", encoding="utf-8")
    return output_path


def _select_best_match(results: list[AniListSearchMedia], search: str) -> AniListSearchMedia:
    normalized_search = search.casefold().strip()

    def score(result: AniListSearchMedia) -> tuple[int, int, int]:
        titles = [
            value
            for value in [result.title.romaji, result.title.english, result.title.native, *result.synonyms]
            if value
        ]
        exact = any(title.casefold().strip() == normalized_search for title in titles)
        return (
            1 if exact else 0,
            result.episodes or 0,
            result.startDate.year or 0,
        )

    return max(results, key=score)


def _main_or_all_studios(result: AniListSearchMedia) -> list[str]:
    main_studios = [edge.node.name for edge in result.studios.edges if edge.isMain]
    if main_studios:
        return _dedupe_strings(main_studios)
    return _dedupe_strings([edge.node.name for edge in result.studios.edges])


def _creator_names(result: AniListSearchMedia) -> list[str]:
    return _dedupe_strings(
        [
            edge.node.name.full or edge.node.name.native
            for edge in result.staff.edges
            if _is_creator_role(edge.role)
        ]
    )


def _is_creator_role(role: str | None) -> bool:
    if role is None:
        return False
    normalized = " ".join(role.lower().strip().split())
    return normalized in _CREATOR_ROLE_ALLOWLIST


def _dedupe_strings(values: Sequence[str | None]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
