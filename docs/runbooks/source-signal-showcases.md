# Source Signal Showcase Runbook

Use this runbook when a provider response demonstrates an important source-quality problem, such as
sparse tags, typo-prone keywords, noisy recommendations, missing relationships, unstable IDs, or
fields that are useful only after normalization.

## Purpose

Source signal showcases make schema and taxonomy work repeatable. They capture why a provider value
is useful, weak, noisy, or dangerous to treat as canonical before the project turns it into a fixture
or implementation requirement.

## Steps

1. Confirm the provider's current source role in `docs/source-admissibility-and-rate-limits.md`.
2. Query the provider through the approved local access path. Do not print, paste, or commit tokens.
3. Record the provider, endpoint family, entity identifier, date observed, and source role.
4. Summarize only the fields needed to explain the signal quality. Do not commit raw provider
   payloads or large copied metadata.
5. Classify each observed signal:
   - broad but useful as weak evidence;
   - sparse or dead-end;
   - typo or provider-quality issue;
   - structured evidence that should become a relationship or facet;
   - local/runtime-only evidence that must not publish directly.
6. Propose the normalized dataset surface that should eventually carry the useful signal, such as a
   facet, relationship, source-material evidence row, judgment candidate, retrieval text input, or
   derived similarity candidate.
7. Link the showcase from any relevant docs or backlog items.
8. Append a decision to `docs/decisions.jsonl` only when the showcase changes project policy,
   artifact shape, or workflow expectations.

## Validation

For documentation-only changes, run:

```sh
docker compose run --rm app uv run pytest tests/test_decision_log.py tests/test_docs_policy.py
```

If the showcase adds fixtures or code, also run the relevant fixture tests and the full suite when
practical.
