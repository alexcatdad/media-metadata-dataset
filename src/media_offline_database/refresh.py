from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from media_offline_database.build_anime import (
    DEFAULT_ANIME_BUILD_OUTPUT_DIR,
    build_manami_anime_artifact,
)
from media_offline_database.enrich_anilist_metadata import (
    AniListMetadataFetcher,
    fetch_anilist_metadata,
)
from media_offline_database.enrich_anilist_relations import (
    AniListRelationFetcher,
    fetch_anilist_relations,
)
from media_offline_database.hf_publish import (
    HfApiLike,
    load_hf_refresh_state,
    publish_checkpoint_bundle,
    resolve_hf_repo_id,
)
from media_offline_database.ingest_manami import load_manami_release, manami_snapshot_id
from media_offline_database.provider_http import ProviderRunGuard
from media_offline_database.refresh_state import (
    RefreshState,
    next_refresh_offset,
    record_refresh_progress,
    write_refresh_state,
)
from media_offline_database.settings import Settings


class RefreshRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_name: str
    source_name: str
    repo_id: str
    snapshot_id: str
    status: Literal["in_progress", "completed"]
    start_offset: int
    end_offset: int
    next_offset: int
    total_candidates: int
    checkpoint_path: str
    local_state_path: Path
    manifest_path: Path
    commit_url: str | None = None


def run_manami_refresh_checkpoint(
    *,
    release_path: Path,
    output_dir: Path = DEFAULT_ANIME_BUILD_OUTPUT_DIR,
    repo_id: str | None = None,
    job_name: str = "anime.manami.default",
    batch_size: int = 100,
    limit: int | None = None,
    title_contains: str | None = None,
    private_repo: bool = True,
    settings: Settings | None = None,
    api: HfApiLike | None = None,
    remote_state: RefreshState | None = None,
    fetch_relations: AniListRelationFetcher | None = None,
    fetch_metadata: AniListMetadataFetcher | None = None,
) -> RefreshRunResult:
    effective_settings = settings or Settings()
    if not effective_settings.hf_token:
        raise ValueError("HF_TOKEN is required for checkpoint publishing")

    from huggingface_hub import HfApi

    effective_api: HfApiLike = api or HfApi()
    resolved_repo_id = resolve_hf_repo_id(
        settings=effective_settings,
        api=effective_api,
        token=effective_settings.hf_token,
        repo_id=repo_id,
    )

    effective_remote_state = remote_state or load_hf_refresh_state(
        repo_id=resolved_repo_id,
        token=effective_settings.hf_token,
    )
    release = load_manami_release(release_path)
    snapshot_id = manami_snapshot_id(release)
    start_offset = next_refresh_offset(
        effective_remote_state,
        job_name=job_name,
        snapshot_id=snapshot_id,
    )

    with ProviderRunGuard(
        scope=f"refresh:{job_name}",
        guard_dir=effective_settings.mod_cache_dir / "provider-http" / "locks",
        stale_after_seconds=effective_settings.provider_run_guard_stale_seconds,
    ):
        build_result = build_manami_anime_artifact(
            release_path=release_path,
            output_dir=output_dir,
            limit=limit,
            title_contains=title_contains,
            start_offset=start_offset,
            batch_size=batch_size,
            fetch_relations=fetch_relations or fetch_anilist_relations,
            fetch_metadata=fetch_metadata or fetch_anilist_metadata,
        )

        completed = build_result.next_offset >= build_result.total_candidates
        checkpoint_path = (
            f"checkpoints/{job_name}/{build_result.snapshot_id}/"
            f"{build_result.start_offset:08d}-{build_result.end_offset:08d}"
        )
        record_refresh_progress(
            effective_remote_state,
            job_name=job_name,
            source_name="manami",
            snapshot_id=build_result.snapshot_id,
            source_snapshot_id=snapshot_id,
            batch_size=batch_size,
            completed_count=build_result.end_offset,
            next_offset=build_result.next_offset,
            status="completed" if completed else "in_progress",
            last_completed_item_key=build_result.last_completed_item_key,
            last_checkpoint_path=checkpoint_path,
        )
        local_state_path = output_dir / "state" / "refresh-state.json"
        write_refresh_state(local_state_path, effective_remote_state)

        publish_result = publish_checkpoint_bundle(
            api=effective_api,
            token=effective_settings.hf_token,
            repo_id=resolved_repo_id,
            manifest_path=build_result.manifest_path,
            checkpoint_path=checkpoint_path,
            state=effective_remote_state,
            private=private_repo,
        )

        return RefreshRunResult(
            job_name=job_name,
            source_name="manami",
            repo_id=resolved_repo_id,
            snapshot_id=build_result.snapshot_id,
            status="completed" if completed else "in_progress",
            start_offset=build_result.start_offset,
            end_offset=build_result.end_offset,
            next_offset=build_result.next_offset,
            total_candidates=build_result.total_candidates,
            checkpoint_path=publish_result.checkpoint_path,
            local_state_path=local_state_path,
            manifest_path=build_result.manifest_path,
            commit_url=publish_result.commit_url,
        )
