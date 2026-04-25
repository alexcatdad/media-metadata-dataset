from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from media_offline_database.bootstrap import BootstrapEntity, BootstrapRelatedEdge
from media_offline_database.sources import SourceRole

_ANIDB_PATTERN = re.compile(r"^/anime/(?P<id>\d+)$")
_ANILIST_PATTERN = re.compile(r"^/anime/(?P<id>\d+)$")
_MAL_PATTERN = re.compile(r"^/anime/(?P<id>\d+)(?:/.*)?$")
_KITSU_PATTERN = re.compile(r"^/anime/(?P<id>[^/]+)$")
_SIMKL_PATTERN = re.compile(r"^/anime/(?P<id>\d+)(?:/.*)?$")
_ANIME_PLANET_PATTERN = re.compile(r"^/anime/(?P<id>[^/]+)$")

_SOURCE_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("anidb.net", "anidb", _ANIDB_PATTERN),
    ("anilist.co", "anilist", _ANILIST_PATTERN),
    ("myanimelist.net", "myanimelist", _MAL_PATTERN),
    ("kitsu.app", "kitsu", _KITSU_PATTERN),
    ("simkl.com", "simkl", _SIMKL_PATTERN),
    ("anime-planet.com", "anime-planet", _ANIME_PLANET_PATTERN),
)

_PREFERRED_SOURCE_ORDER = (
    "anidb",
    "anilist",
    "myanimelist",
    "kitsu",
    "simkl",
    "anime-planet",
)


class ManamiAnimeSeason(BaseModel):
    model_config = ConfigDict(extra="ignore")

    season: str | None = None
    year: int | None = None


class ManamiAnimeEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sources: list[str]
    title: str
    type: Literal["TV", "MOVIE", "OVA", "ONA", "SPECIAL", "UNKNOWN"]
    episodes: int | None = None
    status: Literal["FINISHED", "ONGOING", "UPCOMING", "UNKNOWN"]
    animeSeason: ManamiAnimeSeason = Field(default_factory=ManamiAnimeSeason)
    synonyms: list[str] = Field(default_factory=list)
    relatedAnime: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ManamiRelease(BaseModel):
    model_config = ConfigDict(extra="ignore")

    repository: str
    lastUpdate: str
    data: list[ManamiAnimeEntry]


class ParsedSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    external_id: str
    url: str

    @property
    def entity_id(self) -> str:
        return f"anime:manami:{self.provider}:{self.external_id}"


def load_manami_release(path: Path) -> ManamiRelease:
    return ManamiRelease.model_validate(json.loads(path.read_text(encoding="utf-8")))


def parse_manami_source_ref(url: str) -> ParsedSourceRef:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    for candidate_host, provider, pattern in _SOURCE_PATTERNS:
        if host != candidate_host:
            continue

        match = pattern.match(parsed.path)
        if match is None:
            continue

        return ParsedSourceRef(
            provider=provider,
            external_id=match.group("id"),
            url=url,
        )

    raise ValueError(f"unsupported manami source url: {url}")


def normalize_manami_entry(
    entry: ManamiAnimeEntry,
    *,
    record_source: str,
) -> BootstrapEntity:
    if entry.animeSeason.year is None:
        raise ValueError(f"manami entry is missing animeSeason.year: {entry.title}")

    parsed_sources = _parse_supported_source_refs(entry.sources)
    if not parsed_sources:
        raise ValueError(f"manami entry has no supported source urls: {entry.title}")
    canonical = _select_canonical_source(parsed_sources)

    return BootstrapEntity(
        entity_id=canonical.entity_id,
        domain="anime",
        canonical_source=canonical.url,
        source_role=SourceRole.BACKBONE_SOURCE,
        record_source=record_source,
        title=entry.title,
        original_title=_pick_original_title(entry),
        media_type=entry.type,
        status=entry.status,
        release_year=entry.animeSeason.year,
        episodes=entry.episodes,
        synonyms=_dedupe_strings(entry.synonyms),
        sources=[source.url for source in parsed_sources],
        related=[
            BootstrapRelatedEdge(
                target=related_source.entity_id,
                relationship="related_anime",
                target_url=related_source.url,
                supporting_urls=[related_source.url],
            )
            for related_source in _parse_supported_source_refs(_dedupe_strings(entry.relatedAnime))
        ],
        tags=_dedupe_strings(entry.tags),
        field_sources={
            "title": [canonical.url],
            "episodes": [canonical.url],
            "status": [canonical.url],
            "release_year": [canonical.url],
        },
    )


def normalize_manami_release(
    release: ManamiRelease,
    *,
    limit: int | None = None,
    title_contains: str | None = None,
) -> list[BootstrapEntity]:
    record_source = f"manami-project/anime-offline-database release {release.lastUpdate}"
    entries = release.data

    if title_contains is not None:
        normalized_query = title_contains.casefold()
        entries = [
            entry for entry in entries if normalized_query in entry.title.casefold()
        ]

    if limit is not None:
        entries = entries[:limit]

    normalized_entities: list[BootstrapEntity] = []
    for entry in entries:
        try:
            normalized_entities.append(
                normalize_manami_entry(entry, record_source=record_source)
            )
        except ValueError:
            continue

    return normalized_entities


def write_normalized_manami_seed(
    *,
    release_path: Path,
    output_path: Path,
    limit: int | None = None,
    title_contains: str | None = None,
) -> Path:
    release = load_manami_release(release_path)
    entities = normalize_manami_release(
        release,
        limit=limit,
        title_contains=title_contains,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(entity.model_dump_json() for entity in entities) + ("\n" if entities else ""),
        encoding="utf-8",
    )
    return output_path


def _select_canonical_source(parsed_sources: list[ParsedSourceRef]) -> ParsedSourceRef:
    by_provider = {source.provider: source for source in parsed_sources}

    for provider in _PREFERRED_SOURCE_ORDER:
        preferred = by_provider.get(provider)
        if preferred is not None:
            return preferred

    return parsed_sources[0]


def _parse_supported_source_refs(urls: list[str]) -> list[ParsedSourceRef]:
    parsed_sources: list[ParsedSourceRef] = []

    for url in urls:
        try:
            parsed_sources.append(parse_manami_source_ref(url))
        except ValueError:
            continue

    return parsed_sources


def _pick_original_title(entry: ManamiAnimeEntry) -> str | None:
    for synonym in entry.synonyms:
        if any(ord(character) > 127 for character in synonym):
            return synonym

    return None


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)

    return deduped
