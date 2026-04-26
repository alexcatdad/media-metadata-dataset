from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from media_offline_database.contracts import (
    ALL_TABLE_CONTRACTS,
    CORE_SCHEMA_VERSION,
    CORE_TABLE_CONTRACTS,
    IDENTITY_CHANGES_CONTRACT,
    PROFILE_TABLE_CONTRACTS,
    ArtifactManifest,
    CompatibilityTier,
    IdentityChangeRecord,
    IdentityChangeType,
    PolicyVersions,
    PublishedArtifactManifest,
    resolve_identity_forward,
)


def _policy_versions() -> PolicyVersions:
    return PolicyVersions(
        source_policy_version="source-policy.v1",
        field_policy_version="field-policy.v1",
        artifact_policy_version="artifact-policy.v1",
        publishability_validation_version="publishability.v1",
    )


def _manifest_payload() -> dict[str, Any]:
    policy_versions = _policy_versions().model_dump(mode="json")
    return {
        "dataset_line": "media-metadata-v1",
        "dataset_version": "0.1.0",
        "core_schema_version": CORE_SCHEMA_VERSION,
        "hf_repo_id": "alexcatdad/media-metadata-dataset",
        "hf_commit_sha": "a" * 40,
        "hf_revision": "refs/tags/v0.1.0",
        "published_at": datetime(2026, 4, 26, tzinfo=UTC).isoformat(),
        "policy_versions": policy_versions,
        "recipe_versions": {
            "identity_normalization": "identity-normalization.v1",
            "confidence_core": "confidence-core.v1",
        },
        "confidence_recipe_versions": {
            "core": "confidence-core.v1",
            "relationships": "confidence-relationships.v1",
        },
        "enrichment_status": {
            "snapshot": "source-ingested",
            "facets": "pending",
            "embeddings": "missing",
        },
        "source_coverage": [
            {
                "source_id": "manami",
                "source_role": "BACKBONE_SOURCE",
                "source_snapshot_id": "source-snapshot:manami:2026-04-26",
                "domains": ["anime"],
                "record_count": 2,
            }
        ],
        "compatibility_notices": [
            {
                "notice_id": "initial-core-v1",
                "tier": "core",
                "severity": "info",
                "message": "Initial core schema contract.",
            }
        ],
        "tables": [
            {
                "table_name": "entities",
                "path": "tables/entities.parquet",
                "format": "parquet",
                "row_count": 2,
                "schema_version": CORE_SCHEMA_VERSION,
                "compatibility_tier": "core",
                "policy_versions": policy_versions,
                "recipe_versions": {"identity_normalization": "identity-normalization.v1"},
                "enrichment_status": "source-ingested",
            }
        ],
    }


def test_manifest_accepts_required_publish_contract_fields() -> None:
    manifest = PublishedArtifactManifest.model_validate(_manifest_payload())

    assert manifest.hf_repo_id == "alexcatdad/media-metadata-dataset"
    assert manifest.hf_commit_sha == "a" * 40
    assert manifest.tables[0].path == "tables/entities.parquet"
    assert manifest.tables[0].schema_version == CORE_SCHEMA_VERSION
    assert manifest.tables[0].policy_versions.artifact_policy_version == "artifact-policy.v1"
    assert manifest.recipe_versions["confidence_core"] == "confidence-core.v1"


@pytest.mark.parametrize(
    "missing_field",
    [
        "hf_repo_id",
        "core_schema_version",
        "policy_versions",
        "recipe_versions",
        "tables",
    ],
)
def test_manifest_rejects_missing_required_top_level_fields(missing_field: str) -> None:
    payload = _manifest_payload()
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        ArtifactManifest.model_validate(payload)


def test_draft_manifest_allows_missing_publish_revision_until_finalize() -> None:
    payload = _manifest_payload()
    payload.pop("hf_commit_sha")
    payload.pop("hf_revision")
    payload.pop("published_at")

    manifest = ArtifactManifest.model_validate(payload)

    assert manifest.hf_repo_id == "alexcatdad/media-metadata-dataset"
    assert manifest.hf_commit_sha is None
    assert manifest.hf_revision is None
    assert manifest.published_at is None


@pytest.mark.parametrize("missing_publish_field", ["hf_commit_sha", "hf_revision", "published_at"])
def test_published_manifest_requires_publish_revision_identity(missing_publish_field: str) -> None:
    payload = _manifest_payload()
    payload.pop(missing_publish_field)

    with pytest.raises(ValidationError):
        PublishedArtifactManifest.model_validate(payload)


@pytest.mark.parametrize("bad_path", ["/tmp/entities.parquet", "../entities.parquet", "entities.csv"])
def test_manifest_rejects_non_portable_or_non_parquet_paths(bad_path: str) -> None:
    payload = _manifest_payload()
    payload["tables"][0]["path"] = bad_path

    with pytest.raises(ValidationError):
        ArtifactManifest.model_validate(payload)


def test_manifest_rejects_duplicate_table_names() -> None:
    payload = _manifest_payload()
    payload["tables"].append(dict(payload["tables"][0]))

    with pytest.raises(ValidationError):
        ArtifactManifest.model_validate(payload)


def test_core_table_contracts_cover_required_public_surfaces() -> None:
    required_tables = {
        "entities",
        "titles",
        "external_ids",
        "relationships",
        "relationship_evidence",
        "facets",
        "judgments",
        "provenance",
        "source_records",
    }

    assert required_tables <= CORE_TABLE_CONTRACTS.keys()
    for table_name in required_tables:
        contract = CORE_TABLE_CONTRACTS[table_name]
        assert contract.schema_version == CORE_SCHEMA_VERSION
        assert contract.compatibility_tier in {CompatibilityTier.CORE, CompatibilityTier.DERIVED}
        assert "recipe_version" in contract.required_column_names or table_name == "provenance"


def test_core_contracts_expose_lightweight_trust_signals() -> None:
    entities = CORE_TABLE_CONTRACTS["entities"].required_column_names
    relationships = CORE_TABLE_CONTRACTS["relationships"].required_column_names

    for required in {
        "confidence_tier",
        "evidence_count",
        "conflict_status",
        "quality_flags",
        "recipe_version",
    }:
        assert required in entities
        assert required in relationships
    assert "field_level_provenance" not in entities
    assert "field_level_provenance" not in relationships


def test_profile_contracts_are_independently_versioned() -> None:
    assert set(PROFILE_TABLE_CONTRACTS) == {"anime_profile", "tv_profile", "movie_profile"}

    for table_name, contract in PROFILE_TABLE_CONTRACTS.items():
        assert contract.compatibility_tier == CompatibilityTier.PROFILE
        assert contract.schema_version == f"{table_name}.v1"
        assert "profile_schema_version" in contract.required_column_names
        assert "entity_id" in contract.required_column_names

    anime_columns = PROFILE_TABLE_CONTRACTS["anime_profile"].required_column_names
    tv_columns = PROFILE_TABLE_CONTRACTS["tv_profile"].required_column_names
    movie_columns = PROFILE_TABLE_CONTRACTS["movie_profile"].required_column_names
    assert "anime_format" in anime_columns
    assert "season_count" in tv_columns
    assert "runtime_minutes" in movie_columns


def test_identity_changes_contract_has_migration_fields() -> None:
    required = IDENTITY_CHANGES_CONTRACT.required_column_names

    assert IDENTITY_CHANGES_CONTRACT.table_name in ALL_TABLE_CONTRACTS
    for column_name in {
        "identity_change_id",
        "change_type",
        "old_entity_id",
        "new_entity_ids",
        "reason",
        "effective_snapshot_id",
        "provenance_id",
        "confidence_tier",
        "quality_flags",
        "recipe_version",
    }:
        assert column_name in required


def _identity_change(
    *,
    change_id: str,
    change_type: IdentityChangeType,
    old_entity_id: str,
    new_entity_ids: list[str],
) -> IdentityChangeRecord:
    return IdentityChangeRecord(
        identity_change_id=change_id,
        change_type=change_type,
        old_entity_id=old_entity_id,
        new_entity_ids=new_entity_ids,
        reason="Identity correction.",
        evidence_id="evidence:1",
        effective_snapshot_id="snapshot:2026-04-26",
        provenance_id="provenance:1",
        recipe_version="identity-change.v1",
    )


def test_identity_change_records_resolve_old_ids_forward() -> None:
    change = _identity_change(
        change_id="identity-change:1",
        change_type=IdentityChangeType.REDIRECT,
        old_entity_id="entity:old",
        new_entity_ids=["entity:new"],
    )

    assert resolve_identity_forward("entity:old", [change]) == ["entity:new"]
    assert resolve_identity_forward("entity:current", [change]) == ["entity:current"]


def test_identity_resolution_walks_transitive_changes_and_splits() -> None:
    changes = [
        _identity_change(
            change_id="identity-change:1",
            change_type=IdentityChangeType.REDIRECT,
            old_entity_id="entity:a",
            new_entity_ids=["entity:b"],
        ),
        _identity_change(
            change_id="identity-change:2",
            change_type=IdentityChangeType.SUPERSESSION,
            old_entity_id="entity:b",
            new_entity_ids=["entity:c"],
        ),
        _identity_change(
            change_id="identity-change:3",
            change_type=IdentityChangeType.SPLIT,
            old_entity_id="entity:split",
            new_entity_ids=["entity:a", "entity:d"],
        ),
    ]

    assert resolve_identity_forward("entity:a", changes) == ["entity:c"]
    assert resolve_identity_forward("entity:split", changes) == ["entity:c", "entity:d"]


def test_identity_resolution_detects_cycles() -> None:
    changes = [
        _identity_change(
            change_id="identity-change:1",
            change_type=IdentityChangeType.REDIRECT,
            old_entity_id="entity:a",
            new_entity_ids=["entity:b"],
        ),
        _identity_change(
            change_id="identity-change:2",
            change_type=IdentityChangeType.REDIRECT,
            old_entity_id="entity:b",
            new_entity_ids=["entity:a"],
        ),
    ]

    with pytest.raises(ValueError, match="cycle"):
        resolve_identity_forward("entity:a", changes)


def test_identity_change_records_reject_id_reuse_and_invalid_splits() -> None:
    with pytest.raises(ValidationError):
        IdentityChangeRecord(
            identity_change_id="identity-change:self",
            change_type=IdentityChangeType.REDIRECT,
            old_entity_id="entity:old",
            new_entity_ids=["entity:old"],
            reason="Invalid self redirect.",
            effective_snapshot_id="snapshot:2026-04-26",
            provenance_id="provenance:1",
            recipe_version="identity-change.v1",
        )

    with pytest.raises(ValidationError):
        IdentityChangeRecord(
            identity_change_id="identity-change:split",
            change_type=IdentityChangeType.SPLIT,
            old_entity_id="entity:old",
            new_entity_ids=["entity:new"],
            reason="Split needs at least two minted IDs.",
            effective_snapshot_id="snapshot:2026-04-26",
            provenance_id="provenance:1",
            recipe_version="identity-change.v1",
        )
