from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from media_offline_database.bootstrap import (
    BootstrapEntity,
    BootstrapRelatedEdge,
    load_bootstrap_entities,
)
from media_offline_database.relationships import (
    relationship_confidence,
    supporting_provider_count,
    supporting_source_count,
)
from media_offline_database.sources import SourceRole

_WHITESPACE_RE = re.compile(r"\s+")


def _empty_entity_matches() -> list[EntitySearchMatch]:
    return []


def _empty_related_sections() -> dict[str, list[RelatedEntityCard]]:
    return {}


def _empty_tag_neighbors() -> list[TagNeighbor]:
    return []


class EntitySearchMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    title: str
    domain: str
    media_type: str
    release_year: int
    canonical_source: str
    score: int
    matched_fields: list[str] = Field(default_factory=list)


class PreviewEntityCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    title: str
    domain: str
    media_type: str
    release_year: int
    status: str
    canonical_source: str
    source_role: str
    episodes: int | None = None
    original_title: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    studios: list[str] = Field(default_factory=list)
    creators: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RelatedEntityCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    title: str
    domain: str
    media_type: str
    release_year: int
    relationship: str
    direction: Literal["outgoing", "incoming", "bidirectional"]
    confidence: float
    supporting_source_count: int
    supporting_provider_count: int
    supporting_urls: list[str] = Field(default_factory=list)


class FamilyGraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_entity_id: str
    target_entity_id: str
    relationship: str
    confidence: float


class FamilyGraphPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_entity_id: str
    node_count: int
    edge_count: int
    nodes: list[PreviewEntityCard]
    edges: list[FamilyGraphEdge]


class TagNeighbor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    title: str
    domain: str
    media_type: str
    release_year: int
    shared_tags: list[str]
    overlap_count: int
    score: float


class QueryPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = None
    selected_entity_id: str
    matches: list[EntitySearchMatch] = Field(default_factory=_empty_entity_matches)
    canonical_entity: PreviewEntityCard
    family_graph: FamilyGraphPreview
    related_sections: dict[str, list[RelatedEntityCard]] = Field(
        default_factory=_empty_related_sections
    )
    tag_neighbors: list[TagNeighbor] = Field(default_factory=_empty_tag_neighbors)


def load_query_entities(
    *,
    input_path: Path | None = None,
    manifest_path: Path | None = None,
) -> list[BootstrapEntity]:
    if (input_path is None) == (manifest_path is None):
        raise ValueError("exactly one of input_path or manifest_path must be provided")

    if input_path is not None:
        return load_bootstrap_entities(input_path)

    assert manifest_path is not None
    return _load_entities_from_manifest(manifest_path)


def search_entities(
    entities: list[BootstrapEntity],
    *,
    query: str,
    limit: int = 5,
) -> list[EntitySearchMatch]:
    query_key = _normalize_text(query)
    matches: list[EntitySearchMatch] = []

    for entity in entities:
        score, matched_fields = _score_entity_match(entity, query_key)
        if score <= 0:
            continue

        matches.append(
            EntitySearchMatch(
                entity_id=entity.entity_id,
                title=entity.title,
                domain=entity.domain,
                media_type=entity.media_type,
                release_year=entity.release_year,
                canonical_source=entity.canonical_source,
                score=score,
                matched_fields=matched_fields,
            )
        )

    matches.sort(
        key=lambda match: (
            -match.score,
            match.release_year,
            match.title.casefold(),
            match.entity_id,
        )
    )
    return matches[:limit]


def build_query_preview(
    entities: list[BootstrapEntity],
    *,
    query: str | None = None,
    entity_id: str | None = None,
    match_limit: int = 5,
    tag_limit: int = 5,
) -> QueryPreview:
    if query is None and entity_id is None:
        raise ValueError("query or entity_id is required")

    matches: list[EntitySearchMatch] = (
        search_entities(entities, query=query, limit=match_limit) if query is not None else []
    )
    entity_map = {entity.entity_id: entity for entity in entities}

    if entity_id is not None:
        selected_entity = entity_map.get(entity_id)
        if selected_entity is None:
            raise ValueError(f"entity_id not found: {entity_id}")
    else:
        if not matches:
            raise ValueError(f"no matches found for query: {query}")
        selected_entity = entity_map[matches[0].entity_id]

    family_ids = _connected_family_entity_ids(entities, root_entity_id=selected_entity.entity_id)
    family_entities: list[BootstrapEntity] = [
        entity_map[member_id] for member_id in sorted(family_ids) if member_id in entity_map
    ]
    family_edges: list[FamilyGraphEdge] = _family_edges(family_entities, family_ids)
    related_sections = _related_sections(entities, selected_entity)
    _extend_related_sections_with_metadata(
        related_sections,
        entities,
        selected_entity=selected_entity,
        excluded_entity_ids=family_ids,
    )
    tag_neighbors: list[TagNeighbor]
    tag_neighbors = _tag_neighbors(
        entities,
        selected_entity=selected_entity,
        excluded_entity_ids=family_ids,
        limit=tag_limit,
    )

    return QueryPreview(
        query=query,
        selected_entity_id=selected_entity.entity_id,
        matches=matches,
        canonical_entity=_entity_card(selected_entity),
        family_graph=FamilyGraphPreview(
            root_entity_id=selected_entity.entity_id,
            node_count=len(family_entities),
            edge_count=len(family_edges),
            nodes=[_entity_card(entity) for entity in sorted(family_entities, key=_entity_sort_key)],
            edges=family_edges,
        ),
        related_sections=related_sections,
        tag_neighbors=tag_neighbors,
    )


def _load_entities_from_manifest(manifest_path: Path) -> list[BootstrapEntity]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = {file["kind"]: manifest_path.parent / file["path"] for file in manifest["files"]}
    entity_frame = pl.read_parquet(files["entities"])
    relationship_frame = pl.read_parquet(files["relationships"])

    entities: dict[str, BootstrapEntity] = {}
    for row in entity_frame.iter_rows(named=True):
        entities[row["entity_id"]] = BootstrapEntity(
            entity_id=row["entity_id"],
            domain=row["domain"],
            canonical_source=row["canonical_source"],
            source_role=SourceRole(row["source_role"]),
            record_source=row["record_source"],
            title=row["title"],
            original_title=row["original_title"],
            media_type=row["media_type"],
            status=row["status"],
            release_year=row["release_year"],
            episodes=row["episodes"],
            synonyms=list(row["synonyms"] or []),
            sources=list(row["sources"] or []),
            studios=list(row.get("studios") or []),
            creators=list(row.get("creators") or []),
            related=[],
            tags=list(row["tags"] or []),
            field_sources=json.loads(row["field_sources_json"]),
        )

    for row in relationship_frame.iter_rows(named=True):
        source_entity = entities.get(row["source_entity_id"])
        if source_entity is None:
            continue

        source_entity.related.append(
            BootstrapRelatedEdge(
                target=row["target_entity_id"],
                relationship=row["relationship"],
                target_url=row["target_url"],
                supporting_urls=list(row["supporting_urls"] or []),
            )
        )

    return list(entities.values())


def _score_entity_match(entity: BootstrapEntity, query_key: str) -> tuple[int, list[str]]:
    candidates = [
        ("title", entity.title),
        ("original_title", entity.original_title),
        *[("synonym", synonym) for synonym in entity.synonyms],
    ]

    best_score = 0
    matched_fields: list[str] = []

    for field_name, raw_value in candidates:
        if not raw_value:
            continue

        candidate_key = _normalize_text(raw_value)
        score = 0
        if candidate_key == query_key:
            score = 100 if field_name == "title" else 96
        elif candidate_key.startswith(query_key):
            score = 92 if field_name == "title" else 84
        elif query_key in candidate_key:
            score = 88 if field_name == "title" else 80
        else:
            overlap = _token_overlap_score(query_key, candidate_key)
            if overlap > 0:
                score = 60 + overlap

        if score > best_score:
            best_score = score
            matched_fields = [field_name]
        elif score == best_score and score > 0 and field_name not in matched_fields:
            matched_fields.append(field_name)

    return best_score, matched_fields


def _connected_family_entity_ids(
    entities: list[BootstrapEntity],
    *,
    root_entity_id: str,
) -> set[str]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        for edge in entity.related:
            adjacency[entity.entity_id].add(edge.target)
            adjacency[edge.target].add(entity.entity_id)

    visited: set[str] = set()
    queue: deque[str] = deque([root_entity_id])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(sorted(adjacency.get(current, set()) - visited))
    return visited


def _family_edges(
    entities: list[BootstrapEntity],
    family_ids: set[str],
) -> list[FamilyGraphEdge]:
    edges: list[FamilyGraphEdge] = []
    for entity in entities:
        for edge in entity.related:
            if edge.target not in family_ids:
                continue
            edges.append(
                FamilyGraphEdge(
                    source_entity_id=entity.entity_id,
                    target_entity_id=edge.target,
                    relationship=edge.relationship,
                    confidence=relationship_confidence(edge),
                )
            )
    edges.sort(
        key=lambda edge: (
            edge.source_entity_id,
            edge.relationship,
            edge.target_entity_id,
        )
    )
    return edges


def _related_sections(
    entities: list[BootstrapEntity],
    selected_entity: BootstrapEntity,
) -> dict[str, list[RelatedEntityCard]]:
    entity_map = {entity.entity_id: entity for entity in entities}
    sections: dict[str, dict[str, RelatedEntityCard]] = defaultdict(dict)

    incoming_edges: list[tuple[BootstrapEntity, BootstrapRelatedEdge]] = []
    for entity in entities:
        if entity.entity_id == selected_entity.entity_id:
            continue
        for edge in entity.related:
            if edge.target == selected_entity.entity_id:
                incoming_edges.append((entity, edge))

    incoming_pairs = {
        (source_entity.entity_id, edge.relationship)
        for source_entity, edge in incoming_edges
    }

    for edge in selected_entity.related:
        target_entity = entity_map.get(edge.target)
        if target_entity is None:
            continue
        direction: Literal["outgoing", "incoming", "bidirectional"] = (
            "bidirectional"
            if (target_entity.entity_id, edge.relationship) in incoming_pairs
            else "outgoing"
        )
        sections[edge.relationship][target_entity.entity_id] = _related_entity_card(
            entity=target_entity,
            relationship=edge.relationship,
            direction=direction,
            edge=edge,
        )

    for source_entity, edge in incoming_edges:
        existing = sections[edge.relationship].get(source_entity.entity_id)
        if existing is not None:
            if existing.direction == "outgoing":
                existing.direction = "bidirectional"
            continue
        sections[edge.relationship][source_entity.entity_id] = _related_entity_card(
            entity=source_entity,
            relationship=edge.relationship,
            direction="incoming",
            edge=edge,
        )

    ordered_sections: dict[str, list[RelatedEntityCard]] = {}
    for relationship in sorted(sections):
        ordered_sections[relationship] = sorted(
            sections[relationship].values(),
            key=lambda item: (-item.confidence, item.release_year, item.title.casefold(), item.entity_id),
        )
    return ordered_sections


def _extend_related_sections_with_metadata(
    sections: dict[str, list[RelatedEntityCard]],
    entities: list[BootstrapEntity],
    *,
    selected_entity: BootstrapEntity,
    excluded_entity_ids: set[str],
) -> None:
    shared_sections = {
        "same_studio": _shared_metadata_cards(
            entities,
            selected_entity=selected_entity,
            excluded_entity_ids=excluded_entity_ids,
            values=selected_entity.studios,
            relationship="same_studio",
        ),
        "same_creator": _shared_metadata_cards(
            entities,
            selected_entity=selected_entity,
            excluded_entity_ids=excluded_entity_ids,
            values=selected_entity.creators,
            relationship="same_creator",
        ),
    }

    for section_name, cards in shared_sections.items():
        if cards:
            sections[section_name] = cards


def _shared_metadata_cards(
    entities: list[BootstrapEntity],
    *,
    selected_entity: BootstrapEntity,
    excluded_entity_ids: set[str],
    values: list[str],
    relationship: str,
) -> list[RelatedEntityCard]:
    normalized_values = {_normalize_text(value) for value in values if value.strip()}
    if not normalized_values:
        return []

    cards: list[tuple[int, RelatedEntityCard]] = []
    for entity in entities:
        if entity.entity_id in excluded_entity_ids or entity.entity_id == selected_entity.entity_id:
            continue

        field_values = entity.studios if relationship == "same_studio" else entity.creators
        candidate_values = {_normalize_text(value) for value in field_values if value.strip()}
        overlap = normalized_values & candidate_values
        if not overlap:
            continue

        synthetic_edge = BootstrapRelatedEdge(
            target=entity.entity_id,
            relationship=relationship,
            target_url=entity.canonical_source,
            supporting_urls=[entity.canonical_source],
        )
        cards.append(
            (
                len(overlap),
                _related_entity_card(
                    entity=entity,
                    relationship=relationship,
                    direction="outgoing",
                    edge=synthetic_edge,
                ),
            )
        )

    cards.sort(
        key=lambda item: (
            -item[0],
            -item[1].confidence,
            item[1].release_year,
            item[1].title.casefold(),
            item[1].entity_id,
        )
    )
    return [card for _, card in cards]


def _tag_neighbors(
    entities: list[BootstrapEntity],
    *,
    selected_entity: BootstrapEntity,
    excluded_entity_ids: set[str],
    limit: int,
) -> list[TagNeighbor]:
    selected_tags = {tag.casefold(): tag for tag in selected_entity.tags}
    neighbors: list[TagNeighbor] = []

    for entity in entities:
        if entity.entity_id in excluded_entity_ids:
            continue
        entity_tags = {tag.casefold(): tag for tag in entity.tags}
        shared_tag_keys = sorted(set(selected_tags) & set(entity_tags))
        if not shared_tag_keys:
            continue

        shared_tags = [selected_tags[key] for key in shared_tag_keys]
        union_size = len(set(selected_tags) | set(entity_tags))
        score = round(len(shared_tags) + (len(shared_tags) / union_size), 2)
        neighbors.append(
            TagNeighbor(
                entity_id=entity.entity_id,
                title=entity.title,
                domain=entity.domain,
                media_type=entity.media_type,
                release_year=entity.release_year,
                shared_tags=shared_tags,
                overlap_count=len(shared_tags),
                score=score,
            )
        )

    neighbors.sort(
        key=lambda neighbor: (
            -neighbor.score,
            -neighbor.overlap_count,
            neighbor.release_year,
            neighbor.title.casefold(),
        )
    )
    return neighbors[:limit]


def _entity_card(entity: BootstrapEntity) -> PreviewEntityCard:
    return PreviewEntityCard(
        entity_id=entity.entity_id,
        title=entity.title,
        domain=entity.domain,
        media_type=entity.media_type,
        release_year=entity.release_year,
        status=entity.status,
        canonical_source=entity.canonical_source,
        source_role=entity.source_role.value,
        episodes=entity.episodes,
        original_title=entity.original_title,
        synonyms=entity.synonyms,
        studios=entity.studios,
        creators=entity.creators,
        tags=entity.tags,
    )


def _related_entity_card(
    *,
    entity: BootstrapEntity,
    relationship: str,
    direction: Literal["outgoing", "incoming", "bidirectional"],
    edge: BootstrapRelatedEdge,
) -> RelatedEntityCard:
    return RelatedEntityCard(
        entity_id=entity.entity_id,
        title=entity.title,
        domain=entity.domain,
        media_type=entity.media_type,
        release_year=entity.release_year,
        relationship=relationship,
        direction=direction,
        confidence=relationship_confidence(edge),
        supporting_source_count=supporting_source_count(edge),
        supporting_provider_count=supporting_provider_count(edge),
        supporting_urls=edge.supporting_urls or [edge.target_url],
    )


def _entity_sort_key(entity: BootstrapEntity) -> tuple[str, int, str, str]:
    return (entity.domain, entity.release_year, entity.title.casefold(), entity.entity_id)


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.casefold()).strip()


def _token_overlap_score(query_key: str, candidate_key: str) -> int:
    query_tokens = set(query_key.split())
    candidate_tokens = set(candidate_key.split())
    return min(len(query_tokens & candidate_tokens) * 4, 16)
