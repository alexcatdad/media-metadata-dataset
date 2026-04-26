from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from media_offline_database.bootstrap import (
    BootstrapEntity,
    BootstrapRelatedEdge,
    load_bootstrap_entities,
)
from media_offline_database.ingest_manami import parse_manami_source_ref
from media_offline_database.relationships import deterministic_anilist_relationship_recipe

_ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
_ANILIST_RELATIONS_QUERY = """
query ($id: Int!) {
  Media(id: $id, type: ANIME) {
    id
    relations {
      edges {
        relationType(version: 2)
        node {
          id
          format
        }
      }
    }
  }
}
"""
class AniListRelatedNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    format: str | None = None


class AniListRelationEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    relationType: str | None = None
    node: AniListRelatedNode


class AniListRelationsPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    edges: list[AniListRelationEdge]


class AniListMediaPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    relations: AniListRelationsPayload


class AniListGraphqlData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    Media: AniListMediaPayload | None = None


class AniListGraphqlResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: AniListGraphqlData | None = None


class AniListResolvedRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_anilist_id: int
    relation_type: str
    target_format: str | None = None


type AniListRelationFetcher = Callable[[int], list[AniListResolvedRelation]]


def fetch_anilist_relations(anilist_id: int, *, timeout_seconds: float = 20.0) -> list[AniListResolvedRelation]:
    response = httpx.post(
        _ANILIST_GRAPHQL_URL,
        json={
            "query": _ANILIST_RELATIONS_QUERY,
            "variables": {"id": anilist_id},
        },
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = AniListGraphqlResponse.model_validate(response.json())
    media = payload.data.Media if payload.data is not None else None
    if media is None:
        return []

    return [
        AniListResolvedRelation(
            target_anilist_id=edge.node.id,
            relation_type=edge.relationType or "UNKNOWN",
            target_format=edge.node.format,
        )
        for edge in media.relations.edges
    ]


def enrich_bootstrap_entities_with_anilist_relations(
    entities: list[BootstrapEntity],
    *,
    fetch_relations: AniListRelationFetcher = fetch_anilist_relations,
) -> list[BootstrapEntity]:
    canonical_entities = canonicalize_bootstrap_relationship_targets(entities)
    anilist_source_url_by_entity_id = {
        entity.entity_id: anilist_url
        for entity in canonical_entities
        if (anilist_url := _extract_anilist_url(entity)) is not None
    }
    anilist_ids_by_entity_id = {
        entity.entity_id: anilist_id
        for entity in canonical_entities
        if (anilist_id := _extract_anilist_id(entity)) is not None
    }
    relation_cache: dict[int, dict[int, AniListResolvedRelation]] = {}
    enriched_entities: list[BootstrapEntity] = []

    for entity in canonical_entities:
        source_anilist_id = anilist_ids_by_entity_id.get(entity.entity_id)
        if source_anilist_id is None:
            enriched_entities.append(entity)
            continue

        resolved_relations = relation_cache.get(source_anilist_id)
        if resolved_relations is None:
            resolved_relations = {
                relation.target_anilist_id: relation
                for relation in fetch_relations(source_anilist_id)
            }
            relation_cache[source_anilist_id] = resolved_relations

        enriched_edges: list[BootstrapRelatedEdge] = []
        for edge in entity.related:
            target_anilist_id = anilist_ids_by_entity_id.get(edge.target)
            resolved_relation = (
                resolved_relations.get(target_anilist_id)
                if target_anilist_id is not None
                else None
            )
            relationship = edge.relationship

            if relationship == "related_anime" and resolved_relation is not None:
                relationship = classify_anilist_relationship(
                    relation_type=resolved_relation.relation_type,
                    target_format=resolved_relation.target_format,
                )
                supporting_urls = _dedupe_strings(
                    [
                        *_edge_supporting_urls(edge),
                        anilist_source_url_by_entity_id.get(entity.entity_id),
                        anilist_source_url_by_entity_id.get(edge.target),
                    ]
                )
            else:
                supporting_urls = _edge_supporting_urls(edge)

            enriched_edges.append(
                edge.model_copy(
                    update={
                        "relationship": relationship,
                        "supporting_urls": supporting_urls,
                    }
                )
            )

        enriched_entities.append(entity.model_copy(update={"related": enriched_edges}))

    return enriched_entities


def canonicalize_bootstrap_relationship_targets(
    entities: list[BootstrapEntity],
) -> list[BootstrapEntity]:
    alias_to_canonical_entity_id: dict[str, str] = {}
    entity_by_id = {entity.entity_id: entity for entity in entities}

    for entity in entities:
        alias_to_canonical_entity_id[entity.entity_id] = entity.entity_id
        for url in entity.sources:
            try:
                alias = parse_manami_source_ref(url).entity_id
            except ValueError:
                continue
            alias_to_canonical_entity_id[alias] = entity.entity_id

    canonical_entities: list[BootstrapEntity] = []
    for entity in entities:
        deduped_edges: dict[tuple[str, str], BootstrapRelatedEdge] = {}
        for edge in entity.related:
            canonical_target = alias_to_canonical_entity_id.get(edge.target, edge.target)
            canonical_target_entity = entity_by_id.get(canonical_target)
            target_url = (
                canonical_target_entity.canonical_source
                if canonical_target_entity is not None
                else edge.target_url
            )
            dedupe_key = (canonical_target, edge.relationship)
            existing_edge = deduped_edges.get(dedupe_key)
            supporting_urls = _dedupe_strings(
                [
                    *(existing_edge.supporting_urls if existing_edge is not None else []),
                    *_edge_supporting_urls(edge),
                    target_url,
                ]
            )
            deduped_edges[dedupe_key] = BootstrapRelatedEdge(
                target=canonical_target,
                relationship=edge.relationship,
                target_url=target_url,
                supporting_urls=supporting_urls,
            )

        canonical_entities.append(
            entity.model_copy(update={"related": list(deduped_edges.values())})
        )

    return canonical_entities


def write_anilist_relation_enriched_seed(
    *,
    input_path: Path,
    output_path: Path,
    fetch_relations: AniListRelationFetcher = fetch_anilist_relations,
) -> Path:
    entities = load_bootstrap_entities(input_path)
    enriched_entities = enrich_bootstrap_entities_with_anilist_relations(
        entities,
        fetch_relations=fetch_relations,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(entity.model_dump_json() for entity in enriched_entities)
        + ("\n" if enriched_entities else ""),
        encoding="utf-8",
    )
    return output_path


def classify_anilist_relationship(*, relation_type: str, target_format: str | None) -> str:
    recipe_result = deterministic_anilist_relationship_recipe(
        relation_type=relation_type,
        target_format=target_format,
    )
    return recipe_result.relationship or "related_anime"


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


def _edge_supporting_urls(edge: BootstrapRelatedEdge) -> list[str]:
    if edge.supporting_urls:
        return _dedupe_strings(edge.supporting_urls)

    return [edge.target_url]


def _dedupe_strings(values: Sequence[str | None]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []

    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        deduped.append(value)

    return deduped
