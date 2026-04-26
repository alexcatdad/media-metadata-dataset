# Ingest Normalization Runbook

Use this runbook for work on backlog items B-0007 through B-0010.

## Boundary

Do not run project pipeline tasks on host Python. Use Docker Compose for validation and any future
adapter commands.

Allowed host commands for this lane are limited to repository inspection and source control, such as
`git`, `rg`, and reading files.

## Source Path Plan

The locked v1 source paths are:

| Domain | Source path | Role | Status | Public field path |
|---|---|---|---|---|
| anime | manami anime-offline-database release assets | `BACKBONE_SOURCE` | locked | release-backed anime titles, crossrefs, related anime, type, episodes, season, status, and tags subject to field policy |
| TV | TVmaze show path | `BACKBONE_SOURCE` | waiting on policy/schema fixtures | TVmaze IDs, URLs, titles, status, dates, runtime, genres, network/web channel, and profile fields allowed by CC BY-SA policy |
| movie | Wikidata movie graph | `BACKBONE_SOURCE` | waiting on policy/schema fixtures | Wikidata QIDs, labels, aliases, publication dates, broad type facts, external IDs, adaptation links, and franchise links under CC0 |

Anime TV series and anime movies do not count as the TV or movie source paths for v1.

TMDB, IMDb, OMDb, Trakt, Simkl, TheTVDB, and JustWatch may help matching or runtime lookup only
where their current role allows it. Do not publish restricted fields from those sources.

## Snapshot Metadata Contract

Every adapter or normalization path should be able to produce:

- `source_snapshots`: source ID, role, snapshot kind, source/fetch timestamps, policy versions,
  record counts, content hash, and manifest URI where applicable.
- `provider_runs`: adapter name/version, started/finished timestamps, request/cache counts, status,
  auth shape, and secret name references only.
- `source_records`: source record ID, source snapshot ID or provider run ID, source role,
  provisional source-path field class, optional source URL, and optional record hash.

Provider run records must not expose tokens, API keys, request authorization headers, or raw secret
values.

The provisional source-path field class is only a planning hint for this lane. Replace it with the
shared source field policy contract before writing public artifacts.

## Commands

Build or refresh the container:

```sh
docker compose build
```

Run focused tests for this lane:

```sh
docker compose run --rm app pytest tests/test_ingest_normalization.py tests/test_sources.py tests/test_docs_policy.py
```

Run the standard validation gates before pushing:

```sh
docker compose run --rm app ruff check .
docker compose run --rm app pyright
docker compose run --rm app pytest
```

## B-0009 And B-0010 Gate

Do not implement public TV/movie artifact writers until B-0001 through B-0006 provide manifest,
core/profile schema, source policy, field policy, artifact policy, and publishability validation
fixtures.

Before turning the TVmaze and Wikidata paths into public artifacts:

1. Add source policy fixtures for the selected source.
2. Add field policy fixtures for each published field.
3. Add artifact policy fixtures for every target column.
4. Validate that summaries, runtime-only fields, and local evidence cannot leak into public
   Parquet, retrieval text, embeddings, judgments, or manifests.
