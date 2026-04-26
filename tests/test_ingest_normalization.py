from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from media_offline_database.ingest_normalization import (
    MediaDomain,
    ProviderRun,
    ProvisionalSourcePathFieldClass,
    SourcePathStatus,
    SourceRecordRef,
    SourceSnapshot,
    source_path_plan_by_domain,
)
from media_offline_database.sources import SourceRole


def test_v1_source_path_plan_names_distinct_non_anime_tv_and_movie_paths() -> None:
    plan = source_path_plan_by_domain()

    assert set(plan) == {MediaDomain.ANIME, MediaDomain.TV, MediaDomain.MOVIE}
    assert plan[MediaDomain.TV].source_id == "tvmaze"
    assert plan[MediaDomain.MOVIE].source_id == "wikidata"
    assert "anime" not in plan[MediaDomain.TV].source_id
    assert "anime" not in plan[MediaDomain.MOVIE].source_id
    assert "anime" in plan[MediaDomain.MOVIE].notes.lower()
    assert plan[MediaDomain.TV].status == SourcePathStatus.EXECUTABLE_MILESTONE
    assert plan[MediaDomain.MOVIE].status == SourcePathStatus.EXECUTABLE_MILESTONE
    assert plan[MediaDomain.MOVIE].provider_review_todos


def test_tv_and_movie_paths_keep_publishable_and_restricted_fields_explicit() -> None:
    plan = source_path_plan_by_domain()
    tv_path = plan[MediaDomain.TV]
    movie_path = plan[MediaDomain.MOVIE]

    assert "name" in tv_path.publishable_fields
    assert "summary_html" in tv_path.restricted_fields
    assert "wikidata_qid" in movie_path.publishable_fields
    assert movie_path.restricted_fields == ()


def test_source_snapshot_rejects_inverted_fetch_window() -> None:
    with pytest.raises(ValidationError):
        SourceSnapshot(
            source_snapshot_id="tvmaze:bad-window",
            source_id="tvmaze",
            source_role=SourceRole.BACKBONE_SOURCE,
            snapshot_kind="incremental_api_window",
            fetched_at=datetime(2026, 4, 26, tzinfo=UTC),
            fetch_window_started_at=datetime(2026, 4, 27, tzinfo=UTC),
            fetch_window_finished_at=datetime(2026, 4, 26, tzinfo=UTC),
            policy_version="source-policy-v1",
            publishable_field_policy_version="source-field-policy-v1",
            artifact_policy_version="artifact-policy-v1",
        )


def test_provider_run_metadata_does_not_accept_secret_values() -> None:
    with pytest.raises(ValidationError):
        ProviderRun(
            provider_run_id="run-1",
            source_id="tmdb_api",
            adapter_name="tmdb",
            adapter_version="v1",
            started_at=datetime(2026, 4, 26, tzinfo=UTC),
            status="blocked",
            auth_shape="bearer",
            secret_refs=("token=leaked",),
        )


def test_source_record_ref_requires_snapshot_or_provider_run() -> None:
    with pytest.raises(ValidationError):
        SourceRecordRef(
            source_record_ref_id="record-ref-1",
            source_id="tvmaze",
            source_record_id="82",
            source_role=SourceRole.BACKBONE_SOURCE,
            provisional_source_path_field_class=ProvisionalSourcePathFieldClass.PUBLIC_ID,
        )
