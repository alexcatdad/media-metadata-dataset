# Project Definition Runbook

Use this runbook when changing the project's problem statement, scope, source policy, or other
foundation documents.

## When To Use

- A product or dataset goal changes.
- A new media domain is proposed.
- A source role or admissibility rule changes.
- A new canonical model, publication policy, or execution boundary is proposed.
- A working note needs to become durable project context.

## Steps

1. Read `docs/decisions.jsonl` first. Accepted decisions outrank README prose and working notes.
2. Update the durable document that future contributors should read first.
3. Add or update README links when a new durable document is created.
4. Append an accepted, rejected, or superseded decision to `docs/decisions.jsonl` for material
   project-definition changes.
5. Keep scope language explicit about what is in scope, out of scope, and evidence-only.
6. Run the docs and decision-log tests inside Docker/Compose.

## Validation

```sh
docker compose run --rm app uv run pytest tests/test_decision_log.py tests/test_docs_policy.py
```

For broader policy changes, run the full test suite:

```sh
docker compose run --rm app uv run pytest
```
