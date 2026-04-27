from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from media_offline_database.bootstrap import BootstrapEntity, BootstrapRelatedEdge
from media_offline_database.ingest_normalization import AdapterCandidateRejection
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
    data: list[dict[str, Any]]


class ParsedSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    external_id: str
    url: str

    @property
    def entity_id(self) -> str:
        return f"anime:manami:{self.provider}:{self.external_id}"


def _empty_adapter_candidate_rejections() -> list[AdapterCandidateRejection]:
    return []


class NormalizedManamiBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    total_candidates: int
    selected_candidate_count: int
    normalized_record_count: int
    skipped_candidate_count: int
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    rejections: list[AdapterCandidateRejection] = Field(
        default_factory=_empty_adapter_candidate_rejections
    )
    start_offset: int
    end_offset: int
    next_offset: int
    entities: list[BootstrapEntity]
    last_completed_item_key: str | None = None


def load_manami_release(path: Path) -> ManamiRelease:
    return ManamiRelease.model_validate(json.loads(path.read_text(encoding="utf-8")))


def manami_snapshot_id(release: ManamiRelease) -> str:
    return release.lastUpdate


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
    return normalize_manami_release_batch(
        release,
        start_offset=0,
        batch_size=None,
        limit=limit,
        title_contains=title_contains,
    ).entities


def normalize_manami_release_batch(
    release: ManamiRelease,
    *,
    start_offset: int = 0,
    batch_size: int | None = None,
    limit: int | None = None,
    title_contains: str | None = None,
) -> NormalizedManamiBatch:
    record_source = f"manami-project/anime-offline-database release {release.lastUpdate}"
    entries = _filtered_entries(
        release,
        limit=limit,
        title_contains=title_contains,
    )
    total_candidates = len(entries)

    if start_offset < 0:
        raise ValueError("start_offset must be non-negative")
    if start_offset > total_candidates:
        raise ValueError("start_offset is beyond available candidates")

    if batch_size is None:
        batch_entries = entries[start_offset:]
    else:
        batch_entries = entries[start_offset : start_offset + batch_size]

    end_offset = start_offset + len(batch_entries)
    normalized_entities: list[BootstrapEntity] = []
    rejections: list[AdapterCandidateRejection] = []
    for candidate_index, candidate in enumerate(batch_entries, start=start_offset):
        entry = _validate_manami_candidate(candidate, candidate_index, rejections)
        if entry is None:
            continue
        if entry.animeSeason.year is None:
            rejections.append(
                AdapterCandidateRejection(
                    candidate_index=candidate_index,
                    reason="missing_required_field",
                    detail="animeSeason.year",
                )
            )
            continue
        if not _parse_supported_source_refs(entry.sources):
            rejections.append(
                AdapterCandidateRejection(
                    candidate_index=candidate_index,
                    reason="unsupported_source_url",
                    detail="sources",
                )
            )
            continue

        normalized_entities.append(
            normalize_manami_entry(entry, record_source=record_source)
        )

    last_completed_item_key = None
    if normalized_entities:
        last_completed_item_key = normalized_entities[-1].entity_id

    rejection_reasons = Counter(rejection.reason for rejection in rejections)

    return NormalizedManamiBatch(
        snapshot_id=manami_snapshot_id(release),
        total_candidates=total_candidates,
        selected_candidate_count=len(batch_entries),
        normalized_record_count=len(normalized_entities),
        skipped_candidate_count=len(rejections),
        rejection_reasons=dict(sorted(rejection_reasons.items())),
        rejections=rejections,
        start_offset=start_offset,
        end_offset=end_offset,
        next_offset=end_offset,
        entities=normalized_entities,
        last_completed_item_key=last_completed_item_key,
    )


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


def _filtered_entries(
    release: ManamiRelease,
    *,
    limit: int | None,
    title_contains: str | None,
) -> list[dict[str, Any]]:
    entries = release.data

    if title_contains is not None:
        normalized_query = title_contains.casefold()
        entries = [
            entry
            for entry in entries
            if normalized_query in str(entry.get("title", "")).casefold()
        ]

    if limit is not None:
        entries = entries[:limit]

    return entries


def _validate_manami_candidate(
    candidate: dict[str, Any],
    candidate_index: int,
    rejections: list[AdapterCandidateRejection],
) -> ManamiAnimeEntry | None:
    try:
        return ManamiAnimeEntry.model_validate(candidate)
    except ValidationError as error:
        missing_fields = [
            ".".join(str(part) for part in validation_error["loc"])
            for validation_error in error.errors()
            if validation_error["type"] == "missing"
        ]
        detail = ",".join(sorted(missing_fields)) if missing_fields else "candidate_shape"
        rejections.append(
            AdapterCandidateRejection(
                candidate_index=candidate_index,
                reason="missing_required_field",
                detail=detail,
            )
        )
        return None


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
