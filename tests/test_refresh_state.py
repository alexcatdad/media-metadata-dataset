from __future__ import annotations

import json
from pathlib import Path

from media_offline_database.refresh_state import (
    REFRESH_STATE_SCHEMA,
    REFRESH_STATE_SCHEMA_VERSION,
    RefreshState,
    load_refresh_state,
    next_refresh_offset,
    record_refresh_finalization,
    record_refresh_progress,
    write_refresh_state,
)


def test_refresh_state_defaults_when_missing(tmp_path: Path) -> None:
    state = load_refresh_state(tmp_path / "missing.json")

    assert state.state_schema == REFRESH_STATE_SCHEMA
    assert state.schema_version == REFRESH_STATE_SCHEMA_VERSION
    assert state.jobs == {}


def test_record_refresh_progress_round_trips(tmp_path: Path) -> None:
    state = RefreshState()
    record_refresh_progress(
        state,
        job_name="anime.manami.default",
        source_name="manami",
        snapshot_id="2026-14",
        batch_size=100,
        completed_count=500,
        next_offset=500,
        status="in_progress",
        last_completed_item_key="anime:manami:anidb:12681",
        last_checkpoint_path="checkpoints/anime.manami.default/2026-14/00000000-00000500",
    )
    path = write_refresh_state(tmp_path / "state" / "refresh-state.json", state)

    reloaded = load_refresh_state(path)
    job = reloaded.jobs["anime.manami.default"]

    assert job.source_name == "manami"
    assert job.snapshot_id == "2026-14"
    assert job.batch_size == 100
    assert job.completed_count == 500
    assert job.next_offset == 500
    assert job.last_completed_item_key == "anime:manami:anidb:12681"
    assert next_refresh_offset(
        reloaded,
        job_name="anime.manami.default",
        snapshot_id="2026-14",
    ) == 500
    assert next_refresh_offset(
        reloaded,
        job_name="anime.manami.default",
        snapshot_id="2026-15",
    ) == 0

    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed["state_schema"] == REFRESH_STATE_SCHEMA


def test_record_refresh_finalization_marks_current_snapshot(tmp_path: Path) -> None:
    state = RefreshState()
    record_refresh_progress(
        state,
        job_name="anime.manami.default",
        source_name="manami",
        snapshot_id="2026-14",
        batch_size=100,
        completed_count=500,
        next_offset=500,
        status="in_progress",
        last_completed_item_key="anime:manami:anidb:12681",
        last_checkpoint_path="checkpoints/anime.manami.default/2026-14/00000000-00000500",
    )
    record_refresh_finalization(
        state,
        job_name="anime.manami.default",
        snapshot_id="2026-14",
        snapshot_path="snapshots/anime.manami.default/2026-14",
        snapshot_manifest_path="snapshots/anime.manami.default/2026-14/sample-manifest.json",
        current_path="current/anime.manami.default",
        current_manifest_path="current/anime.manami.default/sample-manifest.json",
    )

    path = write_refresh_state(tmp_path / "state" / "refresh-state.json", state)
    reloaded = load_refresh_state(path)
    job = reloaded.jobs["anime.manami.default"]

    assert job.status == "completed"
    assert job.published_snapshot_path == "snapshots/anime.manami.default/2026-14"
    assert job.current_snapshot_path == "current/anime.manami.default"
    assert job.current_snapshot_manifest_path == (
        "current/anime.manami.default/sample-manifest.json"
    )
    assert job.finalized_at is not None
