from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from media_offline_database.bootstrap import write_bootstrap_corpus_artifact
from media_offline_database.enrich_anilist_metadata import (
    AniListMetadataFetcher,
    fetch_anilist_metadata,
    write_anilist_metadata_enriched_seed,
)
from media_offline_database.enrich_anilist_relations import (
    AniListRelationFetcher,
    fetch_anilist_relations,
    write_anilist_relation_enriched_seed,
)
from media_offline_database.ingest_manami import (
    load_manami_release,
    manami_snapshot_id,
    normalize_manami_release_batch,
)

DEFAULT_ANIME_BUILD_OUTPUT_DIR = Path(".mod/out/anime-build")


class AnimeBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    start_offset: int
    end_offset: int
    next_offset: int
    total_candidates: int
    last_completed_item_key: str | None = None
    normalized_seed_path: Path
    relation_enriched_seed_path: Path
    metadata_enriched_seed_path: Path
    manifest_path: Path


def build_manami_anime_artifact(
    *,
    release_path: Path,
    output_dir: Path = DEFAULT_ANIME_BUILD_OUTPUT_DIR,
    normalized_output_path: Path | None = None,
    relation_enriched_output_path: Path | None = None,
    metadata_enriched_output_path: Path | None = None,
    artifact_output_dir: Path | None = None,
    limit: int | None = None,
    title_contains: str | None = None,
    start_offset: int = 0,
    batch_size: int | None = None,
    fetch_relations: AniListRelationFetcher = fetch_anilist_relations,
    fetch_metadata: AniListMetadataFetcher = fetch_anilist_metadata,
) -> AnimeBuildResult:
    normalized_seed_path = normalized_output_path or (
        output_dir / "normalized" / "manami-normalized.jsonl"
    )
    relation_enriched_seed_path = relation_enriched_output_path or (
        output_dir / "relation-enriched" / "manami-enriched.jsonl"
    )
    metadata_enriched_seed_path = metadata_enriched_output_path or (
        output_dir / "metadata-enriched" / "manami-enriched-metadata.jsonl"
    )
    compiled_artifact_output_dir = artifact_output_dir or (output_dir / "compiled")

    release = load_manami_release(release_path)
    normalized_batch = normalize_manami_release_batch(
        release,
        start_offset=start_offset,
        batch_size=batch_size,
        limit=limit,
        title_contains=title_contains,
    )
    normalized_seed_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_seed_path.write_text(
        "\n".join(
            entity.model_dump_json() for entity in normalized_batch.entities
        )
        + ("\n" if normalized_batch.entities else ""),
        encoding="utf-8",
    )
    write_anilist_relation_enriched_seed(
        input_path=normalized_seed_path,
        output_path=relation_enriched_seed_path,
        fetch_relations=fetch_relations,
    )
    write_anilist_metadata_enriched_seed(
        input_path=relation_enriched_seed_path,
        output_path=metadata_enriched_seed_path,
        fetch_metadata=fetch_metadata,
    )
    manifest_path = write_bootstrap_corpus_artifact(
        input_path=metadata_enriched_seed_path,
        output_dir=compiled_artifact_output_dir,
    )

    return AnimeBuildResult(
        snapshot_id=manami_snapshot_id(release),
        start_offset=normalized_batch.start_offset,
        end_offset=normalized_batch.end_offset,
        next_offset=normalized_batch.next_offset,
        total_candidates=normalized_batch.total_candidates,
        last_completed_item_key=normalized_batch.last_completed_item_key,
        normalized_seed_path=normalized_seed_path,
        relation_enriched_seed_path=relation_enriched_seed_path,
        metadata_enriched_seed_path=metadata_enriched_seed_path,
        manifest_path=manifest_path,
    )
