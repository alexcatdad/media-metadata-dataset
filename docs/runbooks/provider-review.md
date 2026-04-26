# Provider Review Runbook

Use this runbook before adding a new source, changing a source role, expanding fields from an
existing source, or changing how provider data is published.

## Purpose

The project depends on public and authorized data providers that already do valuable work collecting
media information. Our goal is to collate admissible information into reusable dataset artifacts,
not to bypass provider terms, scrape around access controls, or copy closed databases.

## Steps

1. Identify the exact provider surface: bulk dump, public API, authenticated API, generated export,
   web page, partner endpoint, or local-only evidence.
2. Read the current terms of service, API terms, license, attribution rules, rate-limit docs, cache
   rules, and redistribution language.
3. Record evidence links in `docs/source-admissibility-and-rate-limits.md`.
4. Classify the source as `BACKBONE_SOURCE`, `ID_SOURCE`, `LOCAL_EVIDENCE`, `RUNTIME_ONLY`,
   `PAID_EXPERIMENT_ONLY`, or `BLOCKED`.
5. Define publishable fields separately from local-only fields.
6. Define rate limits, cache behavior, attribution requirements, and refresh cadence.
7. Treat credentials or tokens only as access authorization. They do not imply redistribution rights.
8. Add tests or contract checks when a provider adapter or benchmark contract is introduced.
9. Append a decision to `docs/decisions.jsonl` when the source role, publication posture, or
   canonical use changes.

## Review Cadence

- Review provider terms before first integration.
- Re-review before first public dataset release.
- Re-review when a provider changes terms, API docs, rate limits, licensing, auth model, or export
  shape.
- Re-review any source that has not been checked recently before promoting it to canonical use.

## Validation

```sh
docker compose run --rm app uv run pytest tests/test_decision_log.py tests/test_docs_policy.py
```

For provider adapter changes, run the relevant contract tests and the full suite when practical:

```sh
docker compose run --rm app uv run pytest
```
