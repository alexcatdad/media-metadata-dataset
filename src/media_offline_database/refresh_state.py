from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

REFRESH_STATE_SCHEMA = "media-offline-dataset.refresh-state"
REFRESH_STATE_SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class RefreshJobState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    snapshot_id: str
    status: Literal["in_progress", "completed"]
    batch_size: int
    completed_count: int
    next_offset: int
    last_completed_item_key: str | None = None
    last_checkpoint_path: str | None = None
    published_snapshot_path: str | None = None
    published_snapshot_manifest_path: str | None = None
    current_snapshot_path: str | None = None
    current_snapshot_manifest_path: str | None = None
    finalized_at: str | None = None
    updated_at: str = Field(default_factory=_utc_now)


class RefreshState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_schema: str = REFRESH_STATE_SCHEMA
    schema_version: int = REFRESH_STATE_SCHEMA_VERSION
    jobs: dict[str, RefreshJobState] = Field(default_factory=dict)


def load_refresh_state(path: Path) -> RefreshState:
    if not path.exists():
        return RefreshState()
    return RefreshState.model_validate_json(path.read_text(encoding="utf-8"))


def write_refresh_state(path: Path, state: RefreshState) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def next_refresh_offset(
    state: RefreshState,
    *,
    job_name: str,
    snapshot_id: str,
) -> int:
    job = state.jobs.get(job_name)
    if job is None or job.snapshot_id != snapshot_id:
        return 0
    return job.next_offset


def record_refresh_progress(
    state: RefreshState,
    *,
    job_name: str,
    source_name: str,
    snapshot_id: str,
    batch_size: int,
    completed_count: int,
    next_offset: int,
    status: Literal["in_progress", "completed"],
    last_completed_item_key: str | None,
    last_checkpoint_path: str | None,
) -> RefreshState:
    state.jobs[job_name] = RefreshJobState(
        source_name=source_name,
        snapshot_id=snapshot_id,
        status=status,
        batch_size=batch_size,
        completed_count=completed_count,
        next_offset=next_offset,
        last_completed_item_key=last_completed_item_key,
        last_checkpoint_path=last_checkpoint_path,
    )
    return state


def record_refresh_finalization(
    state: RefreshState,
    *,
    job_name: str,
    snapshot_id: str,
    snapshot_path: str,
    snapshot_manifest_path: str,
    current_path: str,
    current_manifest_path: str,
) -> RefreshState:
    existing = state.jobs.get(job_name)
    if existing is None:
        state.jobs[job_name] = RefreshJobState(
            source_name="finalize",
            snapshot_id=snapshot_id,
            status="completed",
            batch_size=0,
            completed_count=0,
            next_offset=0,
            published_snapshot_path=snapshot_path,
            published_snapshot_manifest_path=snapshot_manifest_path,
            current_snapshot_path=current_path,
            current_snapshot_manifest_path=current_manifest_path,
            finalized_at=_utc_now(),
        )
        return state

    state.jobs[job_name] = existing.model_copy(
        update={
            "snapshot_id": snapshot_id,
            "status": "completed",
            "published_snapshot_path": snapshot_path,
            "published_snapshot_manifest_path": snapshot_manifest_path,
            "current_snapshot_path": current_path,
            "current_snapshot_manifest_path": current_manifest_path,
            "finalized_at": _utc_now(),
        }
    )
    return state
