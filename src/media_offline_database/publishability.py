from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, model_validator

from media_offline_database.sources import SourceRole

PUBLISHABILITY_POLICY_VERSION = "publishability-policy-v1"
SOURCE_POLICY_VERSION = "source-policy-v1"
SOURCE_FIELD_POLICY_VERSION = "source-field-policy-v1"
ARTIFACT_POLICY_VERSION = "artifact-policy-v1"
CURRENT_POLICY_VERSIONS = {
    "artifact_policy": ARTIFACT_POLICY_VERSION,
    "publishability_policy": PUBLISHABILITY_POLICY_VERSION,
    "source_field_policy": SOURCE_FIELD_POLICY_VERSION,
    "source_policy": SOURCE_POLICY_VERSION,
}
COMPATIBLE_POLICY_VERSION_SETS = (CURRENT_POLICY_VERSIONS,)


class PublishabilityClass(StrEnum):
    """Field-level eligibility classes for public artifact validation."""

    PUBLIC_METADATA = "PUBLIC_METADATA"
    PUBLIC_IDENTIFIER = "PUBLIC_IDENTIFIER"
    PUBLIC_DERIVED = "PUBLIC_DERIVED"
    LOCAL_ONLY = "LOCAL_ONLY"
    RUNTIME_ONLY = "RUNTIME_ONLY"
    PAID_EXPERIMENT_ONLY = "PAID_EXPERIMENT_ONLY"
    BLOCKED = "BLOCKED"


class PublishableUse(StrEnum):
    """Use sites that can encode or expose source values."""

    PUBLIC_PARQUET = "PUBLIC_PARQUET"
    PUBLIC_MANIFEST = "PUBLIC_MANIFEST"
    RETRIEVAL_TEXT = "RETRIEVAL_TEXT"
    EMBEDDING_INPUT = "EMBEDDING_INPUT"
    LLM_JUDGMENT_INPUT = "LLM_JUDGMENT_INPUT"
    LOCAL_MATCHING = "LOCAL_MATCHING"
    QA = "QA"


class SourcePolicy(BaseModel):
    """Reviewed provider/source policy required before source data shapes artifacts."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_role: SourceRole
    policy_version: str = SOURCE_POLICY_VERSION
    reviewed_at: str
    license_url: str | None = None
    terms_url: str | None = None
    attribution_required: str
    cache_limits: str
    allowed_uses: list[PublishableUse]
    retention_rules: str
    notes: str = ""

    @model_validator(mode="after")
    def _must_have_rights_evidence(self) -> SourcePolicy:
        if self.license_url is None and self.terms_url is None:
            raise ValueError("source policy requires license_url or terms_url evidence")
        return self


class SourceFieldPolicy(BaseModel):
    """Publishability policy for one field from one reviewed source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    field_name: str
    publishability: PublishabilityClass
    policy_version: str = SOURCE_FIELD_POLICY_VERSION
    allowed_uses: list[PublishableUse]
    attribution_required: str
    retention_rules: str
    notes: str = ""


class ArtifactPolicy(BaseModel):
    """Allowed input classes for a public artifact column or sidecar surface."""

    model_config = ConfigDict(extra="forbid")

    artifact: str
    table: str
    column: str
    allowed_input_classes: list[PublishabilityClass]
    policy_version: str = ARTIFACT_POLICY_VERSION
    allowed_uses: list[PublishableUse]
    validation_rule: str


class SourceFieldReference(BaseModel):
    """A concrete source field used as input to an artifact column or text surface."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    field_name: str


class ArtifactInput(BaseModel):
    """Lineage declaration for one artifact column or derived text input."""

    model_config = ConfigDict(extra="forbid")

    artifact: str
    table: str
    column: str
    source_fields: list[SourceFieldReference]
    use: PublishableUse


class PublishabilityPolicyCatalog(BaseModel):
    """In-memory policy catalog used by artifact writers and release gates."""

    model_config = ConfigDict(extra="forbid")

    source_policies: dict[str, SourcePolicy]
    source_field_policies: dict[str, SourceFieldPolicy]
    artifact_policies: dict[str, ArtifactPolicy]

    @staticmethod
    def field_key(source_id: str, field_name: str) -> str:
        return f"{source_id}.{field_name}"

    @staticmethod
    def artifact_key(artifact: str, table: str, column: str) -> str:
        return f"{artifact}.{table}.{column}"

    def source_field_policy(self, reference: SourceFieldReference) -> SourceFieldPolicy | None:
        return self.source_field_policies.get(
            self.field_key(reference.source_id, reference.field_name)
        )

    def artifact_policy(self, input_: ArtifactInput) -> ArtifactPolicy | None:
        return self.artifact_policies.get(
            self.artifact_key(input_.artifact, input_.table, input_.column)
        )

    def policy_versions(self) -> dict[str, str]:
        return dict(CURRENT_POLICY_VERSIONS)


class PublishabilityError(ValueError):
    """Raised when restricted or unpolicyed inputs would enter a public surface."""


class PublishabilityValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_versions: dict[str, str]
    validated_uses: list[PublishableUse]
    input_count: int

    def manifest_payload(self) -> dict[str, Any]:
        return {
            "input_count": self.input_count,
            "policy_versions": self.policy_versions,
            "validated_uses": [use.value for use in self.validated_uses],
        }


def publishability_manifest_payload(
    validated_uses: Iterable[PublishableUse] = (PublishableUse.PUBLIC_MANIFEST,),
    *,
    catalog: PublishabilityPolicyCatalog | None = None,
    input_count: int = 0,
) -> dict[str, Any]:
    resolved_catalog = catalog or default_policy_catalog()
    return PublishabilityValidationResult(
        policy_versions=resolved_catalog.policy_versions(),
        validated_uses=list(dict.fromkeys(validated_uses)),
        input_count=input_count,
    ).manifest_payload()


def validate_artifact_inputs(
    inputs: Sequence[ArtifactInput],
    *,
    catalog: PublishabilityPolicyCatalog | None = None,
) -> PublishabilityValidationResult:
    resolved_catalog = catalog or default_policy_catalog()
    errors: list[str] = []

    for input_ in inputs:
        artifact_policy = resolved_catalog.artifact_policy(input_)
        if artifact_policy is None:
            errors.append(
                "missing artifact policy for "
                f"{input_.artifact}.{input_.table}.{input_.column}"
            )
            continue

        if input_.use not in artifact_policy.allowed_uses:
            errors.append(
                f"{input_.artifact}.{input_.table}.{input_.column} does not allow "
                f"{input_.use.value}"
            )

        for reference in input_.source_fields:
            source_policy = resolved_catalog.source_policies.get(reference.source_id)
            if source_policy is None:
                errors.append(f"missing source policy for {reference.source_id}")
                continue
            if input_.use not in source_policy.allowed_uses:
                errors.append(
                    f"{reference.source_id}.{reference.field_name} cannot be used for "
                    f"{input_.use.value}"
                )

            field_policy = resolved_catalog.source_field_policy(reference)
            if field_policy is None:
                errors.append(
                    "missing source field policy for "
                    f"{reference.source_id}.{reference.field_name}"
                )
                continue
            if input_.use not in field_policy.allowed_uses:
                errors.append(
                    f"{reference.source_id}.{reference.field_name} field policy does not allow "
                    f"{input_.use.value}"
                )
            if field_policy.publishability not in artifact_policy.allowed_input_classes:
                errors.append(
                    f"{reference.source_id}.{reference.field_name} is "
                    f"{field_policy.publishability.value}, not allowed for "
                    f"{input_.artifact}.{input_.table}.{input_.column}"
                )

    if errors:
        raise PublishabilityError("; ".join(errors))

    return PublishabilityValidationResult(
        policy_versions=resolved_catalog.policy_versions(),
        validated_uses=list(dict.fromkeys(input_.use for input_ in inputs)),
        input_count=len(inputs),
    )


def validate_manifest_publishability(
    manifest: Mapping[str, Any],
    *,
    compatible_policy_versions: Sequence[Mapping[str, str]] = COMPATIBLE_POLICY_VERSION_SETS,
) -> None:
    publishability_value: object = manifest.get("publishability")
    if not isinstance(publishability_value, dict):
        raise PublishabilityError("manifest missing publishability validation block")
    publishability = cast(dict[object, object], publishability_value)

    policy_versions_value: object | None = publishability.get("policy_versions")
    if not isinstance(policy_versions_value, dict):
        raise PublishabilityError("manifest missing publishability policy_versions")
    raw_policy_versions = cast(dict[object, object], policy_versions_value)
    policy_versions = {str(key): str(value) for key, value in raw_policy_versions.items()}

    compatible_versions = [
        {str(key): str(value) for key, value in version_set.items()}
        for version_set in compatible_policy_versions
    ]
    if policy_versions not in compatible_versions:
        raise PublishabilityError(
            "manifest publishability policy versions are not in the compatibility registry"
        )

    validated_uses_value: object | None = publishability.get("validated_uses")
    if not isinstance(validated_uses_value, list) or PublishableUse.PUBLIC_MANIFEST.value not in {
        str(use) for use in cast(list[object], validated_uses_value)
    }:
        raise PublishabilityError("manifest was not validated for PUBLIC_MANIFEST")


def validate_current_manifest_publishability(manifest: Mapping[str, Any]) -> None:
    validate_manifest_publishability(
        manifest,
        compatible_policy_versions=(CURRENT_POLICY_VERSIONS,),
    )


def validate_text_inputs(
    inputs: Sequence[SourceFieldReference],
    *,
    artifact: str,
    table: str,
    column: str,
    use: PublishableUse,
    catalog: PublishabilityPolicyCatalog | None = None,
) -> PublishabilityValidationResult:
    return validate_artifact_inputs(
        [
            ArtifactInput(
                artifact=artifact,
                table=table,
                column=column,
                source_fields=list(inputs),
                use=use,
            )
        ],
        catalog=catalog,
    )


def _source_policy(
    source_id: str,
    source_role: SourceRole,
    *,
    license_url: str | None = None,
    terms_url: str | None = None,
    allowed_uses: Sequence[PublishableUse],
    attribution_required: str = "follow source attribution requirements",
    cache_limits: str = "see docs/source-admissibility-and-rate-limits.md",
    retention_rules: str = "retain only policy-approved public fields in public artifacts",
    notes: str = "",
) -> SourcePolicy:
    return SourcePolicy(
        source_id=source_id,
        source_role=source_role,
        reviewed_at="2026-04-26",
        license_url=license_url,
        terms_url=terms_url,
        attribution_required=attribution_required,
        cache_limits=cache_limits,
        allowed_uses=list(allowed_uses),
        retention_rules=retention_rules,
        notes=notes,
    )


def _field_policy(
    source_id: str,
    field_name: str,
    publishability: PublishabilityClass,
    *,
    allowed_uses: Sequence[PublishableUse],
    retention_rules: str = "retain according to source policy",
    attribution_required: str = "follow source policy",
    notes: str = "",
) -> SourceFieldPolicy:
    return SourceFieldPolicy(
        source_id=source_id,
        field_name=field_name,
        publishability=publishability,
        allowed_uses=list(allowed_uses),
        attribution_required=attribution_required,
        retention_rules=retention_rules,
        notes=notes,
    )


def _artifact_policy(
    artifact: str,
    table: str,
    column: str,
    *,
    allowed_input_classes: Sequence[PublishabilityClass],
    allowed_uses: Sequence[PublishableUse],
    validation_rule: str,
) -> ArtifactPolicy:
    return ArtifactPolicy(
        artifact=artifact,
        table=table,
        column=column,
        allowed_input_classes=list(allowed_input_classes),
        allowed_uses=list(allowed_uses),
        validation_rule=validation_rule,
    )


def _default_source_policies() -> dict[str, SourcePolicy]:
    public_uses = [
        PublishableUse.PUBLIC_PARQUET,
        PublishableUse.PUBLIC_MANIFEST,
        PublishableUse.RETRIEVAL_TEXT,
        PublishableUse.EMBEDDING_INPUT,
        PublishableUse.LLM_JUDGMENT_INPUT,
        PublishableUse.LOCAL_MATCHING,
        PublishableUse.QA,
    ]
    id_uses = [
        PublishableUse.PUBLIC_PARQUET,
        PublishableUse.PUBLIC_MANIFEST,
        PublishableUse.LOCAL_MATCHING,
        PublishableUse.QA,
    ]
    local_uses = [PublishableUse.LOCAL_MATCHING, PublishableUse.QA]
    runtime_uses = [PublishableUse.LOCAL_MATCHING, PublishableUse.QA]
    blocked_uses: list[PublishableUse] = []

    policies = [
        _source_policy(
            "bootstrap_seed",
            SourceRole.BACKBONE_SOURCE,
            license_url="https://github.com/alexcatdad/media-metadata-dataset",
            allowed_uses=public_uses,
            notes="Checked-in bootstrap fixture values reviewed for public test artifacts.",
        ),
        _source_policy(
            "manami",
            SourceRole.BACKBONE_SOURCE,
            license_url="https://github.com/manami-project/anime-offline-database",
            allowed_uses=public_uses,
        ),
        _source_policy(
            "wikidata",
            SourceRole.BACKBONE_SOURCE,
            license_url="https://www.wikidata.org/wiki/Wikidata:Licensing",
            allowed_uses=public_uses,
        ),
        _source_policy(
            "tvmaze",
            SourceRole.BACKBONE_SOURCE,
            terms_url="https://www.tvmaze.com/api",
            allowed_uses=public_uses,
        ),
        _source_policy(
            "openlibrary",
            SourceRole.BACKBONE_SOURCE,
            license_url="https://openlibrary.org/developers/licensing",
            terms_url="https://openlibrary.org/developers/api",
            allowed_uses=public_uses,
        ),
        _source_policy(
            "tmdb_daily_ids",
            SourceRole.ID_SOURCE,
            terms_url="https://developer.themoviedb.org/docs/daily-id-exports",
            allowed_uses=id_uses,
        ),
        _source_policy(
            "anidb_title_dump",
            SourceRole.ID_SOURCE,
            terms_url="https://wiki.anidb.net/API",
            allowed_uses=id_uses,
        ),
        _source_policy(
            "thetvdb",
            SourceRole.ID_SOURCE,
            terms_url="https://www.thetvdb.com/tos",
            allowed_uses=id_uses,
        ),
        _source_policy(
            "tmdb_api",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://www.themoviedb.org/api-terms-of-use",
            allowed_uses=local_uses,
        ),
        _source_policy(
            "anidb_http_api",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://wiki.anidb.net/HTTP_API_Definition",
            allowed_uses=local_uses,
        ),
        _source_policy(
            "anilist",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://anilist.gitbook.io/anilist-apiv2-docs/docs/guide/terms-of-use",
            allowed_uses=local_uses,
        ),
        _source_policy(
            "mal_api",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://myanimelist.net/apiconfig/references/api/v2",
            allowed_uses=local_uses,
        ),
        _source_policy(
            "jikan",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://www.postman.com/aqua5624/jikan-api/collection/m52ghbu/jikan-api-v4",
            allowed_uses=local_uses,
        ),
        _source_policy(
            "kitsu",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://hummingbird-me.github.io/api-docs/",
            allowed_uses=local_uses,
        ),
        _source_policy(
            "ann",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://www.animenewsnetwork.org/terms/",
            allowed_uses=local_uses,
        ),
        _source_policy(
            "imdb_datasets",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://developer.imdb.com/non-commercial-datasets/",
            allowed_uses=local_uses,
        ),
        _source_policy(
            "simkl",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://simkl.com/about/policies/terms/",
            allowed_uses=runtime_uses,
        ),
        _source_policy(
            "trakt",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://trakt.docs.apiary.io/",
            allowed_uses=runtime_uses,
        ),
        _source_policy(
            "omdb",
            SourceRole.LOCAL_EVIDENCE,
            terms_url="https://www.omdbapi.com/legal.htm",
            allowed_uses=runtime_uses,
        ),
        _source_policy(
            "justwatch",
            SourceRole.RUNTIME_ONLY,
            terms_url="https://support.justwatch.com/hc/en-us/articles/9567105189405-JustWatch-s-Terms-of-Use",
            allowed_uses=runtime_uses,
        ),
        _source_policy(
            "paid_experiment_fixture",
            SourceRole.PAID_EXPERIMENT_ONLY,
            terms_url="https://example.invalid/paid-contract",
            allowed_uses=[PublishableUse.LOCAL_MATCHING, PublishableUse.QA],
        ),
        _source_policy(
            "anime_planet",
            SourceRole.BLOCKED,
            terms_url="https://www.anime-planet.com/termsofuse",
            allowed_uses=blocked_uses,
        ),
    ]
    return {policy.source_id: policy for policy in policies}


def _default_field_policies() -> dict[str, SourceFieldPolicy]:
    source_policies = _default_source_policies()
    policies: list[SourceFieldPolicy] = []

    public_fields = [
        "canonical_source",
        "creators",
        "domain",
        "entity_id",
        "episodes",
        "genres",
        "media_type",
        "original_title",
        "record_source",
        "release_year",
        "sources",
        "source_role",
        "status",
        "studios",
        "synonyms",
        "tags",
        "title",
        "relationship",
        "relationship_confidence",
        "relationship_id",
        "relationship_type",
        "relationship_family",
        "direction",
        "inverse_relationship_type",
        "confidence_tier",
        "evidence_count",
        "conflict_status",
        "quality_flags",
        "evidence_id",
        "provenance_id",
        "recipe_version",
        "relationship_confidence_score",
        "confidence_profile_json",
        "source_entity_id",
        "supporting_provider_count",
        "supporting_source_count",
        "supporting_urls",
        "target_entity_id",
        "target_url",
    ]
    public_uses = [
        PublishableUse.PUBLIC_PARQUET,
        PublishableUse.PUBLIC_MANIFEST,
        PublishableUse.LOCAL_MATCHING,
        PublishableUse.QA,
    ]
    retrieval_fields = {
        "creators",
        "genres",
        "media_type",
        "original_title",
        "release_year",
        "status",
        "studios",
        "synonyms",
        "tags",
        "title",
    }
    llm_judgment_fields = {
        *retrieval_fields,
        "relationship",
        "relationship_confidence",
        "relationship_type",
        "relationship_confidence_score",
        "supporting_provider_count",
        "supporting_source_count",
        "supporting_urls",
    }
    id_fields = ["entity_id", "source_entity_id", "target_entity_id", "sources", "target_url"]
    id_uses = [
        PublishableUse.PUBLIC_PARQUET,
        PublishableUse.PUBLIC_MANIFEST,
        PublishableUse.LOCAL_MATCHING,
        PublishableUse.QA,
    ]

    for source_id, policy in source_policies.items():
        if policy.source_role == SourceRole.BACKBONE_SOURCE:
            for field_name in public_fields:
                allowed_uses = list(public_uses)
                if field_name in retrieval_fields:
                    allowed_uses.extend(
                        [PublishableUse.RETRIEVAL_TEXT, PublishableUse.EMBEDDING_INPUT]
                    )
                if field_name in llm_judgment_fields:
                    allowed_uses.append(PublishableUse.LLM_JUDGMENT_INPUT)
                policies.append(
                    _field_policy(
                        source_id,
                        field_name,
                        PublishabilityClass.PUBLIC_METADATA,
                        allowed_uses=list(dict.fromkeys(allowed_uses)),
                    )
                )
        elif policy.source_role == SourceRole.ID_SOURCE:
            for field_name in id_fields:
                policies.append(
                    _field_policy(
                        source_id,
                        field_name,
                        PublishabilityClass.PUBLIC_IDENTIFIER,
                        allowed_uses=id_uses,
                    )
                )
        elif policy.source_role == SourceRole.LOCAL_EVIDENCE:
            for field_name in public_fields:
                policies.append(
                    _field_policy(
                        source_id,
                        field_name,
                        PublishabilityClass.LOCAL_ONLY,
                        allowed_uses=[PublishableUse.LOCAL_MATCHING, PublishableUse.QA],
                    )
                )
        elif policy.source_role == SourceRole.RUNTIME_ONLY:
            for field_name in public_fields:
                policies.append(
                    _field_policy(
                        source_id,
                        field_name,
                        PublishabilityClass.RUNTIME_ONLY,
                        allowed_uses=[PublishableUse.LOCAL_MATCHING, PublishableUse.QA],
                    )
                )
        elif policy.source_role == SourceRole.PAID_EXPERIMENT_ONLY:
            for field_name in public_fields:
                policies.append(
                    _field_policy(
                        source_id,
                        field_name,
                        PublishabilityClass.PAID_EXPERIMENT_ONLY,
                        allowed_uses=[PublishableUse.LOCAL_MATCHING, PublishableUse.QA],
                    )
                )
        else:
            for field_name in public_fields:
                policies.append(
                    _field_policy(
                        source_id,
                        field_name,
                        PublishabilityClass.BLOCKED,
                        allowed_uses=[],
                    )
                )

    return {
        PublishabilityPolicyCatalog.field_key(policy.source_id, policy.field_name): policy
        for policy in policies
    }


def _default_artifact_policies() -> dict[str, ArtifactPolicy]:
    public_classes = [
        PublishabilityClass.PUBLIC_METADATA,
        PublishabilityClass.PUBLIC_IDENTIFIER,
        PublishabilityClass.PUBLIC_DERIVED,
    ]
    public_table_uses = [PublishableUse.PUBLIC_PARQUET, PublishableUse.PUBLIC_MANIFEST]
    bootstrap_entity_columns = [
        "canonical_source",
        "creators",
        "domain",
        "entity_id",
        "episodes",
        "field_sources_json",
        "genres",
        "media_type",
        "original_title",
        "record_source",
        "release_year",
        "sources",
        "source_role",
        "status",
        "studios",
        "synonyms",
        "tags",
        "title",
    ]
    bootstrap_relationship_columns = [
        "relationship",
        "relationship_confidence",
        "relationship_id",
        "relationship_type",
        "relationship_family",
        "direction",
        "inverse_relationship_type",
        "confidence_tier",
        "evidence_count",
        "conflict_status",
        "quality_flags",
        "evidence_id",
        "provenance_id",
        "recipe_version",
        "relationship_confidence_score",
        "confidence_profile_json",
        "source_entity_id",
        "supporting_provider_count",
        "supporting_source_count",
        "supporting_urls",
        "target_entity_id",
        "target_url",
    ]
    policies: list[ArtifactPolicy] = []
    for column in bootstrap_entity_columns:
        policies.append(
            _artifact_policy(
                "bootstrap-corpus",
                "entities",
                column,
                allowed_input_classes=public_classes,
                allowed_uses=public_table_uses,
                validation_rule="public entity columns require public metadata/id/derived inputs",
            )
        )
    for column in bootstrap_relationship_columns:
        policies.append(
            _artifact_policy(
                "bootstrap-corpus",
                "relationships",
                column,
                allowed_input_classes=public_classes,
                allowed_uses=public_table_uses,
                validation_rule="public relationship columns require public metadata/id/derived inputs",
            )
        )
    for column in ["domain", "entity_id", "source_role", "title"]:
        policies.append(
            _artifact_policy(
                "keyless-smoke",
                "entities",
                column,
                allowed_input_classes=public_classes,
                allowed_uses=[PublishableUse.PUBLIC_PARQUET, PublishableUse.PUBLIC_MANIFEST],
                validation_rule="smoke artifact columns require public fixture inputs",
            )
        )
    for column in ["text"]:
        policies.append(
            _artifact_policy(
                "retrieval-text",
                "retrieval_text",
                column,
                allowed_input_classes=public_classes,
                allowed_uses=[PublishableUse.RETRIEVAL_TEXT, PublishableUse.EMBEDDING_INPUT],
                validation_rule="retrieval and embedding text must use public-safe inputs",
            )
        )
    for column in ["prompt"]:
        policies.append(
            _artifact_policy(
                "llm-judgment",
                "llm_judgments",
                column,
                allowed_input_classes=public_classes,
                allowed_uses=[PublishableUse.LLM_JUDGMENT_INPUT],
                validation_rule="LLM judgment prompts must use public-safe inputs only",
            )
        )

    return {
        PublishabilityPolicyCatalog.artifact_key(policy.artifact, policy.table, policy.column): policy
        for policy in policies
    }


def default_policy_catalog() -> PublishabilityPolicyCatalog:
    return PublishabilityPolicyCatalog(
        source_policies=_default_source_policies(),
        source_field_policies=_default_field_policies(),
        artifact_policies=_default_artifact_policies(),
    )
