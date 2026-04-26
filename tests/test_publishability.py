from __future__ import annotations

import json
from pathlib import Path

import pytest

from media_offline_database.bootstrap import BootstrapEntity, write_bootstrap_corpus_artifact
from media_offline_database.hf_publish import build_publish_bundle
from media_offline_database.publishability import (
    CURRENT_POLICY_VERSIONS,
    ArtifactInput,
    PublishabilityError,
    PublishableUse,
    SourceFieldReference,
    SourcePolicy,
    validate_artifact_inputs,
    validate_current_manifest_publishability,
    validate_manifest_publishability,
    validate_text_inputs,
)
from media_offline_database.sources import SourceRole


def test_public_artifact_rejects_missing_source_field_policy() -> None:
    with pytest.raises(PublishabilityError, match="missing source field policy"):
        validate_artifact_inputs(
            [
                ArtifactInput(
                    artifact="bootstrap-corpus",
                    table="entities",
                    column="title",
                    source_fields=[
                        SourceFieldReference(
                            source_id="bootstrap_seed",
                            field_name="unreviewed_title",
                        )
                    ],
                    use=PublishableUse.PUBLIC_PARQUET,
                )
            ]
        )


def test_source_policy_requires_terms_or_license_evidence() -> None:
    with pytest.raises(ValueError, match="license_url or terms_url"):
        SourcePolicy(
            source_id="credential_only",
            source_role=SourceRole.LOCAL_EVIDENCE,
            reviewed_at="2026-04-26",
            attribution_required="none",
            cache_limits="local only",
            allowed_uses=[PublishableUse.LOCAL_MATCHING],
            retention_rules="do not publish",
        )


def test_public_artifact_rejects_restricted_source_inputs() -> None:
    with pytest.raises(PublishabilityError, match=r"tmdb_api\.title"):
        validate_artifact_inputs(
            [
                ArtifactInput(
                    artifact="bootstrap-corpus",
                    table="entities",
                    column="title",
                    source_fields=[
                        SourceFieldReference(source_id="tmdb_api", field_name="title")
                    ],
                    use=PublishableUse.PUBLIC_PARQUET,
                )
            ]
        )


def test_retrieval_and_embedding_inputs_reject_local_only_values() -> None:
    with pytest.raises(PublishabilityError, match=r"anilist\.title"):
        validate_text_inputs(
            [SourceFieldReference(source_id="anilist", field_name="title")],
            artifact="retrieval-text",
            table="retrieval_text",
            column="text",
            use=PublishableUse.RETRIEVAL_TEXT,
        )

    with pytest.raises(PublishabilityError, match=r"anilist\.title"):
        validate_text_inputs(
            [SourceFieldReference(source_id="anilist", field_name="title")],
            artifact="retrieval-text",
            table="retrieval_text",
            column="text",
            use=PublishableUse.EMBEDDING_INPUT,
        )


def test_field_policy_is_authority_for_model_facing_uses() -> None:
    validate_text_inputs(
        [SourceFieldReference(source_id="bootstrap_seed", field_name="title")],
        artifact="retrieval-text",
        table="retrieval_text",
        column="text",
        use=PublishableUse.RETRIEVAL_TEXT,
    )

    with pytest.raises(PublishabilityError, match="canonical_source field policy"):
        validate_text_inputs(
            [SourceFieldReference(source_id="bootstrap_seed", field_name="canonical_source")],
            artifact="retrieval-text",
            table="retrieval_text",
            column="text",
            use=PublishableUse.EMBEDDING_INPUT,
        )


def test_bootstrap_artifact_manifest_records_publishability_versions(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.jsonl"
    seed_path.write_text(
        BootstrapEntity(
            entity_id="anime:test:1",
            domain="anime",
            canonical_source="https://example.invalid/anime/1",
            source_role=SourceRole.BACKBONE_SOURCE,
            record_source="bootstrap test",
            title="Policy Test",
            media_type="TV",
            status="FINISHED",
            release_year=2026,
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )

    manifest_path = write_bootstrap_corpus_artifact(
        input_path=seed_path,
        output_dir=tmp_path / "compiled",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["publishability"]["policy_versions"] == {
        "artifact_policy": "artifact-policy-v1",
        "publishability_policy": "publishability-policy-v1",
        "source_field_policy": "source-field-policy-v1",
        "source_policy": "source-policy-v1",
    }
    assert "PUBLIC_PARQUET" in manifest["publishability"]["validated_uses"]
    assert "PUBLIC_MANIFEST" in manifest["publishability"]["validated_uses"]


def test_manifest_publishability_can_use_explicit_compatibility_registry() -> None:
    historical_versions = {
        "artifact_policy": "artifact-policy-v0",
        "publishability_policy": "publishability-policy-v0",
        "source_field_policy": "source-field-policy-v0",
        "source_policy": "source-policy-v0",
    }
    manifest = {
        "publishability": {
            "policy_versions": historical_versions,
            "validated_uses": ["PUBLIC_MANIFEST"],
        }
    }

    validate_manifest_publishability(
        manifest,
        compatible_policy_versions=(historical_versions,),
    )

    with pytest.raises(PublishabilityError, match="compatibility registry"):
        validate_current_manifest_publishability(manifest)


def test_current_manifest_publishability_requires_current_policy_versions() -> None:
    manifest = {
        "publishability": {
            "policy_versions": CURRENT_POLICY_VERSIONS,
            "validated_uses": ["PUBLIC_MANIFEST"],
        }
    }

    validate_current_manifest_publishability(manifest)


def test_bootstrap_writer_rejects_restricted_public_artifact_inputs(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.jsonl"
    seed_path.write_text(
        BootstrapEntity(
            entity_id="anime:test:1",
            domain="anime",
            canonical_source="https://example.invalid/anime/1",
            source_role=SourceRole.BACKBONE_SOURCE,
            record_source="bootstrap test",
            title="Policy Test",
            media_type="TV",
            status="FINISHED",
            release_year=2026,
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PublishabilityError, match=r"tmdb_api\.title"):
        write_bootstrap_corpus_artifact(
            input_path=seed_path,
            output_dir=tmp_path / "compiled",
            policy_inputs=[
                ArtifactInput(
                    artifact="bootstrap-corpus",
                    table="entities",
                    column="title",
                    source_fields=[
                        SourceFieldReference(source_id="tmdb_api", field_name="title")
                    ],
                    use=PublishableUse.PUBLIC_PARQUET,
                )
            ],
        )


def test_release_bundle_rejects_manifest_without_publishability_policy(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "compiled"
    artifact_dir.mkdir()
    parquet_path = artifact_dir / "sample.parquet"
    parquet_path.write_bytes(b"not-real-parquet-for-bundle-test")
    manifest_path = artifact_dir / "sample-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "artifact": "bootstrap-corpus",
                "files": [{"path": parquet_path.name, "kind": "entities"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PublishabilityError, match="missing publishability"):
        build_publish_bundle(manifest_path)
