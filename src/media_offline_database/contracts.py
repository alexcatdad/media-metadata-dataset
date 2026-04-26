from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MANIFEST_SCHEMA = "media-metadata-dataset.manifest"
MANIFEST_SCHEMA_VERSION = 1
CORE_SCHEMA_VERSION = "core.v1"


class CompatibilityTier(StrEnum):
    CORE = "core"
    PROFILE = "profile"
    DERIVED = "derived"
    EXPERIMENTAL = "experimental"


class ArtifactFormat(StrEnum):
    PARQUET = "parquet"


class Domain(StrEnum):
    ANIME = "anime"
    TV = "tv"
    MOVIE = "movie"


class ConfidenceTier(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class IdentityChangeType(StrEnum):
    MERGE = "merge"
    SPLIT = "split"
    REDIRECT = "redirect"
    DEPRECATION = "deprecation"
    WITHDRAWAL = "withdrawal"
    SUPERSESSION = "supersession"


class PolicyVersions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_policy_version: str = Field(min_length=1)
    field_policy_version: str = Field(min_length=1)
    artifact_policy_version: str = Field(min_length=1)
    publishability_validation_version: str = Field(min_length=1)


class SourceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_role: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    domains: list[Domain] = Field(min_length=1)
    record_count: int = Field(ge=0)


class CompatibilityNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notice_id: str = Field(min_length=1)
    tier: CompatibilityTier
    severity: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ArtifactTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    format: ArtifactFormat = ArtifactFormat.PARQUET
    row_count: int = Field(ge=0)
    schema_version: str = Field(min_length=1)
    compatibility_tier: CompatibilityTier
    policy_versions: PolicyVersions
    recipe_versions: dict[str, str] = Field(min_length=1)
    enrichment_status: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def artifact_path_is_relative(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("artifact path must be a relative POSIX path")
        if path.suffix != ".parquet":
            raise ValueError("artifact path must point to a parquet file")
        return value


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_schema: str = MANIFEST_SCHEMA
    manifest_schema_version: int = MANIFEST_SCHEMA_VERSION
    dataset_line: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    core_schema_version: str = Field(min_length=1)
    hf_repo_id: str = Field(min_length=1)
    hf_commit_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    hf_revision: str | None = Field(default=None, min_length=1)
    published_at: datetime | None = None
    tables: list[ArtifactTable] = Field(min_length=1)
    source_coverage: list[SourceCoverage] = Field(default_factory=lambda: [])
    policy_versions: PolicyVersions
    recipe_versions: dict[str, str] = Field(min_length=1)
    confidence_recipe_versions: dict[str, str] = Field(default_factory=dict)
    enrichment_status: dict[str, str] = Field(default_factory=dict)
    compatibility_notices: list[CompatibilityNotice] = Field(default_factory=lambda: [])

    @model_validator(mode="after")
    def table_names_are_unique(self) -> ArtifactManifest:
        table_names = [table.table_name for table in self.tables]
        if len(table_names) != len(set(table_names)):
            raise ValueError("manifest table names must be unique")
        return self


class PublishedArtifactManifest(ArtifactManifest):
    @model_validator(mode="after")
    def publish_revision_identity_is_stamped(self) -> PublishedArtifactManifest:
        if self.hf_commit_sha is None:
            raise ValueError("published manifests require hf_commit_sha")
        if self.hf_revision is None:
            raise ValueError("published manifests require hf_revision")
        if self.published_at is None:
            raise ValueError("published manifests require published_at")
        return self


class ColumnContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    dtype: str = Field(min_length=1)
    nullable: bool = True
    required: bool = True


class TableContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    table_name: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    compatibility_tier: CompatibilityTier
    columns: tuple[ColumnContract, ...] = Field(min_length=1)

    @property
    def required_column_names(self) -> set[str]:
        return {column.name for column in self.columns if column.required}


def column(name: str, dtype: str, *, nullable: bool = True) -> ColumnContract:
    return ColumnContract(name=name, dtype=dtype, nullable=nullable)


CORE_TABLE_CONTRACTS: dict[str, TableContract] = {
    "entities": TableContract(
        table_name="entities",
        schema_version=CORE_SCHEMA_VERSION,
        compatibility_tier=CompatibilityTier.CORE,
        columns=(
            column("entity_id", "string", nullable=False),
            column("domain", "string", nullable=False),
            column("media_type", "string", nullable=False),
            column("status", "string", nullable=False),
            column("release_year", "int64"),
            column("release_date", "date"),
            column("confidence_tier", "string", nullable=False),
            column("evidence_count", "int64", nullable=False),
            column("conflict_status", "string", nullable=False),
            column("quality_flags", "list[string]", nullable=False),
            column("evidence_id", "string"),
            column("provenance_id", "string"),
            column("recipe_version", "string", nullable=False),
            column("manifest_table_name", "string", nullable=False),
        ),
    ),
    "titles": TableContract(
        table_name="titles",
        schema_version=CORE_SCHEMA_VERSION,
        compatibility_tier=CompatibilityTier.CORE,
        columns=(
            column("title_id", "string", nullable=False),
            column("entity_id", "string", nullable=False),
            column("title", "string", nullable=False),
            column("title_type", "string", nullable=False),
            column("language", "string"),
            column("script", "string"),
            column("source_id", "string"),
            column("evidence_id", "string"),
            column("provenance_id", "string"),
            column("confidence_tier", "string", nullable=False),
            column("quality_flags", "list[string]", nullable=False),
            column("recipe_version", "string", nullable=False),
        ),
    ),
    "external_ids": TableContract(
        table_name="external_ids",
        schema_version=CORE_SCHEMA_VERSION,
        compatibility_tier=CompatibilityTier.CORE,
        columns=(
            column("external_id_row_id", "string", nullable=False),
            column("entity_id", "string", nullable=False),
            column("source_id", "string", nullable=False),
            column("source_role", "string", nullable=False),
            column("external_id", "string", nullable=False),
            column("url", "string"),
            column("provenance_id", "string"),
            column("recipe_version", "string", nullable=False),
        ),
    ),
    "relationships": TableContract(
        table_name="relationships",
        schema_version=CORE_SCHEMA_VERSION,
        compatibility_tier=CompatibilityTier.CORE,
        columns=(
            column("relationship_id", "string", nullable=False),
            column("source_entity_id", "string", nullable=False),
            column("target_entity_id", "string", nullable=False),
            column("relationship_type", "string", nullable=False),
            column("relationship_family", "string", nullable=False),
            column("direction", "string", nullable=False),
            column("inverse_relationship_type", "string"),
            column("confidence_tier", "string", nullable=False),
            column("evidence_count", "int64", nullable=False),
            column("conflict_status", "string", nullable=False),
            column("quality_flags", "list[string]", nullable=False),
            column("evidence_id", "string"),
            column("provenance_id", "string"),
            column("recipe_version", "string", nullable=False),
        ),
    ),
    "relationship_evidence": TableContract(
        table_name="relationship_evidence",
        schema_version=CORE_SCHEMA_VERSION,
        compatibility_tier=CompatibilityTier.CORE,
        columns=(
            column("relationship_evidence_id", "string", nullable=False),
            column("relationship_id", "string", nullable=False),
            column("evidence_id", "string", nullable=False),
            column("source_id", "string", nullable=False),
            column("source_record_id", "string"),
            column("evidence_strength", "string", nullable=False),
            column("claim", "string"),
            column("provenance_id", "string"),
            column("recipe_version", "string", nullable=False),
        ),
    ),
    "facets": TableContract(
        table_name="facets",
        schema_version=CORE_SCHEMA_VERSION,
        compatibility_tier=CompatibilityTier.CORE,
        columns=(
            column("facet_id", "string", nullable=False),
            column("entity_id", "string", nullable=False),
            column("facet_namespace", "string", nullable=False),
            column("facet_key", "string", nullable=False),
            column("facet_value", "string", nullable=False),
            column("confidence_tier", "string", nullable=False),
            column("evidence_id", "string"),
            column("provenance_id", "string"),
            column("recipe_version", "string", nullable=False),
        ),
    ),
    "judgments": TableContract(
        table_name="judgments",
        schema_version=CORE_SCHEMA_VERSION,
        compatibility_tier=CompatibilityTier.DERIVED,
        columns=(
            column("judgment_id", "string", nullable=False),
            column("target_table", "string", nullable=False),
            column("target_id", "string", nullable=False),
            column("provider", "string", nullable=False),
            column("model", "string", nullable=False),
            column("prompt_version", "string", nullable=False),
            column("output_schema_version", "string", nullable=False),
            column("confidence_tier", "string", nullable=False),
            column("quality_flags", "list[string]", nullable=False),
            column("provenance_id", "string"),
            column("recipe_version", "string", nullable=False),
        ),
    ),
    "provenance": TableContract(
        table_name="provenance",
        schema_version=CORE_SCHEMA_VERSION,
        compatibility_tier=CompatibilityTier.CORE,
        columns=(
            column("provenance_id", "string", nullable=False),
            column("source_id", "string"),
            column("source_snapshot_id", "string"),
            column("provider_run_id", "string"),
            column("recipe_run_id", "string"),
            column("policy_version", "string", nullable=False),
        ),
    ),
    "source_records": TableContract(
        table_name="source_records",
        schema_version=CORE_SCHEMA_VERSION,
        compatibility_tier=CompatibilityTier.CORE,
        columns=(
            column("source_record_ref_id", "string", nullable=False),
            column("entity_id", "string", nullable=False),
            column("source_id", "string", nullable=False),
            column("source_record_id", "string", nullable=False),
            column("source_snapshot_id", "string"),
            column("provider_run_id", "string"),
            column("source_role", "string", nullable=False),
            column("source_url", "string"),
            column("source_record_hash", "string"),
            column("provenance_id", "string"),
            column("recipe_version", "string", nullable=False),
        ),
    ),
}


PROFILE_TABLE_CONTRACTS: dict[str, TableContract] = {
    "anime_profile": TableContract(
        table_name="anime_profile",
        schema_version="anime_profile.v1",
        compatibility_tier=CompatibilityTier.PROFILE,
        columns=(
            column("entity_id", "string", nullable=False),
            column("profile_schema_version", "string", nullable=False),
            column("anime_format", "string"),
            column("anime_season", "string"),
            column("anime_season_year", "int64"),
            column("cour_count", "int64"),
            column("episode_count", "int64"),
            column("source_demographic", "string"),
            column("anime_relationship_hints", "list[string]", nullable=False),
            column("provenance_id", "string"),
            column("recipe_version", "string", nullable=False),
        ),
    ),
    "tv_profile": TableContract(
        table_name="tv_profile",
        schema_version="tv_profile.v1",
        compatibility_tier=CompatibilityTier.PROFILE,
        columns=(
            column("entity_id", "string", nullable=False),
            column("profile_schema_version", "string", nullable=False),
            column("season_count", "int64"),
            column("episode_count", "int64"),
            column("show_status", "string"),
            column("network_or_platform", "string"),
            column("release_shape", "string"),
            column("provenance_id", "string"),
            column("recipe_version", "string", nullable=False),
        ),
    ),
    "movie_profile": TableContract(
        table_name="movie_profile",
        schema_version="movie_profile.v1",
        compatibility_tier=CompatibilityTier.PROFILE,
        columns=(
            column("entity_id", "string", nullable=False),
            column("profile_schema_version", "string", nullable=False),
            column("runtime_minutes", "int64"),
            column("release_year", "int64"),
            column("release_date", "date"),
            column("collection_id", "string"),
            column("franchise_hint", "string"),
            column("release_shape", "string"),
            column("provenance_id", "string"),
            column("recipe_version", "string", nullable=False),
        ),
    ),
}


IDENTITY_CHANGES_CONTRACT = TableContract(
    table_name="identity_changes",
    schema_version=CORE_SCHEMA_VERSION,
    compatibility_tier=CompatibilityTier.CORE,
    columns=(
        column("identity_change_id", "string", nullable=False),
        column("change_type", "string", nullable=False),
        column("old_entity_id", "string", nullable=False),
        column("new_entity_ids", "list[string]", nullable=False),
        column("reason", "string", nullable=False),
        column("evidence_id", "string"),
        column("effective_snapshot_id", "string", nullable=False),
        column("provenance_id", "string", nullable=False),
        column("confidence_tier", "string", nullable=False),
        column("quality_flags", "list[string]", nullable=False),
        column("recipe_version", "string", nullable=False),
    ),
)


class IdentityChangeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_change_id: str = Field(min_length=1)
    change_type: IdentityChangeType
    old_entity_id: str = Field(min_length=1)
    new_entity_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    evidence_id: str | None = None
    effective_snapshot_id: str = Field(min_length=1)
    provenance_id: str = Field(min_length=1)
    confidence_tier: ConfidenceTier = ConfidenceTier.UNKNOWN
    quality_flags: list[str] = Field(default_factory=list)
    recipe_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_new_identity_targets(self) -> IdentityChangeRecord:
        if self.old_entity_id in self.new_entity_ids:
            raise ValueError("identity changes cannot point an entity ID at itself")
        if len(self.new_entity_ids) != len(set(self.new_entity_ids)):
            raise ValueError("identity change targets must be unique")
        if self.change_type is IdentityChangeType.SPLIT and len(self.new_entity_ids) < 2:
            raise ValueError("split changes must mint at least two new entity IDs")
        if self.change_type in {
            IdentityChangeType.MERGE,
            IdentityChangeType.REDIRECT,
            IdentityChangeType.SUPERSESSION,
        } and len(self.new_entity_ids) != 1:
            raise ValueError("merge, redirect, and supersession changes require one new entity ID")
        if self.change_type in {
            IdentityChangeType.DEPRECATION,
            IdentityChangeType.WITHDRAWAL,
        } and self.new_entity_ids:
            raise ValueError("deprecation and withdrawal changes must not have new entity IDs")
        return self


def resolve_identity_forward(
    entity_id: str,
    changes: list[IdentityChangeRecord],
) -> list[str]:
    changes_by_old_id: dict[str, IdentityChangeRecord] = {}
    for change in changes:
        if change.old_entity_id in changes_by_old_id:
            raise ValueError(f"duplicate identity change for {change.old_entity_id}")
        changes_by_old_id[change.old_entity_id] = change

    def resolve_one(current_entity_id: str, seen: set[str]) -> list[str]:
        if current_entity_id in seen:
            raise ValueError(f"identity change cycle detected at {current_entity_id}")

        change = changes_by_old_id.get(current_entity_id)
        if change is None:
            return [current_entity_id]
        if not change.new_entity_ids:
            return []

        next_seen = {*seen, current_entity_id}
        resolved: list[str] = []
        for next_entity_id in change.new_entity_ids:
            for resolved_entity_id in resolve_one(next_entity_id, next_seen):
                if resolved_entity_id not in resolved:
                    resolved.append(resolved_entity_id)
        return resolved

    return resolve_one(entity_id, set())


ALL_TABLE_CONTRACTS: dict[str, TableContract] = {
    **CORE_TABLE_CONTRACTS,
    **PROFILE_TABLE_CONTRACTS,
    "identity_changes": IDENTITY_CHANGES_CONTRACT,
}
