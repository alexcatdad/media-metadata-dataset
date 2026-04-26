from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from media_offline_database.sources import SourceRole


class MediaDomain(StrEnum):
    """First-class v1 media domains."""

    ANIME = "anime"
    TV = "tv"
    MOVIE = "movie"


class SourcePathStatus(StrEnum):
    """Implementation state for a v1 source path."""

    LOCKED = "locked"
    WAITING_ON_POLICY_SCHEMA = "waiting_on_policy_schema"
    EXECUTABLE_MILESTONE = "executable_milestone"


class ProvisionalSourcePathFieldClass(StrEnum):
    """Temporary source-path planning hint until shared field policy lands."""

    PUBLIC_FIELD = "public_field"
    PUBLIC_ID = "public_id"
    LOCAL_ONLY = "local_only"
    RUNTIME_ONLY = "runtime_only"
    BLOCKED = "blocked"


class V1SourcePath(BaseModel):
    """Selected source path for one v1 domain."""

    model_config = ConfigDict(extra="forbid")

    domain: MediaDomain
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_role: SourceRole
    status: SourcePathStatus
    publishable_fields: tuple[str, ...] = Field(min_length=1)
    restricted_fields: tuple[str, ...] = ()
    provider_review_todos: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_explicit_review_work_for_unready_paths(self) -> V1SourcePath:
        if (
            self.status == SourcePathStatus.WAITING_ON_POLICY_SCHEMA
            and not self.provider_review_todos
        ):
            raise ValueError("waiting source paths must record provider review TODOs")
        return self


class SourceSnapshot(BaseModel):
    """Normalized metadata for a provider source snapshot."""

    model_config = ConfigDict(extra="forbid")

    source_snapshot_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_role: SourceRole
    snapshot_kind: str = Field(min_length=1)
    fetched_at: datetime
    source_published_at: datetime | None = None
    fetch_window_started_at: datetime | None = None
    fetch_window_finished_at: datetime | None = None
    source_version: str | None = None
    policy_version: str = Field(min_length=1)
    publishable_field_policy_version: str = Field(min_length=1)
    artifact_policy_version: str = Field(min_length=1)
    record_count: int | None = Field(default=None, ge=0)
    content_hash: str | None = None
    manifest_uri: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_fetch_window(self) -> SourceSnapshot:
        if (
            self.fetch_window_started_at is not None
            and self.fetch_window_finished_at is not None
            and self.fetch_window_finished_at < self.fetch_window_started_at
        ):
            raise ValueError("fetch window cannot finish before it starts")
        return self


class ProviderRun(BaseModel):
    """Auditable adapter run metadata that must not expose secrets."""

    model_config = ConfigDict(extra="forbid")

    provider_run_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_snapshot_id: str | None = None
    adapter_name: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    started_at: datetime
    finished_at: datetime | None = None
    request_count: int = Field(default=0, ge=0)
    cache_hit_count: int = Field(default=0, ge=0)
    status: str = Field(min_length=1)
    auth_shape: str | None = None
    secret_refs: tuple[str, ...] = ()
    notes: str | None = None

    @field_validator("secret_refs")
    @classmethod
    def forbid_secret_values(cls, secret_refs: tuple[str, ...]) -> tuple[str, ...]:
        for secret_ref in secret_refs:
            lowered = secret_ref.lower()
            if any(marker in lowered for marker in ("token=", "bearer ", "secret=", "api_key=")):
                raise ValueError("provider run metadata may reference secret names, not values")
        return secret_refs

    @model_validator(mode="after")
    def validate_provider_run(self) -> ProviderRun:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("provider run cannot finish before it starts")
        if self.cache_hit_count > self.request_count:
            raise ValueError("cache hits cannot exceed request count")
        return self


class SourceRecordRef(BaseModel):
    """Join contract from normalized rows back to source records."""

    model_config = ConfigDict(extra="forbid")

    source_record_ref_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    source_snapshot_id: str | None = None
    provider_run_id: str | None = None
    source_role: SourceRole
    provisional_source_path_field_class: ProvisionalSourcePathFieldClass
    source_url: str | None = None
    source_record_hash: str | None = None

    @model_validator(mode="after")
    def require_snapshot_or_run(self) -> SourceRecordRef:
        if self.source_snapshot_id is None and self.provider_run_id is None:
            raise ValueError("source record refs must point to a snapshot or provider run")
        return self


def v1_source_path_plan() -> tuple[V1SourcePath, ...]:
    """Return the locked v1 source path plan for ingest-normalization."""

    return (
        V1SourcePath(
            domain=MediaDomain.ANIME,
            source_id="manami_anime_offline_database",
            source_name="manami anime-offline-database",
            source_role=SourceRole.BACKBONE_SOURCE,
            status=SourcePathStatus.LOCKED,
            publishable_fields=(
                "anime_id",
                "canonical_title",
                "synonyms",
                "sources",
                "type",
                "episodes",
                "status",
                "season",
                "related_anime",
                "tags",
            ),
            restricted_fields=(),
            notes="Anime source path uses manami release assets and remains the anime v1 spine.",
        ),
        V1SourcePath(
            domain=MediaDomain.TV,
            source_id="tvmaze",
            source_name="TVmaze",
            source_role=SourceRole.BACKBONE_SOURCE,
            status=SourcePathStatus.EXECUTABLE_MILESTONE,
            publishable_fields=(
                "tvmaze_id",
                "url",
                "name",
                "type",
                "language",
                "genres",
                "status",
                "premiered",
                "ended",
                "runtime",
                "average_runtime",
                "official_site",
                "network",
                "web_channel",
            ),
            restricted_fields=("summary_html",),
            provider_review_todos=(
                "Encode CC BY-SA attribution/share-alike handling in source and artifact policy.",
                "Classify summary HTML separately before retrieval text or embeddings consume it.",
            ),
            notes="TVmaze is the first non-anime TV path; anime TV series do not count here.",
        ),
        V1SourcePath(
            domain=MediaDomain.MOVIE,
            source_id="wikidata",
            source_name="Wikidata movie graph",
            source_role=SourceRole.BACKBONE_SOURCE,
            status=SourcePathStatus.EXECUTABLE_MILESTONE,
            publishable_fields=(
                "wikidata_qid",
                "label",
                "aliases",
                "instance_of",
                "publication_date",
                "country",
                "external_ids",
                "adaptation_links",
                "franchise_links",
            ),
            restricted_fields=(),
            provider_review_todos=(
                "Define the SPARQL/dump extraction recipe and CC0 attribution posture in policy fixtures.",
                "Specify which external ID properties can be emitted as IDs versus local evidence.",
            ),
            open_questions=(
                "Whether TMDB daily ID exports join this path at v1 as ID_SOURCE evidence only.",
            ),
            notes="Wikidata is the first non-anime movie path; anime movies do not count here.",
        ),
    )


def source_path_plan_by_domain() -> dict[MediaDomain, V1SourcePath]:
    return {source_path.domain: source_path for source_path in v1_source_path_plan()}


def example_source_snapshot() -> SourceSnapshot:
    """Small deterministic example used by docs and tests."""

    now = datetime(2026, 4, 26, tzinfo=UTC)
    return SourceSnapshot(
        source_snapshot_id="tvmaze:shows:2026-04-26",
        source_id="tvmaze",
        source_role=SourceRole.BACKBONE_SOURCE,
        snapshot_kind="incremental_api_window",
        fetched_at=now,
        fetch_window_started_at=now,
        fetch_window_finished_at=now,
        policy_version="source-policy-v1",
        publishable_field_policy_version="source-field-policy-v1",
        artifact_policy_version="artifact-policy-v1",
        record_count=0,
        notes="Example metadata only; no provider payload is embedded.",
    )
