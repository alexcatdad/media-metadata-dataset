# Media Metadata Dataset

An open, non-commercial dataset compiler for narrative screen media discovery.

The project is in architecture/bootstrap stage. The current goal is to produce reusable,
versioned datasets for anime, TV, and movies with source links, safe factual metadata, identity
cross-references, relationship edges, embeddings, provenance, and auditable LLM-assisted judgments.

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

Out of scope for now:

- music;
- games, podcasts, and books as full browse domains;
- copying closed provider metadata into public datasets;
- hosted APIs or always-on services;
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
```

## Source Policy

Provider credentials grant access, not redistribution rights. Each source must be classified as one
of:

- `BACKBONE_SOURCE`
- `ID_SOURCE`
- `LOCAL_EVIDENCE`
- `RUNTIME_ONLY`
- `BLOCKED`

See [`docs/source-admissibility-and-rate-limits.md`](docs/source-admissibility-and-rate-limits.md).

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
tests/                       Smoke and policy tests
docs/                        Decision log and source policy
.github/workflows/           GitHub Actions CI
.woodpecker/                 Woodpecker CI
```
