# V1 Core Artifact Runbook

Use this runbook to compile source-backed normalized rows into the v1 shared core and profile
artifact. Do not run project pipeline tasks on host Python.

## Boundary

This command writes local Parquet tables and a manifest only. It does not publish to Hugging Face.

TMDB API data must not be passed into this public v1 writer. TMDB remains local evidence/runtime
validation unless a later accepted decision changes its role.

## Inputs

Use bootstrap-like JSONL seeds produced by accepted backbone source paths:

- manami anime build metadata-enriched seed;
- TVmaze normalized seed;
- Wikidata movie normalized seed.

Release-intended builds should also consume the source metadata sidecars emitted by those build
commands:

- `source-metadata/source-snapshots.jsonl`
- `source-metadata/provider-runs.jsonl`

## Command

```sh
docker compose run --rm app mod v1-core-artifact \
  --input-path .mod/out/milestone-anime-build-YYYY-MM-DD/metadata-enriched/manami-enriched-metadata.jsonl \
  --input-path .mod/out/milestone-tvmaze-build-YYYY-MM-DD/normalized/tvmaze-normalized.jsonl \
  --input-path .mod/out/milestone-wikidata-movie-build-YYYY-MM-DD/normalized/wikidata-movie-normalized.jsonl \
  --source-snapshot-path .mod/out/milestone-anime-build-YYYY-MM-DD/source-metadata/source-snapshots.jsonl \
  --source-snapshot-path .mod/out/milestone-tvmaze-build-YYYY-MM-DD/source-metadata/source-snapshots.jsonl \
  --source-snapshot-path .mod/out/milestone-wikidata-movie-build-YYYY-MM-DD/source-metadata/source-snapshots.jsonl \
  --provider-run-path .mod/out/milestone-anime-build-YYYY-MM-DD/source-metadata/provider-runs.jsonl \
  --provider-run-path .mod/out/milestone-tvmaze-build-YYYY-MM-DD/source-metadata/provider-runs.jsonl \
  --provider-run-path .mod/out/milestone-wikidata-movie-build-YYYY-MM-DD/source-metadata/provider-runs.jsonl \
  --output-dir .mod/out/milestone-v1-core-YYYY-MM-DD
```

`--source-snapshot-id source=snapshot` remains available as a compatibility fallback. Builds with
`*:unspecified` snapshot IDs are acceptable smoke runs, but they are not release-ready.

## Release Readiness

```sh
docker compose run --rm app mod validate-release-readiness \
  .mod/out/milestone-v1-core-YYYY-MM-DD/media-metadata-v1-manifest.json
```

The readiness gate validates the v1 manifest identity, publishability policy, required anime/TV/movie
source coverage, source snapshot IDs, manifest/table/file consistency, physical Parquet row counts,
required columns, source snapshot/provider run joinability, and meaningful per-domain rows before
current materialization or Hugging Face publication.

## Local Current Snapshot

```sh
docker compose run --rm app mod materialize-current-snapshot-surface \
  .mod/out/milestone-v1-core-YYYY-MM-DD/media-metadata-v1-manifest.json \
  --job-name local.v1-core.milestone \
  --snapshot-id YYYY-MM-DD \
  --output-dir .mod/out/milestone-v1-core-finalized-YYYY-MM-DD
```

## Validation

```sh
docker compose run --rm app uv run --extra dev ruff check .
docker compose run --rm app uv run --extra dev pyright
docker compose run --rm app uv run pytest
```

## Expected Tables

- `entities`
- `titles`
- `external_ids`
- `relationships`
- `relationship_evidence`
- `facets`
- `provenance`
- `source_snapshots`
- `provider_runs`
- `source_records`
- `anime_profile`
- `tv_profile`
- `movie_profile`

The manifest must include source coverage for `manami`, `tvmaze`, and `wikidata` before a local
cross-domain milestone counts as complete.
