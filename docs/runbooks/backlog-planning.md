# Backlog Planning Runbook

Use this runbook when adding, splitting, closing, or reprioritizing implementation work in
`docs/backlog.jsonl`.

## Goals

- Keep implementation work splittable across developers or agents.
- Link each backlog item to accepted decisions and source docs.
- Preserve enough context for a later contributor to resume without reading the whole conversation.

## Backlog Format

The backlog is append-friendly JSONL. Each line is one object with:

- `id`: stable backlog ID such as `B-0001`.
- `status`: `todo`, `in_progress`, `blocked`, `done`, or `deferred`.
- `priority`: `P0`, `P1`, or `P2`.
- `lane`: work lane such as `schema-manifest`, `publishability`, or `llm-judgment`.
- `title`: short task name.
- `summary`: plain-language task description.
- `depends_on`: backlog IDs that should land first.
- `decision_refs`: decision IDs from `docs/decisions.jsonl`.
- `doc_refs`: repository docs that explain the context.
- `deliverables`: concrete artifacts expected from the task.
- `acceptance_criteria`: checks that define done.

## Workflow

1. Read `docs/decisions.jsonl` and `docs/dataset-surfaces.md` before creating new work.
2. Add or update backlog items in `docs/backlog.jsonl`.
3. Keep tasks small enough for a developer to own without broad merge conflicts.
4. Prefer dependencies over overloaded task descriptions.
5. Add a decision log entry when the backlog introduces a new project-management convention or
   changes a major implementation direction.
6. Run the backlog and docs validation tests inside Docker:

```sh
docker compose run --rm app uv run pytest tests/test_backlog.py tests/test_decision_log.py tests/test_docs_policy.py
```

7. Commit and push the backlog update.

## Lane Guidance

- `schema-manifest`: table contracts, manifest, compatibility, identity changes.
- `publishability`: source policy, field policy, artifact policy, leak prevention.
- `ingest-normalization`: source adapters, source snapshots, identity normalization.
- `relationships-taxonomy`: relationship types, evidence, deterministic extraction.
- `llm-judgment`: judgment schemas, prompts, materialization, benchmark fixtures.
- `publication-refresh`: Hugging Face publish, tags, snapshots, refresh state.
- `docs-decisions`: docs, examples, dataset card, decision capture.
- `derived-similarity`: post-v1 similarity candidate recipes.

