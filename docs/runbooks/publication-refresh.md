# Publication Refresh Runbook

Use this runbook for publication-refresh work that spans Hugging Face publication, supported
release tags, compatibility checks, and checkpoint continuity.

Project pipeline commands run through Docker/Compose, not host Python.

## Preconditions

- `HF_TOKEN` is available in `.env` or the runner secret store.
- The target Hugging Face dataset repo is explicit through `--repo-id` or `HF_NAMESPACE` plus
  `HF_DATASET_REPO`.
- The artifact manifest was produced by a containerized build command.

## Publish A Checkpoint

```sh
docker compose run --rm app mod hf-publish /path/to/manifest.json \
  --repo-id namespace/media-metadata-dataset-test \
  --checkpoint-path checkpoints/manual
```

For a supported release snapshot, create a Hugging Face tag against the captured commit:

```sh
docker compose run --rm app mod hf-publish /path/to/manifest.json \
  --repo-id namespace/media-metadata-dataset-test \
  --checkpoint-path checkpoints/manual \
  --release-tag v0.1.0
```

The local manifest is updated with `huggingface.repo_id`, `huggingface.commit_sha`, and
`huggingface.revision`. Consumers that need exact reproducibility should pin the full commit SHA.
Consumers that need a supported release line may pin the release tag.

## Run A Checkpointed Refresh

```sh
docker compose run --rm app mod manami-refresh \
  --input-path /path/to/anime-offline-database.json \
  --repo-id namespace/media-metadata-dataset-test \
  --batch-size 100
```

Refresh state lives in the Hugging Face dataset repo at `state/refresh-state.json`. Runner cache is
not continuity. Each job records the source snapshot, stable source-order offset basis, next offset,
last completed item key, and last checkpoint path.

## Finalize Current Snapshot

```sh
docker compose run --rm app mod hf-finalize-current /path/to/manifest.json \
  --repo-id namespace/media-metadata-dataset-test \
  --job-name anime.manami.default \
  --snapshot-id 2026-14
```

Add `--release-tag v0.1.0` when the finalized snapshot is a supported release.

## Validate Snapshot Compatibility

```sh
docker compose run --rm app mod validate-snapshot-compatibility \
  /path/to/previous-manifest.json \
  /path/to/current-manifest.json
```

The command exits nonzero when a core compatibility error is found. Profile, derived, and
experimental findings are reported so they can become manifest notices or release notes.
