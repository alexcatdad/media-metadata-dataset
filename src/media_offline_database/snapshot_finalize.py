from __future__ import annotations

import json
import shutil
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from media_offline_database.hf_publish import (
    HF_REFRESH_STATE_PATH,
    HfApiLike,
    build_publish_bundle,
    create_release_tag,
    extract_hf_commit_sha,
    write_hf_dataset_card,
)
from media_offline_database.refresh_state import RefreshState, record_refresh_finalization


class SnapshotFinalizeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_id: str | None = None
    snapshot_path: str
    snapshot_manifest_path: str
    current_path: str
    current_manifest_path: str
    state_path: str | None = None
    commit_sha: str | None = None
    bundle_commit_sha: str | None = None
    commit_url: str | None = None
    release_tag: str | None = None


def _copy_bundle_to_path(*, manifest_path: Path, destination_dir: Path) -> Path:
    bundle = build_publish_bundle(manifest_path)
    destination_dir.mkdir(parents=True, exist_ok=True)
    for pattern in bundle.allow_patterns:
        source_path = bundle.local_dir / pattern
        if not source_path.exists():
            raise FileNotFoundError(f"bundle path missing for finalize copy: {source_path}")
        destination_path = destination_dir / pattern
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
    return destination_dir / manifest_path.name


def materialize_current_snapshot(
    *,
    manifest_path: Path,
    output_dir: Path,
    job_name: str,
    snapshot_id: str,
    snapshot_prefix: str = "snapshots",
    current_prefix: str = "current",
) -> SnapshotFinalizeResult:
    snapshot_path = f"{snapshot_prefix}/{job_name}/{snapshot_id}"
    current_path = f"{current_prefix}/{job_name}"

    snapshot_manifest_path = _copy_bundle_to_path(
        manifest_path=manifest_path,
        destination_dir=output_dir / snapshot_path,
    )
    current_manifest_path = _copy_bundle_to_path(
        manifest_path=manifest_path,
        destination_dir=output_dir / current_path,
    )

    return SnapshotFinalizeResult(
        snapshot_path=snapshot_path,
        snapshot_manifest_path=str(snapshot_manifest_path),
        current_path=current_path,
        current_manifest_path=str(current_manifest_path),
    )


def publish_current_snapshot(
    *,
    api: HfApiLike,
    token: str,
    repo_id: str,
    manifest_path: Path,
    state: RefreshState,
    job_name: str,
    snapshot_id: str,
    private: bool = True,
    write_dataset_card: bool = True,
    snapshot_prefix: str = "snapshots",
    current_prefix: str = "current",
    release_tag: str | None = None,
) -> SnapshotFinalizeResult:
    bundle = build_publish_bundle(manifest_path)
    api.create_repo(
        repo_id,
        token=token,
        private=private,
        repo_type="dataset",
        exist_ok=True,
    )
    if write_dataset_card:
        write_hf_dataset_card(
            repo_id=repo_id,
            api=api,
            token=token,
            title=repo_id.split("/")[-1],
            private=private,
        )

    snapshot_path = f"{snapshot_prefix}/{job_name}/{snapshot_id}"
    current_path = f"{current_prefix}/{job_name}"
    snapshot_manifest_path = f"{snapshot_path}/{manifest_path.name}"
    current_manifest_path = f"{current_path}/{manifest_path.name}"

    snapshot_commit = api.upload_folder(
        repo_id=repo_id,
        folder_path=bundle.local_dir,
        path_in_repo=snapshot_path,
        commit_message=f"Publish snapshot {snapshot_path}",
        token=token,
        repo_type="dataset",
        allow_patterns=bundle.allow_patterns,
    )
    current_commit = api.upload_folder(
        repo_id=repo_id,
        folder_path=bundle.local_dir,
        path_in_repo=current_path,
        commit_message=f"Promote current snapshot {current_path}",
        token=token,
        repo_type="dataset",
        allow_patterns=bundle.allow_patterns,
    )
    current_commit_sha = extract_hf_commit_sha(current_commit)

    record_refresh_finalization(
        state,
        job_name=job_name,
        snapshot_id=snapshot_id,
        snapshot_path=snapshot_path,
        snapshot_manifest_path=snapshot_manifest_path,
        current_path=current_path,
        current_manifest_path=current_manifest_path,
    )
    state_bytes = (
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    state_commit = api.upload_file(
        path_or_fileobj=state_bytes,
        path_in_repo=HF_REFRESH_STATE_PATH,
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
        commit_message=f"Finalize current snapshot for {current_path}",
    )
    final_commit_sha = extract_hf_commit_sha(state_commit) or current_commit_sha
    if release_tag is not None and final_commit_sha is not None:
        create_release_tag(
            api=api,
            token=token,
            repo_id=repo_id,
            tag=release_tag,
            commit_sha=final_commit_sha,
        )

    commit_info = (
        state_commit
        if getattr(state_commit, "commit_url", None)
        else current_commit
        if getattr(current_commit, "commit_url", None)
        else snapshot_commit
    )
    commit_url = getattr(commit_info, "commit_url", None)
    return SnapshotFinalizeResult(
        repo_id=repo_id,
        snapshot_path=snapshot_path,
        snapshot_manifest_path=snapshot_manifest_path,
        current_path=current_path,
        current_manifest_path=current_manifest_path,
        state_path=HF_REFRESH_STATE_PATH,
        commit_sha=final_commit_sha,
        bundle_commit_sha=current_commit_sha,
        commit_url=commit_url,
        release_tag=release_tag,
    )
