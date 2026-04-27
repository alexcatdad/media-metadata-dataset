# Release Readiness Runbook

Use this runbook before copying, finalizing, or publishing a compiled artifact bundle. Do not run
project pipeline tasks on host Python.

## Command

```sh
docker compose run --rm app mod validate-release-readiness \
  .mod/out/milestone-v1-core-YYYY-MM-DD/media-metadata-v1-manifest.json
```

## Scope

The gate is artifact-aware. For `media-metadata-v1`, it requires:

- current publishability policy validation;
- `media-metadata-v1` artifact and dataset-line identity;
- anime, TV, and movie domains;
- source coverage for `manami`, `tvmaze`, and `wikidata`;
- release-grade source snapshot IDs instead of `*:unspecified`;
- required v1 core/profile tables, including `source_snapshots` and `provider_runs`, and matching
  manifest `files`;
- readable Parquet files with row counts and columns matching table contracts;
- non-null required columns;
- every `source_records` and `provenance` source snapshot/provider run reference resolves to
  `source_snapshots` and `provider_runs`;
- at least one meaningful entity/title/external-ID/source-record/profile path per v1 domain.

## Validation

```sh
docker compose run --rm app uv run --extra dev ruff check .
docker compose run --rm app uv run --extra dev pyright
docker compose run --rm app uv run pytest
```
