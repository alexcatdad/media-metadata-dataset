# Schema Manifest Lane Runbook

Use this runbook for backlog items B-0001 through B-0004.

## Scope

Implement and maintain the artifact manifest schema, shared core Parquet table contracts, domain
profile contracts, and the identity-change surface. Keep this lane limited to file-based dataset
contracts: Parquet tables plus a manifest. Do not add a hosted API, GraphQL endpoint, application
query layer, or DuckDB artifact as a project-owned output.

## Workflow

1. Start from latest `main` and work on `codex/schema-manifest`.
2. Read `docs/decisions.jsonl` entries D-0030, D-0037, D-0038, D-0039, D-0040, D-0041, D-0042, and
   D-0043 before changing contracts.
3. Update `docs/backlog.jsonl` statuses as each backlog item moves through `todo`, `in_progress`,
   and `done`.
4. Add or update typed contracts and fixtures for manifest, core tables, profiles, and identity
   changes.
5. Validate through Docker/Compose only:
   `docker compose run --rm app --extra dev pytest tests/test_schema_manifest_contracts.py tests/test_backlog.py tests/test_decision_log.py`.
6. Run the lane quality gates through Docker/Compose:
   `docker compose run --rm app --extra dev ruff check src tests` and
   `docker compose run --rm app --extra dev pyright`.
7. Commit and push the branch after coherent slices of work.

## Audit Notes

- Decisions go in `docs/decisions.jsonl`; keep it append-only.
- Backlog remains JSONL so agents and developers can resume from stable IDs.
- Manifest examples must not contain credentials, restricted source values, or private paths.
