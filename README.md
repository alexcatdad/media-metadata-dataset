# Media Metadata Dataset

An open, non-commercial dataset compiler for narrative screen media discovery.

The project is in architecture/bootstrap stage. The current goal is to produce reusable,
versioned datasets for anime, TV, and movies with source links, safe factual metadata, identity
cross-references, relationship edges, embeddings, provenance, and auditable LLM-assisted judgments.
The project produces data artifacts only; it is not an API, hosted service, application, or
consumption layer.

See [`docs/problem-statement.md`](docs/problem-statement.md) for the durable problem statement.
See [`docs/dataset-surfaces.md`](docs/dataset-surfaces.md) for the intended artifact surfaces.
See [`docs/schema-documentation.md`](docs/schema-documentation.md) for contributor-facing schema
guidance, [`docs/hugging-face-dataset-card-plan.md`](docs/hugging-face-dataset-card-plan.md) for
the dataset card plan, and [`docs/consumer-examples.md`](docs/consumer-examples.md) for file-based
consumer examples.
Downstream-consumer personas:
[`John`](docs/personas/john-downstream-app-developer.md) and
[`Alex`](docs/personas/alex-anime-discovery.md).
The initial PRD is treated as rough intent, not final product direction. Current decisions live in
[`docs/decisions.jsonl`](docs/decisions.jsonl).

## Scope

In scope first:

- anime as a first-class domain;
- TV;
- movies;
- identity and source-link graphs;
- relationship graphs such as sequel, prequel, spinoff, adaptation, source material, remake,
  same franchise, and similarity;
- Hugging Face Dataset publication;
- containerized local/CI execution.

V1 is not considered complete with anime alone. It must include at least one meaningful anime source
path, one meaningful TV source path, and one meaningful movie source path through the shared core
schema.

Out of scope for now:

- music;
- games, podcasts, and books as full browse domains;
- copying closed provider metadata into public datasets;
- hosted APIs or always-on services;
- direct applications or consumption layers;
- user-personalized recommendations.

## Execution Boundary

Do not run project pipeline tasks directly on host Python.

Local development uses this computer as a Docker host. The same image and commands should work in
GitHub Actions and Woodpecker.

```sh
docker compose build
docker compose run --rm app mod --help
docker compose run --rm app ruff check .
docker compose run --rm app pyright
docker compose run --rm app pytest
docker compose run --rm app mod smoke-artifact
docker compose run --rm app mod bootstrap-artifact
docker compose run --rm app mod anime-build --input-path /path/to/anime-offline-database.json --title-contains 'Made in Abyss'
docker compose run --rm app mod openrouter-smoke
```

CI runs a keyless precursor before any provider credentials are needed: image build, CLI smoke,
Ruff, Pyright, focused contract tests, focused dataset tests, and deterministic smoke artifact
generation.

When AI credentials are configured, CI also runs a credentials wiring smoke test. The current GitHub
shape is:

- repository variable: `CLOUDFLARE_ACCOUNT_ID`
- repository secrets: `CLOUDFLARE_API_TOKEN`, `OPENAI_COMPAT_API_KEY`

The current deterministic CI lanes are repo-owned scripts:

```sh
docker compose run --rm app ./scripts/ci/run_contract_tests.sh
docker compose run --rm app ./scripts/ci/run_dataset_tests.sh
docker compose run --rm app ./scripts/ci/run_artifact_smokes.sh
```

A separate GitHub Actions workflow at [`.github/workflows/dataset-refresh.yml`](.github/workflows/dataset-refresh.yml)
owns checkpointed refresh/publish runs. It is intentionally split from deterministic CI:

- manual trigger first via `workflow_dispatch`;
- conservative weekly `schedule` second;
- schedule runs only when repository variable `DATASET_REFRESH_SCHEDULE_ENABLED` is set to `true`;
- refresh state continuity comes from the Hugging Face dataset repo, not from runner cache.

The workflow uses the existing CLI surface:

- `mod manami-refresh` to build one checkpointed batch and publish it;
- `mod hf-state` before and after the run to show persisted checkpoint progress.

Recommended GitHub configuration:

- secret: `HF_TOKEN`
- optional variables:
  - `HF_NAMESPACE`
  - `HF_DATASET_REPO`
  - `DATASET_REFRESH_RELEASE_URL` if the scheduled run should fetch a real release JSON instead of using the tiny built-in fixture
  - `DATASET_REFRESH_REPO_ID`
  - `DATASET_REFRESH_JOB_NAME`
  - `DATASET_REFRESH_BATCH_SIZE`
  - `DATASET_REFRESH_TITLE_CONTAINS`
  - `DATASET_REFRESH_LIMIT`
  - `DATASET_REFRESH_PRIVATE_REPO`

The manual workflow inputs are the preferred first operator surface. The scheduled lane is kept deliberately conservative and falls back to a tiny built-in fixture when no release URL variable is configured, so we can exercise checkpoint/publish continuity without depending on a separate source-download implementation.

## Source Policy

Provider credentials grant access, not redistribution rights. Each source must be classified as one
of:

- `BACKBONE_SOURCE`
- `ID_SOURCE`
- `LOCAL_EVIDENCE`
- `RUNTIME_ONLY`
- `PAID_EXPERIMENT_ONLY`
- `BLOCKED`

See [`docs/source-admissibility-and-rate-limits.md`](docs/source-admissibility-and-rate-limits.md).
See [`docs/runbooks/provider-review.md`](docs/runbooks/provider-review.md) before adding or changing
provider use.
See [`docs/model-selection.md`](docs/model-selection.md) for current free-access model choices.

Canonical published runs should prefer open bulk downloads, public free tiers, and free/open model
inference. Paid or contract access is private experiment-only unless a decision log entry records
rights evidence and approves publication use.

## Local Configuration

Copy `.env.example` to `.env` for local container runs and fill only the credentials needed for the
task at hand.

```sh
cp .env.example .env
```

Never commit real secrets.

## Repository Layout

```text
src/media_offline_database/  Python package and CLI
corpus/                      Tiny checked-in seed corpora for architecture bootstrap
tests/                       Smoke and policy tests
docs/                        Decision log and source policy
.github/workflows/           GitHub Actions CI
.woodpecker/                 Woodpecker CI
```

## Current Build Flow

The current anime build spine is intentionally staged so we can keep improving the dataset without
rewriting the whole pipeline:

1. normalize a scheduled manami snapshot into bootstrap-like JSONL
2. refine generic anime relations with AniList
3. enrich anime metadata such as genres, studios, and creators
4. compile the result into versioned Parquet artifacts plus a manifest

The composed entrypoint is:

```sh
docker compose run --rm app mod anime-build \
  --input-path /path/to/anime-offline-database.json \
  --title-contains 'Made in Abyss'
```

## Checkpointed Refresh State

The dataset continuity layer should live with the published dataset, not inside a CI runner.

- Hugging Face dataset repos hold checkpoint artifacts and `state/refresh-state.json`.
- Hugging Face dataset commits are physical snapshots of the published Parquet artifacts plus
  manifest.
- `main` is the moving latest pointer; supported releases should be tagged.
- Exact consumers should pin a full Hugging Face commit SHA recorded in the manifest.
- Each refresh job records progress by source snapshot plus stable batch offsets.
- Partial checkpoint uploads are allowed; the next run resumes from the last persisted offset for
  that snapshot.

Current commands:

```sh
docker compose run --rm app mod hf-state --repo-id namespace/media-metadata-dataset-test
docker compose run --rm app mod hf-publish /path/to/manifest.json --repo-id namespace/media-metadata-dataset-test
docker compose run --rm app mod manami-refresh \
  --input-path /path/to/anime-offline-database.json \
  --repo-id namespace/media-metadata-dataset-test \
  --batch-size 100
```
