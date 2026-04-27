from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from media_offline_database.bootstrap import write_bootstrap_corpus_artifact
from media_offline_database.ingest_normalization import (
    ProviderRun,
    SourceSnapshot,
    write_provider_runs,
    write_source_snapshots,
)
from media_offline_database.ingest_wikidata_movies import (
    WIKIDATA_MOVIE_ADAPTER_VERSION,
    WIKIDATA_SOURCE_ID,
    WikidataMovieFetch,
    fetch_wikidata_movie_records,
    normalize_wikidata_movie_batch,
)
from media_offline_database.publishability import (
    ARTIFACT_POLICY_VERSION,
    SOURCE_FIELD_POLICY_VERSION,
    SOURCE_POLICY_VERSION,
)
from media_offline_database.sources import SourceRole

DEFAULT_WIKIDATA_MOVIE_BUILD_OUTPUT_DIR = Path(".mod/out/wikidata-movie-build")


class WikidataMovieBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    total_candidates: int
    normalized_seed_path: Path
    source_snapshot_path: Path
    provider_run_path: Path
    manifest_path: Path


def build_wikidata_movie_artifact(
    *,
    qids: list[str],
    output_dir: Path = DEFAULT_WIKIDATA_MOVIE_BUILD_OUTPUT_DIR,
    normalized_output_path: Path | None = None,
    artifact_output_dir: Path | None = None,
    fetch_records: WikidataMovieFetch = fetch_wikidata_movie_records,
) -> WikidataMovieBuildResult:
    normalized_seed_path = normalized_output_path or (
        output_dir / "normalized" / "wikidata-movie-normalized.jsonl"
    )
    source_snapshot_path = output_dir / "source-metadata" / "source-snapshots.jsonl"
    provider_run_path = output_dir / "source-metadata" / "provider-runs.jsonl"
    compiled_artifact_output_dir = artifact_output_dir or (output_dir / "compiled")

    started_at = datetime.now(tz=UTC)
    batch = normalize_wikidata_movie_batch(qids=qids, fetch_records=fetch_records)
    normalized_seed_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_seed_path.write_text(
        "\n".join(entity.model_dump_json() for entity in batch.entities)
        + ("\n" if batch.entities else ""),
        encoding="utf-8",
    )
    manifest_path = write_bootstrap_corpus_artifact(
        input_path=normalized_seed_path,
        output_dir=compiled_artifact_output_dir,
        source_id=WIKIDATA_SOURCE_ID,
    )
    finished_at = datetime.now(tz=UTC)
    write_source_snapshots(
        source_snapshot_path,
        [
            SourceSnapshot(
                source_snapshot_id=batch.source_snapshot_id,
                source_id=WIKIDATA_SOURCE_ID,
                source_role=SourceRole.BACKBONE_SOURCE,
                snapshot_kind="sparql_query_window",
                fetched_at=batch.fetched_at,
                fetch_window_started_at=batch.fetched_at,
                fetch_window_finished_at=batch.fetched_at,
                source_version=batch.source_snapshot_id,
                policy_version=SOURCE_POLICY_VERSION,
                publishable_field_policy_version=SOURCE_FIELD_POLICY_VERSION,
                artifact_policy_version=ARTIFACT_POLICY_VERSION,
                record_count=len(batch.entities),
                notes="Wikidata SPARQL query normalized without provider credentials.",
            )
        ],
    )
    write_provider_runs(
        provider_run_path,
        [
            ProviderRun(
                provider_run_id=f"provider-run:{WIKIDATA_SOURCE_ID}:{batch.source_snapshot_id}",
                source_id=WIKIDATA_SOURCE_ID,
                source_snapshot_id=batch.source_snapshot_id,
                adapter_name="wikidata-movie-normalizer",
                adapter_version=WIKIDATA_MOVIE_ADAPTER_VERSION,
                started_at=started_at,
                finished_at=finished_at,
                request_count=1 if qids else 0,
                cache_hit_count=0,
                status="completed",
                auth_shape="none",
                notes="Public Wikidata SPARQL fetch; no secret values involved.",
            )
        ],
    )

    return WikidataMovieBuildResult(
        snapshot_id=batch.source_snapshot_id,
        total_candidates=batch.total_candidates,
        normalized_seed_path=normalized_seed_path,
        source_snapshot_path=source_snapshot_path,
        provider_run_path=provider_run_path,
        manifest_path=manifest_path,
    )
