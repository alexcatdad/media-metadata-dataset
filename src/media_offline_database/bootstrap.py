from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from media_offline_database.artifacts import artifact_manifest_metadata
from media_offline_database.publishability import (
    ArtifactInput,
    PublishableUse,
    SourceFieldReference,
    publishability_manifest_payload,
    validate_artifact_inputs,
)
from media_offline_database.relationships import (
    RELATIONSHIP_RECIPE_VERSION,
    inverse_relationship,
    relationship_confidence_score,
    relationship_confidence_score_profile_json,
    relationship_confidence_score_tier,
    relationship_direction,
    relationship_evidence_id,
    relationship_family,
    relationship_id,
    relationship_quality_flags,
    supporting_provider_count,
    supporting_source_count,
)
from media_offline_database.sources import SourceRole


def _empty_related_edges() -> list[BootstrapRelatedEdge]:
    return []


class BootstrapRelatedEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    relationship: str
    target_url: str
    supporting_urls: list[str] = Field(default_factory=list)


class BootstrapEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    domain: str
    canonical_source: str
    source_role: SourceRole
    record_source: str
    title: str
    original_title: str | None = None
    media_type: str
    status: str
    release_year: int
    episodes: int | None = None
    synonyms: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    studios: list[str] = Field(default_factory=list)
    creators: list[str] = Field(default_factory=list)
    related: list[BootstrapRelatedEdge] = Field(default_factory=_empty_related_edges)
    tags: list[str] = Field(default_factory=list)
    field_sources: dict[str, list[str]] = Field(default_factory=dict)


def _field_sources_json(field_sources: dict[str, list[str]]) -> str:
    return json.dumps(
        field_sources,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def load_bootstrap_entities(path: Path) -> list[BootstrapEntity]:
    entities: list[BootstrapEntity] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entities.append(BootstrapEntity.model_validate_json(line))
    return entities


def bootstrap_entities_frame(entities: list[BootstrapEntity]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "entity_id": entity.entity_id,
                "domain": entity.domain,
                "canonical_source": entity.canonical_source,
                "source_role": entity.source_role.value,
                "record_source": entity.record_source,
                "title": entity.title,
                "original_title": entity.original_title,
                "media_type": entity.media_type,
                "status": entity.status,
                "release_year": entity.release_year,
                "episodes": entity.episodes,
                "synonyms": entity.synonyms,
                "sources": entity.sources,
                "genres": entity.genres,
                "studios": entity.studios,
                "creators": entity.creators,
                "tags": entity.tags,
                "field_sources_json": _field_sources_json(entity.field_sources),
            }
            for entity in entities
        ]
    )


def bootstrap_relationships_frame(entities: list[BootstrapEntity]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "relationship_id": relationship_id(
                    source_entity_id=entity.entity_id,
                    target_entity_id=edge.target,
                    relationship=edge.relationship,
                ),
                "source_entity_id": entity.entity_id,
                "target_entity_id": edge.target,
                "relationship_type": edge.relationship,
                "relationship_family": relationship_family(edge.relationship),
                "direction": relationship_direction(edge.relationship),
                "inverse_relationship_type": inverse_relationship(edge.relationship),
                "confidence_tier": relationship_confidence_score_tier(edge),
                "evidence_count": supporting_source_count(edge),
                "conflict_status": "none",
                "quality_flags": relationship_quality_flags(edge),
                "evidence_id": relationship_evidence_id(
                    source_entity_id=entity.entity_id,
                    target_entity_id=edge.target,
                    relationship=edge.relationship,
                    supporting_urls=edge.supporting_urls or [edge.target_url],
                ),
                "provenance_id": None,
                "recipe_version": RELATIONSHIP_RECIPE_VERSION,
                "target_url": edge.target_url,
                "supporting_urls": edge.supporting_urls or [edge.target_url],
                "supporting_source_count": supporting_source_count(edge),
                "supporting_provider_count": supporting_provider_count(edge),
                "relationship_confidence_score": relationship_confidence_score(edge),
                "confidence_profile_json": relationship_confidence_score_profile_json(edge),
            }
            for entity in entities
            for edge in entity.related
        ],
        schema={
            "relationship_id": pl.String,
            "source_entity_id": pl.String,
            "target_entity_id": pl.String,
            "relationship_type": pl.String,
            "relationship_family": pl.String,
            "direction": pl.String,
            "inverse_relationship_type": pl.String,
            "confidence_tier": pl.String,
            "evidence_count": pl.Int64,
            "conflict_status": pl.String,
            "quality_flags": pl.List(pl.String),
            "evidence_id": pl.String,
            "provenance_id": pl.String,
            "recipe_version": pl.String,
            "target_url": pl.String,
            "supporting_urls": pl.List(pl.String),
            "supporting_source_count": pl.Int64,
            "supporting_provider_count": pl.Int64,
            "relationship_confidence_score": pl.Float64,
            "confidence_profile_json": pl.String,
        },
    )


def write_bootstrap_corpus_artifact(
    *,
    input_path: Path,
    output_dir: Path,
    source_id: str = "bootstrap_seed",
    policy_inputs: Sequence[ArtifactInput] | None = None,
) -> Path:
    entities = load_bootstrap_entities(input_path)
    entity_frame = bootstrap_entities_frame(entities)
    relationship_frame = bootstrap_relationships_frame(entities)
    default_policy_inputs = [
        *[
            ArtifactInput(
                artifact="bootstrap-corpus",
                table="entities",
                column=column,
                source_fields=[
                    SourceFieldReference(
                        source_id=source_id,
                        field_name=("sources" if column == "field_sources_json" else column),
                    )
                ],
                use=PublishableUse.PUBLIC_PARQUET,
            )
            for column in entity_frame.columns
        ],
        *[
            ArtifactInput(
                artifact="bootstrap-corpus",
                table="relationships",
                column=column,
                source_fields=[
                    SourceFieldReference(
                        source_id=source_id,
                        field_name=column,
                    )
                ],
                use=PublishableUse.PUBLIC_PARQUET,
            )
            for column in relationship_frame.columns
        ],
    ]
    validation = validate_artifact_inputs(policy_inputs or default_policy_inputs)

    output_dir.mkdir(parents=True, exist_ok=True)
    entities_path = output_dir / f"{input_path.stem}-entities.parquet"
    relationships_path = output_dir / f"{input_path.stem}-relationships.parquet"
    manifest_path = output_dir / f"{input_path.stem}-manifest.json"

    entity_frame.write_parquet(entities_path, compression="zstd")
    relationship_frame.write_parquet(relationships_path, compression="zstd")

    manifest: dict[str, Any] = {
        **artifact_manifest_metadata(
            artifact="bootstrap-corpus",
            build_stage="bootstrap",
        ),
        "input_path": str(input_path),
        "row_count": entity_frame.height,
        "entity_row_count": entity_frame.height,
        "relationship_row_count": relationship_frame.height,
        "domains": sorted(entity_frame.get_column("domain").unique().to_list()),
        "publishability": publishability_manifest_payload(
            [
                *validation.validated_uses,
                PublishableUse.PUBLIC_MANIFEST,
            ],
            input_count=validation.input_count,
        ),
        "files": [
            {
                "path": entities_path.name,
                "format": "parquet",
                "compression": "zstd",
                "kind": "entities",
            },
            {
                "path": relationships_path.name,
                "format": "parquet",
                "compression": "zstd",
                "kind": "relationships",
            }
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path
