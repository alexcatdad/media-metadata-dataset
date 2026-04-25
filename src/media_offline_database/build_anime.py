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
from media_offline_database.ingest_manami import write_normalized_manami_seed

DEFAULT_ANIME_BUILD_OUTPUT_DIR = Path(".mod/out/anime-build")


class AnimeBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

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

    write_normalized_manami_seed(
        release_path=release_path,
        output_path=normalized_seed_path,
        limit=limit,
        title_contains=title_contains,
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
        normalized_seed_path=normalized_seed_path,
        relation_enriched_seed_path=relation_enriched_seed_path,
        metadata_enriched_seed_path=metadata_enriched_seed_path,
        manifest_path=manifest_path,
    )
