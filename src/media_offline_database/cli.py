from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from huggingface_hub import HfApi
from rich.console import Console

from media_offline_database.anilist_concept_search import search_anime_by_concept
from media_offline_database.artifacts import write_keyless_smoke_artifact
from media_offline_database.bootstrap import write_bootstrap_corpus_artifact
from media_offline_database.build_anime import (
    DEFAULT_ANIME_BUILD_OUTPUT_DIR,
    build_manami_anime_artifact,
)
from media_offline_database.build_movie import (
    DEFAULT_WIKIDATA_MOVIE_BUILD_OUTPUT_DIR,
    build_wikidata_movie_artifact,
)
from media_offline_database.build_tv import (
    DEFAULT_TVMAZE_BUILD_OUTPUT_DIR,
    build_tvmaze_tv_artifact,
)
from media_offline_database.corpus_concept_search import search_corpus_by_concept
from media_offline_database.enrich_anilist_metadata import (
    write_anilist_metadata_enriched_seed,
)
from media_offline_database.enrich_anilist_relations import (
    write_anilist_relation_enriched_seed,
)
from media_offline_database.hf_publish import (
    HF_REFRESH_STATE_PATH,
    load_hf_refresh_state,
    publish_checkpoint_bundle,
    rehearse_publish_bundle,
    resolve_hf_repo_id,
)
from media_offline_database.ingest_anilist import write_anilist_search_seed
from media_offline_database.ingest_manami import write_normalized_manami_seed
from media_offline_database.llm import openai_compat_handshake, resolve_z_ai_api_key
from media_offline_database.llm_enhancement import (
    apply_llm_relationship_judgments,
    execute_llm_relationship_candidates,
    select_llm_relationship_candidates,
    write_llm_candidate_plan,
)
from media_offline_database.query import build_query_preview, load_query_entities
from media_offline_database.refresh import run_manami_refresh_checkpoint
from media_offline_database.release_readiness import validate_release_readiness
from media_offline_database.settings import Settings
from media_offline_database.snapshot_compatibility import validate_snapshot_compatibility
from media_offline_database.snapshot_finalize import (
    materialize_current_snapshot,
    publish_current_snapshot,
)
from media_offline_database.sources import SourceRole
from media_offline_database.v1_artifact import DEFAULT_V1_OUTPUT_DIR, write_v1_core_artifact

app = typer.Typer(help="Media Offline Database dataset compiler.")
console = Console()
DEFAULT_SMOKE_OUTPUT_DIR = Path(".mod/out/keyless-smoke")
DEFAULT_BOOTSTRAP_INPUT_PATH = Path("corpus/bootstrap-screen-v1.jsonl")
DEFAULT_BOOTSTRAP_OUTPUT_DIR = Path(".mod/out/bootstrap-corpus")
DEFAULT_MANAMI_OUTPUT_PATH = Path(".mod/out/manami-normalized/manami-normalized.jsonl")
DEFAULT_ANILIST_ENRICHED_OUTPUT_PATH = Path(
    ".mod/out/manami-enriched/manami-enriched.jsonl"
)
DEFAULT_QUERY_MATCH_LIMIT = 5
DEFAULT_QUERY_TAG_LIMIT = 5
DEFAULT_ANILIST_METADATA_ENRICHED_OUTPUT_PATH = Path(
    ".mod/out/manami-enriched/manami-enriched-metadata.jsonl"
)
DEFAULT_TVMAZE_SHOW_IDS = [1825]
DEFAULT_WIKIDATA_MOVIE_QIDS = ["Q166262", "Q163872", "Q189330"]
SmokeOutputDirOption = Annotated[
    Path,
    typer.Option(
        "--output-dir",
        help="Directory where the keyless smoke artifact should be written.",
    ),
]
BootstrapInputPathOption = Annotated[
    Path,
    typer.Option(
        "--input-path",
        help="JSONL bootstrap corpus seed to compile into a Parquet artifact.",
    ),
]
BootstrapOutputDirOption = Annotated[
    Path,
    typer.Option(
        "--output-dir",
        help="Directory where the bootstrap corpus artifact should be written.",
    ),
]
ManamiInputPathOption = Annotated[
    Path,
    typer.Option(
        "--input-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to a downloaded manami release JSON file.",
    ),
]
ManamiOutputPathOption = Annotated[
    Path,
    typer.Option(
        "--output-path",
        help="Where the normalized bootstrap-like JSONL subset should be written.",
    ),
]
ManamiLimitOption = Annotated[
    int | None,
    typer.Option(
        "--limit",
        min=1,
        help="Optional maximum number of normalized entries to emit after filtering.",
    ),
]
ManamiTitleContainsOption = Annotated[
    str | None,
    typer.Option(
        "--title-contains",
        help="Optional case-insensitive title substring filter for a tiny focused subset.",
    ),
]
AniListEnrichmentInputPathOption = Annotated[
    Path,
    typer.Option(
        "--input-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Normalized bootstrap-like JSONL seed to enrich with AniList relation typing.",
    ),
]
AniListEnrichmentOutputPathOption = Annotated[
    Path,
    typer.Option(
        "--output-path",
        help="Where the AniList relation-enriched JSONL seed should be written.",
    ),
]
QueryStringArgument = Annotated[
    str,
    typer.Argument(help="Free-text title query to resolve into a canonical entity preview."),
]
QueryInputPathOption = Annotated[
    Path | None,
    typer.Option(
        "--input-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Bootstrap JSONL seed to query.",
    ),
]
QueryManifestPathOption = Annotated[
    Path | None,
    typer.Option(
        "--manifest-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Compiled bootstrap artifact manifest to query instead of raw JSONL.",
    ),
]
QueryEntityIdOption = Annotated[
    str | None,
    typer.Option(
        "--entity-id",
        help="Optional canonical entity id to preview directly after loading the corpus.",
    ),
]
QueryMatchLimitOption = Annotated[
    int,
    typer.Option(
        "--match-limit",
        min=1,
        help="How many search matches to include in the structured preview.",
    ),
]
QueryTagLimitOption = Annotated[
    int,
    typer.Option(
        "--tag-limit",
        min=0,
        help="How many shared-tag neighbors to include outside the family graph.",
    ),
]
AniListMetadataEnrichmentOutputPathOption = Annotated[
    Path,
    typer.Option(
        "--output-path",
        help="Where the AniList metadata-enriched JSONL seed should be written.",
    ),
]
ConceptQueryArgument = Annotated[
    str,
    typer.Argument(
        help="Plain-language anime discovery query, for example 'romance anime where characters are in university/college'.",
    ),
]
ConceptLimitOption = Annotated[
    int,
    typer.Option(
        "--limit",
        min=1,
        help="Maximum number of AniList concept matches to return.",
    ),
]
CorpusConceptInputPathOption = Annotated[
    Path,
    typer.Option(
        "--input-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Bootstrap-like JSONL seed to search locally by concept.",
    ),
]
AniListSearchStringArgument = Annotated[
    str,
    typer.Argument(
        help="AniList anime title search to normalize into a bootstrap-like local evidence seed.",
    ),
]
AniListSearchOutputPathOption = Annotated[
    Path,
    typer.Option(
        "--output-path",
        help="Where the AniList normalized JSONL seed should be written.",
    ),
]
AnimeBuildOutputDirOption = Annotated[
    Path,
    typer.Option(
        "--output-dir",
        help="Directory where the composed anime build outputs should be written.",
    ),
]
TVmazeBuildOutputDirOption = Annotated[
    Path,
    typer.Option(
        "--output-dir",
        help="Directory where the composed TVmaze build outputs should be written.",
    ),
]
WikidataMovieBuildOutputDirOption = Annotated[
    Path,
    typer.Option(
        "--output-dir",
        help="Directory where the composed Wikidata movie build outputs should be written.",
    ),
]
TVmazeShowIdOption = Annotated[
    list[int] | None,
    typer.Option(
        "--show-id",
        min=1,
        help="TVmaze show ID to include. May be passed more than once.",
    ),
]
WikidataMovieQidOption = Annotated[
    list[str] | None,
    typer.Option(
        "--qid",
        help="Wikidata movie QID to include. May be passed more than once.",
    ),
]
V1CoreInputPathOption = Annotated[
    list[Path],
    typer.Option(
        "--input-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Bootstrap-like JSONL seed to include in the v1 core/profile artifact. May be passed more than once.",
    ),
]
V1CoreOutputDirOption = Annotated[
    Path,
    typer.Option(
        "--output-dir",
        help="Directory where the v1 core/profile artifact should be written.",
    ),
]
V1CoreSourceSnapshotIdOption = Annotated[
    list[str] | None,
    typer.Option(
        "--source-snapshot-id",
        help="Source snapshot mapping as source_id=snapshot_id. May be passed more than once.",
    ),
]
V1CoreSourceSnapshotPathOption = Annotated[
    list[Path] | None,
    typer.Option(
        "--source-snapshot-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="SourceSnapshot JSONL sidecar to include. May be passed more than once.",
    ),
]
V1CoreProviderRunPathOption = Annotated[
    list[Path] | None,
    typer.Option(
        "--provider-run-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="ProviderRun JSONL sidecar to include. May be passed more than once.",
    ),
]
HfRepoIdOption = Annotated[
    str | None,
    typer.Option(
        "--repo-id",
        help="Explicit Hugging Face dataset repo id like namespace/name.",
    ),
]
HfPrivateOption = Annotated[
    bool,
    typer.Option(
        "--private/--public",
        help="Whether the target Hugging Face dataset repo should be private.",
    ),
]
ManifestPathArgument = Annotated[
    Path,
    typer.Argument(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Compiled artifact manifest to publish.",
    ),
]
CheckpointPathOption = Annotated[
    str,
    typer.Option(
        "--checkpoint-path",
        help="Remote dataset path prefix for this artifact bundle.",
    ),
]
RehearsalOutputDirOption = Annotated[
    Path | None,
    typer.Option(
        "--output-dir",
        help="Optional directory where rehearsal artifacts such as README.md should be written.",
    ),
]
ReleaseTagOption = Annotated[
    str | None,
    typer.Option(
        "--release-tag",
        help="Optional Hugging Face dataset tag to create for this supported snapshot.",
    ),
]
RefreshJobNameOption = Annotated[
    str,
    typer.Option(
        "--job-name",
        help="Stable refresh job key used to resume checkpointed runs.",
    ),
]
BatchSizeOption = Annotated[
    int,
    typer.Option(
        "--batch-size",
        min=1,
        help="How many source candidates to process before checkpointing.",
    ),
]
FinalizeOutputDirOption = Annotated[
    Path,
    typer.Option(
        "--output-dir",
        help="Directory where the canonical current/snapshot surface should be materialized.",
    ),
]
PreviousManifestPathOption = Annotated[
    Path | None,
    typer.Option(
        "--previous-manifest-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Optional previous compiled manifest used to mark changed relationships.",
    ),
]
CandidatesPathArgument = Annotated[
    Path,
    typer.Argument(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Prepared LLM candidate JSONL file.",
    ),
]
DecisionPathArgument = Annotated[
    Path,
    typer.Argument(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="LLM judgment decision JSONL file.",
    ),
]
@app.callback()
def main() -> None:
    """Compile and validate open media discovery datasets."""


@app.command()
def doctor() -> None:
    """Print runtime configuration that is safe to display."""

    settings = Settings()
    console.print(
        {
            "env": settings.mod_env,
            "data_dir": str(settings.mod_data_dir),
            "cache_dir": str(settings.mod_cache_dir),
            "output_dir": str(settings.mod_output_dir),
            "source_roles": [role.value for role in SourceRole],
        }
    )


@app.command()
def credentials_smoke() -> None:
    """Verify required AI credential names are wired without printing secrets."""

    settings = Settings()
    settings.require_ai_credentials()
    console.print(
        {
            "cloudflare_account_id": "present",
            "cloudflare_api_token": "present",
            "openai_compat_api_key": "present",
        }
    )


@app.command()
def openrouter_smoke() -> None:
    """Run a tiny local OpenRouter model handshake using typed settings."""

    settings = Settings()
    if not settings.openai_compat_api_key:
        raise typer.BadParameter("OPENAI_COMPAT_API_KEY is required")

    results = openai_compat_handshake(
        api_key=settings.openai_compat_api_key,
        base_url=settings.openai_compat_base_url,
        models=settings.openai_compat_models,
    )
    console.print([result.model_dump() for result in results])


@app.command()
def z_ai_smoke() -> None:
    """Run a serialized tiny Z.ai model handshake using typed settings."""

    settings = Settings()
    if not settings.z_ai_api_key_id:
        raise typer.BadParameter("Z_AI_API_KEY_ID is required")
    if not settings.z_ai_api_key_secret:
        raise typer.BadParameter("Z_AI_API_KEY_SECRET is required")

    api_key = resolve_z_ai_api_key(
        api_key_id=settings.z_ai_api_key_id,
        api_key_secret=settings.z_ai_api_key_secret,
    )
    results = openai_compat_handshake(
        api_key=api_key,
        base_url=settings.z_ai_base_url,
        models=settings.z_ai_models,
    )
    console.print([result.model_dump() for result in results])


@app.command()
def smoke_artifact(
    output_dir: SmokeOutputDirOption = DEFAULT_SMOKE_OUTPUT_DIR,
) -> None:
    """Generate a tiny Parquet artifact without credentials or network access."""

    manifest_path = write_keyless_smoke_artifact(output_dir)
    console.print({"manifest": str(manifest_path)})


@app.command()
def bootstrap_artifact(
    input_path: BootstrapInputPathOption = DEFAULT_BOOTSTRAP_INPUT_PATH,
    output_dir: BootstrapOutputDirOption = DEFAULT_BOOTSTRAP_OUTPUT_DIR,
) -> None:
    """Compile the tiny checked-in bootstrap corpus into a Parquet artifact."""

    manifest_path = write_bootstrap_corpus_artifact(
        input_path=input_path,
        output_dir=output_dir,
    )
    console.print({"manifest": str(manifest_path)})


@app.command()
def manami_normalize(
    input_path: ManamiInputPathOption,
    output_path: ManamiOutputPathOption = DEFAULT_MANAMI_OUTPUT_PATH,
    limit: ManamiLimitOption = None,
    title_contains: ManamiTitleContainsOption = None,
) -> None:
    """Normalize a downloaded manami release into a tiny bootstrap-like JSONL subset."""

    normalized_path = write_normalized_manami_seed(
        release_path=input_path,
        output_path=output_path,
        limit=limit,
        title_contains=title_contains,
    )
    console.print({"normalized_seed": str(normalized_path)})


@app.command()
def anime_build(
    input_path: ManamiInputPathOption,
    output_dir: AnimeBuildOutputDirOption = DEFAULT_ANIME_BUILD_OUTPUT_DIR,
    limit: ManamiLimitOption = None,
    title_contains: ManamiTitleContainsOption = None,
    start_offset: Annotated[
        int,
        typer.Option("--start-offset", min=0, help="Candidate offset to start from."),
    ] = 0,
    batch_size: Annotated[
        int | None,
        typer.Option(
            "--batch-size",
            min=1,
            help="Optional batch size for checkpointed chunk builds.",
        ),
    ] = None,
) -> None:
    """Run the composed anime build pipeline from manami release to compiled artifact."""

    result = build_manami_anime_artifact(
        release_path=input_path,
        output_dir=output_dir,
        limit=limit,
        title_contains=title_contains,
        start_offset=start_offset,
        batch_size=batch_size,
    )
    console.print(
        {
            "snapshot_id": result.snapshot_id,
            "start_offset": result.start_offset,
            "end_offset": result.end_offset,
            "next_offset": result.next_offset,
            "total_candidates": result.total_candidates,
            "selected_candidates": result.selected_candidate_count,
            "normalized_records": result.normalized_record_count,
            "skipped_candidates": result.skipped_candidate_count,
            "rejection_reasons": result.rejection_reasons,
            "normalized_seed": str(result.normalized_seed_path),
            "relation_enriched_seed": str(result.relation_enriched_seed_path),
            "metadata_enriched_seed": str(result.metadata_enriched_seed_path),
            "source_snapshot": str(result.source_snapshot_path),
            "provider_run": str(result.provider_run_path),
            "rejection_summary": str(result.rejection_summary_path),
            "manifest": str(result.manifest_path),
        }
    )


@app.command()
def tvmaze_build(
    output_dir: TVmazeBuildOutputDirOption = DEFAULT_TVMAZE_BUILD_OUTPUT_DIR,
    show_id: TVmazeShowIdOption = None,
) -> None:
    """Run the composed TV build pipeline from TVmaze shows to compiled artifact."""

    result = build_tvmaze_tv_artifact(
        show_ids=show_id or DEFAULT_TVMAZE_SHOW_IDS,
        output_dir=output_dir,
    )
    console.print(
        {
            "snapshot_id": result.snapshot_id,
            "total_candidates": result.total_candidates,
            "normalized_seed": str(result.normalized_seed_path),
            "source_snapshot": str(result.source_snapshot_path),
            "provider_run": str(result.provider_run_path),
            "manifest": str(result.manifest_path),
        }
    )


@app.command()
def wikidata_movie_build(
    output_dir: WikidataMovieBuildOutputDirOption = DEFAULT_WIKIDATA_MOVIE_BUILD_OUTPUT_DIR,
    qid: WikidataMovieQidOption = None,
) -> None:
    """Run the composed movie build pipeline from Wikidata movie QIDs to compiled artifact."""

    result = build_wikidata_movie_artifact(
        qids=qid or DEFAULT_WIKIDATA_MOVIE_QIDS,
        output_dir=output_dir,
    )
    console.print(
        {
            "snapshot_id": result.snapshot_id,
            "total_candidates": result.total_candidates,
            "normalized_seed": str(result.normalized_seed_path),
            "source_snapshot": str(result.source_snapshot_path),
            "provider_run": str(result.provider_run_path),
            "manifest": str(result.manifest_path),
        }
    )


@app.command()
def v1_core_artifact(
    input_path: V1CoreInputPathOption,
    output_dir: V1CoreOutputDirOption = DEFAULT_V1_OUTPUT_DIR,
    source_snapshot_id: V1CoreSourceSnapshotIdOption = None,
    source_snapshot_path: V1CoreSourceSnapshotPathOption = None,
    provider_run_path: V1CoreProviderRunPathOption = None,
) -> None:
    """Compile bootstrap-like seeds into v1 shared core and profile tables."""

    manifest_path = write_v1_core_artifact(
        input_paths=input_path,
        output_dir=output_dir,
        source_snapshot_ids=_parse_source_snapshot_ids(source_snapshot_id),
        source_snapshot_paths=source_snapshot_path,
        provider_run_paths=provider_run_path,
    )
    console.print({"manifest": str(manifest_path)})


def _parse_source_snapshot_ids(values: list[str] | None) -> dict[str, str] | None:
    if values is None:
        return None

    parsed: dict[str, str] = {}
    for value in values:
        source_id, separator, snapshot_id = value.partition("=")
        if separator != "=" or not source_id or not snapshot_id:
            raise typer.BadParameter(
                "--source-snapshot-id values must use source_id=snapshot_id"
            )
        parsed[source_id] = snapshot_id
    return parsed


@app.command()
def anilist_enrich_relations(
    input_path: AniListEnrichmentInputPathOption,
    output_path: AniListEnrichmentOutputPathOption = DEFAULT_ANILIST_ENRICHED_OUTPUT_PATH,
) -> None:
    """Refine generic anime relations using public AniList relation semantics."""

    enriched_path = write_anilist_relation_enriched_seed(
        input_path=input_path,
        output_path=output_path,
    )
    console.print({"enriched_seed": str(enriched_path)})


@app.command()
def query_preview(
    query: QueryStringArgument,
    input_path: QueryInputPathOption = None,
    manifest_path: QueryManifestPathOption = None,
    entity_id: QueryEntityIdOption = None,
    match_limit: QueryMatchLimitOption = DEFAULT_QUERY_MATCH_LIMIT,
    tag_limit: QueryTagLimitOption = DEFAULT_QUERY_TAG_LIMIT,
) -> None:
    """Search the current corpus, select a canonical entity, and preview its family graph."""

    if input_path is not None and manifest_path is not None:
        raise typer.BadParameter("use either --input-path or --manifest-path, not both")

    try:
        effective_input_path = input_path if manifest_path is None else None
        if effective_input_path is None and manifest_path is None:
            effective_input_path = DEFAULT_BOOTSTRAP_INPUT_PATH

        entities = load_query_entities(
            input_path=effective_input_path,
            manifest_path=manifest_path,
        )
        preview = build_query_preview(
            entities,
            query=query,
            entity_id=entity_id,
            match_limit=match_limit,
            tag_limit=tag_limit,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    console.print_json(
        json=preview.model_dump_json(indent=2),
    )


@app.command()
def anilist_enrich_metadata(
    input_path: AniListEnrichmentInputPathOption,
    output_path: AniListMetadataEnrichmentOutputPathOption = DEFAULT_ANILIST_METADATA_ENRICHED_OUTPUT_PATH,
) -> None:
    """Attach AniList studio and creator metadata for anime entities."""

    enriched_path = write_anilist_metadata_enriched_seed(
        input_path=input_path,
        output_path=output_path,
    )
    console.print({"enriched_seed": str(enriched_path)})


@app.command()
def hf_publish(
    manifest_path: ManifestPathArgument,
    repo_id: HfRepoIdOption = None,
    checkpoint_path: CheckpointPathOption = "checkpoints/manual",
    private: HfPrivateOption = True,
    release_tag: ReleaseTagOption = None,
) -> None:
    """Publish a compiled artifact bundle plus refresh state to a Hugging Face dataset repo."""

    settings = Settings()
    if not settings.hf_token:
        raise typer.BadParameter("HF_TOKEN is required")

    api = HfApi()
    resolved_repo_id = resolve_hf_repo_id(
        settings=settings,
        api=api,
        token=settings.hf_token,
        repo_id=repo_id,
    )
    state = load_hf_refresh_state(
        repo_id=resolved_repo_id,
        token=settings.hf_token,
    )
    result = publish_checkpoint_bundle(
        api=api,
        token=settings.hf_token,
        repo_id=resolved_repo_id,
        manifest_path=manifest_path,
        checkpoint_path=checkpoint_path,
        state=state,
        private=private,
        release_tag=release_tag,
    )
    console.print_json(json=result.model_dump_json(indent=2))


@app.command("hf-rehearse-publish")
def hf_rehearse_publish(
    manifest_path: ManifestPathArgument,
    repo_id: HfRepoIdOption = "local/media-metadata-dataset",
    output_dir: RehearsalOutputDirOption = Path(".mod/out/hf-publication-rehearsal"),
    private: HfPrivateOption = True,
) -> None:
    """Validate the publish bundle and render the dataset card without network upload."""

    result = rehearse_publish_bundle(
        manifest_path=manifest_path,
        repo_id=repo_id or "local/media-metadata-dataset",
        output_dir=output_dir,
        private=private,
    )
    console.print_json(json=result.model_dump_json(indent=2))


@app.command()
def hf_state(
    repo_id: HfRepoIdOption = None,
) -> None:
    """Read the current persisted refresh state from the Hugging Face dataset repo."""

    settings = Settings()
    if not settings.hf_token:
        raise typer.BadParameter("HF_TOKEN is required")

    api = HfApi()
    resolved_repo_id = resolve_hf_repo_id(
        settings=settings,
        api=api,
        token=settings.hf_token,
        repo_id=repo_id,
    )
    state = load_hf_refresh_state(
        repo_id=resolved_repo_id,
        token=settings.hf_token,
        state_path_in_repo=HF_REFRESH_STATE_PATH,
    )
    console.print_json(json=state.model_dump_json(indent=2))


@app.command()
def hf_finalize_current(
    manifest_path: ManifestPathArgument,
    snapshot_id: Annotated[
        str,
        typer.Option("--snapshot-id", help="Stable source snapshot identifier being finalized."),
    ],
    job_name: RefreshJobNameOption = "dataset.default",
    repo_id: HfRepoIdOption = None,
    private: HfPrivateOption = True,
    release_tag: ReleaseTagOption = None,
) -> None:
    """Promote one compiled artifact bundle into a stable current snapshot surface on Hugging Face."""

    settings = Settings()
    if not settings.hf_token:
        raise typer.BadParameter("HF_TOKEN is required")

    api = HfApi()
    resolved_repo_id = resolve_hf_repo_id(
        settings=settings,
        api=api,
        token=settings.hf_token,
        repo_id=repo_id,
    )
    state = load_hf_refresh_state(
        repo_id=resolved_repo_id,
        token=settings.hf_token,
    )
    result = publish_current_snapshot(
        api=api,
        token=settings.hf_token,
        repo_id=resolved_repo_id,
        manifest_path=manifest_path,
        state=state,
        job_name=job_name,
        snapshot_id=snapshot_id,
        private=private,
        release_tag=release_tag,
    )
    console.print_json(json=result.model_dump_json(indent=2))


@app.command("validate-snapshot-compatibility")
def validate_snapshot_compatibility_command(
    previous_manifest_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Previous snapshot manifest to compare from.",
        ),
    ],
    current_manifest_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Current snapshot manifest to validate.",
        ),
    ],
) -> None:
    """Compare two snapshot manifests and report compatibility findings."""

    report = validate_snapshot_compatibility(
        previous_manifest_path=previous_manifest_path,
        current_manifest_path=current_manifest_path,
    )
    console.print_json(json=report.model_dump_json(indent=2))
    if not report.compatible:
        raise typer.Exit(code=1)


@app.command("validate-release-readiness")
def validate_release_readiness_command(
    manifest_path: ManifestPathArgument,
) -> None:
    """Validate that a compiled artifact bundle is ready for release materialization."""

    report = validate_release_readiness(manifest_path)
    console.print_json(json=report.model_dump_json(indent=2))
    if not report.ready:
        raise typer.Exit(code=1)


@app.command()
def materialize_current_snapshot_surface(
    manifest_path: ManifestPathArgument,
    snapshot_id: Annotated[
        str,
        typer.Option("--snapshot-id", help="Stable source snapshot identifier being finalized."),
    ],
    job_name: RefreshJobNameOption = "dataset.default",
    output_dir: FinalizeOutputDirOption = Path(".mod/out/finalized-snapshots"),
) -> None:
    """Copy a compiled artifact bundle into stable local snapshot and current paths."""

    result = materialize_current_snapshot(
        manifest_path=manifest_path,
        output_dir=output_dir,
        job_name=job_name,
        snapshot_id=snapshot_id,
    )
    console.print_json(json=result.model_dump_json(indent=2))


@app.command()
def llm_prepare_candidates(
    manifest_path: ManifestPathArgument,
    previous_manifest_path: PreviousManifestPathOption = None,
    confidence_threshold: Annotated[
        float,
        typer.Option(
            "--confidence-threshold",
            min=0.0,
            max=1.0,
            help="Only relationships below this confidence, or generic fallback edges, become candidates.",
        ),
    ] = 0.85,
) -> None:
    """Build a cross-domain LLM judgment candidate plan from compiled artifacts."""

    candidates = select_llm_relationship_candidates(
        manifest_path=manifest_path,
        previous_manifest_path=previous_manifest_path,
        confidence_threshold=confidence_threshold,
    )
    result = write_llm_candidate_plan(
        manifest_path=manifest_path,
        candidates=candidates,
    )
    console.print_json(json=result.model_dump_json(indent=2))


@app.command()
def llm_execute_candidates(
    candidates_path: CandidatesPathArgument,
    manifest_path: ManifestPathArgument,
) -> None:
    """Execute provider-backed relationship judgments for prepared candidates."""

    settings = Settings()
    if not settings.openai_compat_api_key:
        raise typer.BadParameter("OPENAI_COMPAT_API_KEY is required")

    result = execute_llm_relationship_candidates(
        candidates_path=candidates_path,
        manifest_path=manifest_path,
        api_key=settings.openai_compat_api_key,
        base_url=settings.openai_compat_base_url,
        provider="openrouter",
        model=settings.openai_compat_default_model,
    )
    console.print_json(json=result.model_dump_json(indent=2))


@app.command()
def llm_apply_judgments(
    decisions_path: DecisionPathArgument,
    manifest_path: ManifestPathArgument,
    min_confidence: Annotated[
        float,
        typer.Option(
            "--min-confidence",
            min=0.0,
            max=1.0,
            help="Only apply successful LLM judgments at or above this confidence.",
        ),
    ] = 0.8,
) -> None:
    """Materialize eligible LLM relationship judgments into a derived sidecar."""

    result = apply_llm_relationship_judgments(
        decisions_path=decisions_path,
        manifest_path=manifest_path,
        min_confidence=min_confidence,
    )
    console.print_json(json=result.model_dump_json(indent=2))


@app.command()
def manami_refresh(
    input_path: ManamiInputPathOption,
    output_dir: AnimeBuildOutputDirOption = DEFAULT_ANIME_BUILD_OUTPUT_DIR,
    repo_id: HfRepoIdOption = None,
    job_name: RefreshJobNameOption = "anime.manami.default",
    batch_size: BatchSizeOption = 100,
    limit: ManamiLimitOption = None,
    title_contains: ManamiTitleContainsOption = None,
    private: HfPrivateOption = True,
) -> None:
    """Run one checkpointed manami batch and persist resume state to Hugging Face."""

    result = run_manami_refresh_checkpoint(
        release_path=input_path,
        output_dir=output_dir,
        repo_id=repo_id,
        job_name=job_name,
        batch_size=batch_size,
        limit=limit,
        title_contains=title_contains,
        private_repo=private,
    )
    console.print_json(json=result.model_dump_json(indent=2))


@app.command()
def anilist_concept_preview(
    query: ConceptQueryArgument,
    limit: ConceptLimitOption = 10,
) -> None:
    """Run a thin AniList-backed concept search from a plain-language anime query."""

    filters, matches = search_anime_by_concept(query, limit=limit)
    console.print_json(
        json=json.dumps(
            {
                "query": query,
                "filters": filters.model_dump(),
                "matches": [match.model_dump() for match in matches],
            }
        )
    )


@app.command()
def corpus_concept_preview(
    query: ConceptQueryArgument,
    input_path: CorpusConceptInputPathOption = DEFAULT_BOOTSTRAP_INPUT_PATH,
    limit: ConceptLimitOption = 10,
) -> None:
    """Run concept search against the stored bootstrap-like corpus."""

    entities = load_query_entities(input_path=input_path)
    preview = search_corpus_by_concept(entities, query=query, limit=limit)
    console.print_json(
        json=json.dumps(
            {
                "query": query,
                "filters": preview.filters.model_dump(),
                "matches": [match.model_dump() for match in preview.matches],
            }
        )
    )


@app.command()
def anilist_normalize_search(
    search: AniListSearchStringArgument,
    output_path: AniListSearchOutputPathOption = Path(".mod/out/anilist-search/anilist-search.jsonl"),
) -> None:
    """Normalize one AniList anime title search into a bootstrap-like local evidence seed."""

    normalized_path = write_anilist_search_seed(
        search=search,
        output_path=output_path,
    )
    console.print({"normalized_seed": str(normalized_path)})
