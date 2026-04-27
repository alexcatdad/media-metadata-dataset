# V1 Release Candidate Runbook

Use this runbook to build a bounded, local release candidate for `media-metadata-v1`. Do not run
project pipeline tasks on host Python.

## Boundary

This RC is a rehearsal artifact, not a full corpus build and not a Hugging Face publication. It
should include meaningful anime, TV, and movie source paths, source metadata sidecars, release
readiness validation, and an offline publication rehearsal.

The RC should stay bounded enough to run locally and in CI-like Docker conditions. Increase source
counts deliberately and record the chosen scope in the command log or release notes.

## Source Scope

Default bounded RC scope:

- 50 manami anime rows from the pinned local manami release;
- 15 to 25 TVmaze shows chosen by explicit `--show-id` values;
- 15 to 25 Wikidata movies chosen by explicit `--qid` values.

The exact TVmaze IDs and Wikidata QIDs should be resolved before the run and kept in the command
log. Avoid free-text source queries inside the build commands so the RC can be repeated.

## Commands

```sh
docker compose run --rm app mod anime-build \
  --input-path .mod/out/manami-release/anime-offline-database-minified-YYYY-NN.json \
  --limit 50 \
  --output-dir .mod/out/rc-v1-anime-YYYY-MM-DD

docker compose run --rm app mod tvmaze-build \
  --show-id TVMAZE_ID \
  --show-id TVMAZE_ID \
  --output-dir .mod/out/rc-v1-tvmaze-YYYY-MM-DD

docker compose run --rm app mod wikidata-movie-build \
  --qid QID \
  --qid QID \
  --output-dir .mod/out/rc-v1-wikidata-movie-YYYY-MM-DD

docker compose run --rm app mod v1-core-artifact \
  --input-path .mod/out/rc-v1-anime-YYYY-MM-DD/metadata-enriched/manami-enriched-metadata.jsonl \
  --input-path .mod/out/rc-v1-tvmaze-YYYY-MM-DD/normalized/tvmaze-normalized.jsonl \
  --input-path .mod/out/rc-v1-wikidata-movie-YYYY-MM-DD/normalized/wikidata-movie-normalized.jsonl \
  --source-snapshot-path .mod/out/rc-v1-anime-YYYY-MM-DD/source-metadata/source-snapshots.jsonl \
  --source-snapshot-path .mod/out/rc-v1-tvmaze-YYYY-MM-DD/source-metadata/source-snapshots.jsonl \
  --source-snapshot-path .mod/out/rc-v1-wikidata-movie-YYYY-MM-DD/source-metadata/source-snapshots.jsonl \
  --provider-run-path .mod/out/rc-v1-anime-YYYY-MM-DD/source-metadata/provider-runs.jsonl \
  --provider-run-path .mod/out/rc-v1-tvmaze-YYYY-MM-DD/source-metadata/provider-runs.jsonl \
  --provider-run-path .mod/out/rc-v1-wikidata-movie-YYYY-MM-DD/source-metadata/provider-runs.jsonl \
  --output-dir .mod/out/rc-v1-core-YYYY-MM-DD

docker compose run --rm app mod validate-release-readiness \
  .mod/out/rc-v1-core-YYYY-MM-DD/media-metadata-v1-manifest.json

docker compose run --rm app mod hf-rehearse-publish \
  .mod/out/rc-v1-core-YYYY-MM-DD/media-metadata-v1-manifest.json \
  --repo-id local/media-metadata-dataset \
  --output-dir .mod/out/rc-v1-hf-rehearsal-YYYY-MM-DD

docker compose run --rm app mod materialize-current-snapshot-surface \
  .mod/out/rc-v1-core-YYYY-MM-DD/media-metadata-v1-manifest.json \
  --job-name local.v1-rc \
  --snapshot-id YYYY-MM-DD \
  --output-dir .mod/out/rc-v1-finalized-YYYY-MM-DD
```

## Validation

```sh
docker compose run --rm app uv run --extra dev ruff check .
docker compose run --rm app uv run --extra dev pyright
docker compose run --rm app uv run pytest
```

## Expected Result

The RC succeeds only if release readiness passes and the offline Hugging Face rehearsal renders a
publish bundle without uploading anything. Generated files under `.mod/out` remain local artifacts
unless a later explicit publication decision approves upload.
