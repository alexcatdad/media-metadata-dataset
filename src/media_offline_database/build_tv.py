from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from media_offline_database.bootstrap import write_bootstrap_corpus_artifact
from media_offline_database.ingest_tvmaze import (
    TVMAZE_SOURCE_ID,
    TVmazeFetchShow,
    fetch_tvmaze_show,
    normalize_tvmaze_shows,
)

DEFAULT_TVMAZE_BUILD_OUTPUT_DIR = Path(".mod/out/tvmaze-build")


class TVmazeBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    total_candidates: int
    normalized_seed_path: Path
    manifest_path: Path


def build_tvmaze_tv_artifact(
    *,
    show_ids: list[int],
    output_dir: Path = DEFAULT_TVMAZE_BUILD_OUTPUT_DIR,
    normalized_output_path: Path | None = None,
    artifact_output_dir: Path | None = None,
    fetch_show: TVmazeFetchShow = fetch_tvmaze_show,
) -> TVmazeBuildResult:
    normalized_seed_path = normalized_output_path or (
        output_dir / "normalized" / "tvmaze-normalized.jsonl"
    )
    compiled_artifact_output_dir = artifact_output_dir or (output_dir / "compiled")

    batch = normalize_tvmaze_shows(show_ids=show_ids, fetch_show=fetch_show)
    normalized_seed_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_seed_path.write_text(
        "\n".join(entity.model_dump_json() for entity in batch.entities)
        + ("\n" if batch.entities else ""),
        encoding="utf-8",
    )
    manifest_path = write_bootstrap_corpus_artifact(
        input_path=normalized_seed_path,
        output_dir=compiled_artifact_output_dir,
        source_id=TVMAZE_SOURCE_ID,
    )

    return TVmazeBuildResult(
        snapshot_id=batch.source_snapshot_id,
        total_candidates=batch.total_candidates,
        normalized_seed_path=normalized_seed_path,
        manifest_path=manifest_path,
    )
