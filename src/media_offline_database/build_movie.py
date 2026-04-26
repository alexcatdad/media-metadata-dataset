from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from media_offline_database.bootstrap import write_bootstrap_corpus_artifact
from media_offline_database.ingest_wikidata_movies import (
    WIKIDATA_SOURCE_ID,
    WikidataMovieFetch,
    fetch_wikidata_movie_records,
    normalize_wikidata_movie_batch,
)

DEFAULT_WIKIDATA_MOVIE_BUILD_OUTPUT_DIR = Path(".mod/out/wikidata-movie-build")


class WikidataMovieBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    total_candidates: int
    normalized_seed_path: Path
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
    compiled_artifact_output_dir = artifact_output_dir or (output_dir / "compiled")

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

    return WikidataMovieBuildResult(
        snapshot_id=batch.source_snapshot_id,
        total_candidates=batch.total_candidates,
        normalized_seed_path=normalized_seed_path,
        manifest_path=manifest_path,
    )
