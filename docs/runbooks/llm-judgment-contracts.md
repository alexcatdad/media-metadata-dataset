# LLM Judgment Contract Runbook

Use this runbook when changing judgment candidate schemas, `llm_judgments` schemas,
materialization recipes, or local LLM prompt fixtures.

## Goals

- Keep LLM outputs as derived judgments, not source metadata.
- Materialize queryable relationship, facet, profile, quality, or confidence outputs only through
  versioned gates.
- Keep local prompt fixtures reproducible and separate from provider benchmark results.

## Workflow

1. Read `docs/decisions.jsonl`, especially D-0029, D-0042, D-0043, and D-0044.
2. Update strict Pydantic contracts for candidates, judgments, confidence profiles, and
   materialization recipes before changing pipeline behavior.
3. Ensure every materialization path validates publishable input refs, structured output schema,
   evidence refs, confidence profile, quality flags, and target surface eligibility.
4. Keep invalid, failed, low-confidence, or unsupported model outputs in judgment artifacts only.
5. Keep candidate, execution, and materialized LLM sidecars marked `public: false` and
   `publishability_status: private_experiment_only` until the full source/field/artifact
   publishability policy layer accepts them as public outputs.
6. Add or update benchmark fixtures under `benchmarks/fixtures/`.
7. Keep relationship judgment fixtures separate from inferred-facet fixtures unless benchmark
   harnesses explicitly support both task shapes.
8. Append an accepted decision when changing the project boundary or materialization policy.

## Validation

Run validation inside Docker/Compose:

```sh
docker compose run --rm app uv run ruff check .
docker compose run --rm app uv run pyright
docker compose run --rm app uv run pytest
```

For a narrower fixture/schema pass:

```sh
docker compose run --rm app uv run pytest tests/test_modeling.py tests/test_llm_enhancement.py tests/test_benchmark_fixtures.py
```
