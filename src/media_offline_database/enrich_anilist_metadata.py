from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from media_offline_database.anilist_http import post_anilist_graphql
from media_offline_database.bootstrap import BootstrapEntity, load_bootstrap_entities
from media_offline_database.ingest_manami import parse_manami_source_ref

_ANILIST_METADATA_QUERY = """
query ($id: Int!) {
  Media(id: $id, type: ANIME) {
    id
    genres
    studios {
      edges {
        isMain
        node {
          id
          name
        }
      }
    }
    staff(sort: [RELEVANCE, ROLE, ID]) {
      edges {
        role
        node {
          id
          name {
            full
            native
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


class AniListStudioNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str


class AniListStudioEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    isMain: bool = False
    node: AniListStudioNode


class AniListStudiosPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    edges: list[AniListStudioEdge]


class AniListStaffName(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full: str | None = None
    native: str | None = None


class AniListStaffNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: AniListStaffName


class AniListStaffEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str | None = None
    node: AniListStaffNode


class AniListStaffPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    edges: list[AniListStaffEdge]


class AniListMediaPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    genres: list[str] = []
    studios: AniListStudiosPayload
    staff: AniListStaffPayload


class AniListGraphqlData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    Media: AniListMediaPayload | None = None


class AniListGraphqlResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: AniListGraphqlData | None = None


class AniListResolvedMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    genres: list[str]
    studios: list[str]
    creators: list[str]


type AniListMetadataFetcher = Callable[[int], AniListResolvedMetadata]


def fetch_anilist_metadata(
    anilist_id: int,
    *,
    timeout_seconds: float = 20.0,
) -> AniListResolvedMetadata:
    response = post_anilist_graphql(
        query=_ANILIST_METADATA_QUERY,
        variables={"id": anilist_id},
        timeout_seconds=timeout_seconds,
    )
    payload = AniListGraphqlResponse.model_validate(response.json())
    media = payload.data.Media if payload.data is not None else None
    if media is None:
        return AniListResolvedMetadata(genres=[], studios=[], creators=[])

    main_studios = _dedupe_strings(
        [edge.node.name for edge in media.studios.edges if edge.isMain and edge.node.name]
    )
    studios = main_studios or _dedupe_strings(
        [edge.node.name for edge in media.studios.edges if edge.node.name]
    )

    return AniListResolvedMetadata(
        genres=_dedupe_strings(media.genres),
        studios=studios,
        creators=_dedupe_strings(
            [
                _display_name(edge.node.name)
                for edge in media.staff.edges
                if _is_creator_role(edge.role)
            ]
        ),
    )


def enrich_bootstrap_entities_with_anilist_metadata(
    entities: list[BootstrapEntity],
    *,
    fetch_metadata: AniListMetadataFetcher = fetch_anilist_metadata,
) -> list[BootstrapEntity]:
    metadata_cache: dict[int, AniListResolvedMetadata] = {}
    enriched_entities: list[BootstrapEntity] = []

    for entity in entities:
        anilist_id = _extract_anilist_id(entity)
        if entity.domain != "anime" or anilist_id is None:
            enriched_entities.append(entity)
            continue

        metadata = metadata_cache.get(anilist_id)
        if metadata is None:
            metadata = fetch_metadata(anilist_id)
            metadata_cache[anilist_id] = metadata

        anilist_url = _extract_anilist_url(entity)
        field_sources = dict(entity.field_sources)
        if metadata.studios:
            field_sources["studios"] = _merge_field_sources(
                field_sources.get("studios", []),
                [anilist_url],
            )
        if metadata.genres:
            field_sources["genres"] = _merge_field_sources(
                field_sources.get("genres", []),
                [anilist_url],
            )
        if metadata.creators:
            field_sources["creators"] = _merge_field_sources(
                field_sources.get("creators", []),
                [anilist_url],
            )

        enriched_entities.append(
            entity.model_copy(
                update={
                    "genres": metadata.genres or entity.genres,
                    "studios": metadata.studios or entity.studios,
                    "creators": metadata.creators or entity.creators,
                    "field_sources": field_sources,
                }
            )
        )

    return enriched_entities


def write_anilist_metadata_enriched_seed(
    *,
    input_path: Path,
    output_path: Path,
    fetch_metadata: AniListMetadataFetcher = fetch_anilist_metadata,
) -> Path:
    entities = load_bootstrap_entities(input_path)
    enriched_entities = enrich_bootstrap_entities_with_anilist_metadata(
        entities,
        fetch_metadata=fetch_metadata,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(entity.model_dump_json() for entity in enriched_entities)
        + ("\n" if enriched_entities else ""),
        encoding="utf-8",
    )
    return output_path


def _extract_anilist_id(entity: BootstrapEntity) -> int | None:
    anilist_url = _extract_anilist_url(entity)
    if anilist_url is None:
        return None

    return int(parse_manami_source_ref(anilist_url).external_id)


def _extract_anilist_url(entity: BootstrapEntity) -> str | None:
    for url in entity.sources:
        try:
            parsed_source = parse_manami_source_ref(url)
        except ValueError:
            continue

        if parsed_source.provider != "anilist":
            continue

        return url

    return None


def _display_name(name: AniListStaffName) -> str | None:
    return name.full or name.native


def _is_creator_role(role: str | None) -> bool:
    if role is None:
        return False

    normalized = " ".join(role.lower().strip().split())
    return normalized in _CREATOR_ROLE_ALLOWLIST


def _merge_field_sources(existing: Sequence[str], incoming: Sequence[str | None]) -> list[str]:
    return _dedupe_strings([*existing, *incoming])


def _dedupe_strings(values: Sequence[str | None]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []

    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        deduped.append(value)

    return deduped
