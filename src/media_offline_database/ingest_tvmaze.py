from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from media_offline_database.bootstrap import BootstrapEntity
from media_offline_database.provider_http import TVMAZE_HTTP_CLIENT
from media_offline_database.sources import SourceRole

TVMAZE_SOURCE_ID = "tvmaze"
TVMAZE_ADAPTER_VERSION = "tvmaze-bootstrap-v1"
TVMAZE_USER_AGENT = (
    "media-metadata-dataset local compiler "
    "(https://github.com/alexcatdad/media-metadata-dataset)"
)


class TVmazeEpisode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None


class TVmazeSeason(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None


def _empty_episodes() -> list[TVmazeEpisode]:
    return []


def _empty_seasons() -> list[TVmazeSeason]:
    return []


class TVmazeNetwork(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None


class TVmazeExternals(BaseModel):
    model_config = ConfigDict(extra="ignore")

    imdb: str | None = None
    thetvdb: int | None = None
    tvrage: int | None = None


class TVmazeEmbedded(BaseModel):
    model_config = ConfigDict(extra="ignore")

    episodes: list[TVmazeEpisode] = Field(default_factory=_empty_episodes)
    seasons: list[TVmazeSeason] = Field(default_factory=_empty_seasons)


class TVmazeShow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    url: str
    name: str
    type: str | None = None
    language: str | None = None
    genres: list[str] = Field(default_factory=list)
    status: str | None = None
    runtime: int | None = None
    averageRuntime: int | None = None
    premiered: str | None = None
    ended: str | None = None
    officialSite: str | None = None
    network: TVmazeNetwork | None = None
    webChannel: TVmazeNetwork | None = None
    externals: TVmazeExternals = Field(default_factory=TVmazeExternals)
    embedded: TVmazeEmbedded = Field(default_factory=TVmazeEmbedded, alias="_embedded")

    @field_validator("genres")
    @classmethod
    def sort_unique_genres(cls, genres: list[str]) -> list[str]:
        return sorted(dict.fromkeys(genre for genre in genres if genre))


class TVmazeBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_snapshot_id: str
    fetched_at: datetime
    entities: list[BootstrapEntity]
    total_candidates: int


TVmazeFetchShow = Callable[[int], TVmazeShow]


def fetch_tvmaze_show(show_id: int) -> TVmazeShow:
    response = TVMAZE_HTTP_CLIENT.get(
        f"https://api.tvmaze.com/shows/{show_id}",
        params=[("embed[]", "episodes"), ("embed[]", "seasons")],
        headers={"User-Agent": TVMAZE_USER_AGENT},
        timeout=30,
    )
    return TVmazeShow.model_validate(response.json())


def normalize_tvmaze_show(show: TVmazeShow) -> BootstrapEntity:
    release_year = _year_from_date(show.premiered)
    if release_year is None:
        release_year = 0

    network_or_platform = _network_or_platform(show)
    tags = [
        *_normalized_tags(show.genres),
        *_optional_tag("language", show.language),
        *_optional_tag("network", network_or_platform),
        *_optional_tag("tv_type", show.type),
    ]
    sources = [show.url]
    if show.officialSite:
        sources.append(show.officialSite)
    if show.externals.imdb:
        sources.append(f"https://www.imdb.com/title/{show.externals.imdb}/")
    if show.externals.thetvdb is not None:
        sources.append(f"https://thetvdb.com/series/{show.externals.thetvdb}")

    return BootstrapEntity(
        entity_id=f"tv:tvmaze:{show.id}",
        domain="tv",
        canonical_source=show.url,
        source_role=SourceRole.BACKBONE_SOURCE,
        record_source=TVMAZE_SOURCE_ID,
        title=show.name,
        media_type=show.type or "TV",
        status=show.status or "UNKNOWN",
        release_year=release_year,
        episodes=len(show.embedded.episodes) or None,
        sources=sorted(dict.fromkeys(sources)),
        genres=show.genres,
        studios=[],
        creators=[],
        tags=sorted(dict.fromkeys(tags)),
        field_sources={
            "title": [show.url],
            "status": [show.url],
            "release_year": [show.url],
            "genres": [show.url],
            "episodes": [show.url],
            "sources": [show.url],
        },
    )


def normalize_tvmaze_shows(
    *,
    show_ids: Sequence[int],
    fetch_show: TVmazeFetchShow = fetch_tvmaze_show,
) -> TVmazeBatch:
    fetched_at = datetime.now(tz=UTC)
    unique_ids = list(dict.fromkeys(show_ids))
    entities = [normalize_tvmaze_show(fetch_show(show_id)) for show_id in unique_ids]
    return TVmazeBatch(
        source_snapshot_id=tvmaze_snapshot_id(fetched_at),
        fetched_at=fetched_at,
        entities=entities,
        total_candidates=len(unique_ids),
    )


def write_normalized_tvmaze_seed(
    *,
    show_ids: Sequence[int],
    output_path: Path,
    fetch_show: TVmazeFetchShow = fetch_tvmaze_show,
) -> Path:
    batch = normalize_tvmaze_shows(show_ids=show_ids, fetch_show=fetch_show)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(entity.model_dump_json() for entity in batch.entities)
        + ("\n" if batch.entities else ""),
        encoding="utf-8",
    )
    return output_path


def tvmaze_snapshot_id(fetched_at: datetime) -> str:
    return f"tvmaze:{fetched_at.date().isoformat()}"


def _year_from_date(value: str | None) -> int | None:
    if value is None or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def _network_or_platform(show: TVmazeShow) -> str | None:
    if show.webChannel is not None and show.webChannel.name:
        return show.webChannel.name
    if show.network is not None and show.network.name:
        return show.network.name
    return None


def _normalized_tags(values: Sequence[str]) -> list[str]:
    return [value.strip().casefold().replace(" ", "_") for value in values if value.strip()]


def _optional_tag(prefix: str, value: str | None) -> list[str]:
    if value is None or not value.strip():
        return []
    return [f"{prefix}:{value.strip().casefold().replace(' ', '_')}"]
