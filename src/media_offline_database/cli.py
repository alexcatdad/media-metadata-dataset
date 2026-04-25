from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from media_offline_database.anilist_concept_search import search_anime_by_concept
from media_offline_database.artifacts import write_keyless_smoke_artifact
from media_offline_database.bootstrap import write_bootstrap_corpus_artifact
from media_offline_database.build_anime import (
    DEFAULT_ANIME_BUILD_OUTPUT_DIR,
    build_manami_anime_artifact,
)
from media_offline_database.corpus_concept_search import search_corpus_by_concept
from media_offline_database.enrich_anilist_metadata import (
    write_anilist_metadata_enriched_seed,
)
from media_offline_database.enrich_anilist_relations import (
    write_anilist_relation_enriched_seed,
)
from media_offline_database.ingest_anilist import write_anilist_search_seed
from media_offline_database.ingest_manami import write_normalized_manami_seed
from media_offline_database.llm import openai_compat_handshake, resolve_z_ai_api_key
from media_offline_database.query import build_query_preview, load_query_entities
from media_offline_database.settings import Settings
from media_offline_database.sources import SourceRole

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
) -> None:
    """Run the composed anime build pipeline from manami release to compiled artifact."""

    result = build_manami_anime_artifact(
        release_path=input_path,
        output_dir=output_dir,
        limit=limit,
        title_contains=title_contains,
    )
    console.print(
        {
            "normalized_seed": str(result.normalized_seed_path),
            "relation_enriched_seed": str(result.relation_enriched_seed_path),
            "metadata_enriched_seed": str(result.metadata_enriched_seed_path),
            "manifest": str(result.manifest_path),
        }
    )


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
