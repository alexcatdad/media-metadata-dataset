# Relationships Taxonomy Runbook

Use this runbook for backlog items in the `relationships-taxonomy` lane.

## Scope

- Start from the latest `main` and work on a `codex/relationships-taxonomy` branch.
- Keep relationship types precise when evidence supports precision.
- Preserve broad `relationship_family` values only as grouping fields.
- Route ambiguous cases to judgment candidates instead of guessing canonical relationships.
- Validate with Docker/Compose only; do not run project pipeline tasks on host Python.

## Implementation Steps

1. Inspect `docs/backlog.jsonl`, `docs/decisions.jsonl`, and `docs/dataset-surfaces.md` for the active backlog item and decision references.
2. Update `src/media_offline_database/relationships.py` for relationship contracts, inverse behavior, evidence references, confidence dimensions, quality flags, and deterministic recipe versions.
3. Update artifact writers so relationship rows expose lightweight evidence, provenance, confidence, quality, family, and recipe fields.
4. Update deterministic source-specific extraction code before changing LLM judgment behavior.
5. Add or update fixture-based tests for precise labels and ambiguous judgment-candidate behavior.
6. Append a decision to `docs/decisions.jsonl` for material implementation choices that future agents need to resume safely.

## Validation

Run validation through the container command surface:

```bash
docker compose run --rm app ruff check .
docker compose run --rm app pyright
docker compose run --rm app pytest
```

For a focused loop, use targeted pytest paths inside the same Docker/Compose surface.
