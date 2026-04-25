from __future__ import annotations

from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from media_offline_database.anilist_concept_search import ConceptSearchFilters, parse_concept_query
from media_offline_database.bootstrap import BootstrapEntity


class CorpusConceptMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    title: str
    domain: str
    media_type: str
    release_year: int
    genres: list[str] = Field(default_factory=list)
    matched_genres: list[str] = Field(default_factory=list)
    matched_tags: list[str] = Field(default_factory=list)
    score: float
    rationale: str


class CorpusConceptPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    filters: ConceptSearchFilters
    matches: list[CorpusConceptMatch] = Field(
        default_factory=lambda: cast(list[CorpusConceptMatch], [])
    )


def search_corpus_by_concept(
    entities: list[BootstrapEntity],
    *,
    query: str,
    limit: int = 10,
) -> CorpusConceptPreview:
    filters = parse_concept_query(query)
    matches: list[CorpusConceptMatch] = []

    for entity in entities:
        if entity.domain != "anime":
            continue

        entity_genres = {genre.casefold(): genre for genre in entity.genres}
        entity_tags = {tag.casefold(): tag for tag in entity.tags}
        matched_genres = [
            genre for genre in filters.genres if genre.casefold() in entity_genres
        ]
        matched_tags = [
            tag for tag in filters.tags if tag.casefold() in entity_tags
        ]
        if not matched_genres and not matched_tags:
            continue
        if filters.tags and not matched_tags:
            continue

        score = len(matched_genres) * 3.0 + len(matched_tags) * 2.0
        score += min(len(entity.tags), 20) * 0.01
        if matched_genres and matched_tags:
            score += 0.5

        rationale_parts: list[str] = []
        if matched_genres:
            rationale_parts.append(f"genre match: {', '.join(matched_genres)}")
        if matched_tags:
            rationale_parts.append(f"tag match: {', '.join(matched_tags)}")

        matches.append(
            CorpusConceptMatch(
                entity_id=entity.entity_id,
                title=entity.title,
                domain=entity.domain,
                media_type=entity.media_type,
                release_year=entity.release_year,
                genres=entity.genres,
                matched_genres=matched_genres,
                matched_tags=matched_tags,
                score=round(score, 2),
                rationale="; ".join(rationale_parts),
            )
        )

    matches.sort(
        key=lambda match: (
            -match.score,
            -len(match.matched_tags),
            match.release_year,
            match.title.casefold(),
            match.entity_id,
        )
    )
    return CorpusConceptPreview(
        query=query,
        filters=filters,
        matches=matches[:limit],
    )
