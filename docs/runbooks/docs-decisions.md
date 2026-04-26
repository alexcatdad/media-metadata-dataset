# Docs-Decisions Runbook

Use this runbook for the `docs-decisions` lane. It exists because documentation and decision-lane
work usually spans multiple CLI commands and should be resumable.

## Scope

This lane owns contributor-facing documentation derived from accepted decisions, especially:

- schema documentation from current decisions;
- Hugging Face dataset card planning;
- consumer examples for John and Alex;
- decision-log updates that record important documentation posture changes.

This lane does not implement pipeline code, run project pipeline tasks on host Python, define a
hosted API, create an app, publish a DuckDB artifact, or build a recommendation product.

## Command Surface

Allowed host commands for this lane:

```sh
git fetch origin main
git status --short --branch
git worktree list --porcelain
rg --files
rg -n "B-0019|B-0020|B-0021" docs README.md
sed -n '1,220p' docs/dataset-surfaces.md
git diff -- docs README.md tests
```

Validation must use Docker/Compose for project tooling:

```sh
docker compose run --rm app ruff check .
docker compose run --rm app pyright
docker compose run --rm app pytest
```

When the bind-mounted worktree does not already have dev dependencies installed in `.venv`, pass
the dev extra through the image entrypoint:

```sh
docker compose run --rm app --extra dev ruff check .
docker compose run --rm app --extra dev pyright
docker compose run --rm app --extra dev pytest
```

For docs-only edits, a focused test command is acceptable before the full gates when iteration is
needed:

```sh
docker compose run --rm app --extra dev pytest tests/test_decision_log.py tests/test_backlog.py tests/test_docs_policy.py
```

Do not run project pipeline tasks directly on host Python.

## Steps

1. Start from latest `origin/main`.
2. Create or use the `codex/docs-decisions` branch/worktree.
3. Read `docs/backlog.jsonl` entries for the owned backlog IDs.
4. Read the referenced decisions in `docs/decisions.jsonl`.
5. Edit documentation with the product boundary visible: Parquet plus manifest, not an API, app,
   DuckDB artifact, or recommendation product.
6. Append decision-log entries for important new posture decisions.
7. Update backlog records when deliverables are complete.
8. Validate in Docker/Compose.
9. Commit and push the branch.

## Resume Notes

If interrupted, inspect:

```sh
git status --short --branch
git diff --stat
git diff -- docs README.md
tail -n 5 docs/decisions.jsonl
```

Then continue from the first incomplete backlog deliverable.
