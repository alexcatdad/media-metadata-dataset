from __future__ import annotations

from datetime import UTC, datetime
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
from media_offline_database.ingest_normalization import (
    AdapterRejectionSummary,
    ProviderRun,
    SourceSnapshot,
    write_adapter_rejection_summary,
    write_provider_runs,
    write_source_snapshots,
)
from media_offline_database.publishability import (
    ARTIFACT_POLICY_VERSION,
    SOURCE_FIELD_POLICY_VERSION,
    SOURCE_POLICY_VERSION,
)
from media_offline_database.sources import SourceRole

DEFAULT_ANIME_BUILD_OUTPUT_DIR = Path(".mod/out/anime-build")
MANAMI_ADAPTER_VERSION = "manami-bootstrap-v1"


class AnimeBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    start_offset: int
    end_offset: int
    next_offset: int
    total_candidates: int
    selected_candidate_count: int
    normalized_record_count: int
    skipped_candidate_count: int
    rejection_reasons: dict[str, int]
    last_completed_item_key: str | None = None
    normalized_seed_path: Path
    relation_enriched_seed_path: Path
    metadata_enriched_seed_path: Path
    source_snapshot_path: Path
    provider_run_path: Path
    rejection_summary_path: Path
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
    source_snapshot_path = output_dir / "source-metadata" / "source-snapshots.jsonl"
    provider_run_path = output_dir / "source-metadata" / "provider-runs.jsonl"
    rejection_summary_path = output_dir / "source-metadata" / "adapter-rejections.json"
    compiled_artifact_output_dir = artifact_output_dir or (output_dir / "compiled")

    started_at = datetime.now(tz=UTC)
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
    finished_at = datetime.now(tz=UTC)
    fetched_at = _datetime_from_date(manami_snapshot_id(release))
    source_snapshot_id = f"manami:{manami_snapshot_id(release)}"
    rejection_summary = AdapterRejectionSummary(
        adapter_name="manami-release-normalizer",
        adapter_version=MANAMI_ADAPTER_VERSION,
        source_id="manami",
        source_snapshot_id=source_snapshot_id,
        selected_candidate_count=normalized_batch.selected_candidate_count,
        normalized_record_count=normalized_batch.normalized_record_count,
        skipped_candidate_count=normalized_batch.skipped_candidate_count,
        rejection_reasons=normalized_batch.rejection_reasons,
        rejections=normalized_batch.rejections,
        notes=(
            "Candidate rejection accounting stores source offsets, reason codes, "
            "and field names only; no restricted payload data is included."
        ),
    )
    write_adapter_rejection_summary(rejection_summary_path, rejection_summary)
    write_source_snapshots(
        source_snapshot_path,
        [
            SourceSnapshot(
                source_snapshot_id=source_snapshot_id,
                source_id="manami",
                source_role=SourceRole.BACKBONE_SOURCE,
                snapshot_kind="release_file",
                fetched_at=fetched_at,
                source_published_at=fetched_at,
                source_version=manami_snapshot_id(release),
                policy_version=SOURCE_POLICY_VERSION,
                publishable_field_policy_version=SOURCE_FIELD_POLICY_VERSION,
                artifact_policy_version=ARTIFACT_POLICY_VERSION,
                record_count=len(normalized_batch.entities),
                manifest_uri=str(release_path),
                notes="manami release normalized without provider credentials.",
            )
        ],
    )
    write_provider_runs(
        provider_run_path,
        [
            ProviderRun(
                provider_run_id=f"provider-run:manami:{manami_snapshot_id(release)}",
                source_id="manami",
                source_snapshot_id=f"manami:{manami_snapshot_id(release)}",
                adapter_name="manami-release-normalizer",
                adapter_version=MANAMI_ADAPTER_VERSION,
                started_at=started_at,
                finished_at=finished_at,
                request_count=0,
                cache_hit_count=0,
                status="completed",
                auth_shape="none",
                notes=(
                    "Local release-file normalization; no secret values involved. "
                    f"Selected candidates: {normalized_batch.selected_candidate_count}; "
                    f"normalized records: {normalized_batch.normalized_record_count}; "
                    f"skipped candidates: {normalized_batch.skipped_candidate_count}; "
                    f"rejection reasons: {normalized_batch.rejection_reasons}."
                ),
            )
        ],
    )

    return AnimeBuildResult(
        snapshot_id=manami_snapshot_id(release),
        start_offset=normalized_batch.start_offset,
        end_offset=normalized_batch.end_offset,
        next_offset=normalized_batch.next_offset,
        total_candidates=normalized_batch.total_candidates,
        selected_candidate_count=normalized_batch.selected_candidate_count,
        normalized_record_count=normalized_batch.normalized_record_count,
        skipped_candidate_count=normalized_batch.skipped_candidate_count,
        rejection_reasons=normalized_batch.rejection_reasons,
        last_completed_item_key=normalized_batch.last_completed_item_key,
        normalized_seed_path=normalized_seed_path,
        relation_enriched_seed_path=relation_enriched_seed_path,
        metadata_enriched_seed_path=metadata_enriched_seed_path,
        source_snapshot_path=source_snapshot_path,
        provider_run_path=provider_run_path,
        rejection_summary_path=rejection_summary_path,
        manifest_path=manifest_path,
    )


def _datetime_from_date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)
