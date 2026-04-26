# Publishability Policy Runbook

Use this runbook when changing source policy, source field policy, artifact policy, or release
publishability gates.

## Scope

This lane owns backlog items `B-0005` and `B-0006`.

Contract sources:

- `docs/source-admissibility-and-rate-limits.md`
- decisions `D-0004`, `D-0027`, `D-0043`, and `D-0044`
- `docs/dataset-surfaces.md`

## Workflow

1. Start from latest `origin/main` and work on `codex/publishability-policy`.
2. Update typed policy models in `src/media_offline_database/publishability.py`.
3. Keep policy changes versioned with:
   - `SOURCE_POLICY_VERSION`
   - `SOURCE_FIELD_POLICY_VERSION`
   - `ARTIFACT_POLICY_VERSION`
   - `PUBLISHABILITY_POLICY_VERSION`
4. Wire public artifact writers through `validate_artifact_inputs`.
5. Ensure public manifests record `publishability.policy_versions` and `validated_uses`.
6. Ensure release paths call `validate_manifest_publishability` before copying or uploading bundles.
7. Add regression tests for missing policy, restricted source inputs, retrieval text inputs,
   embedding inputs, and release manifest validation.

## Validation

Run validation inside Docker/Compose only:

```sh
docker compose run --rm app pytest tests/test_publishability.py
docker compose run --rm app pytest
docker compose run --rm app ruff check .
docker compose run --rm app pyright
```

Do not run project pipeline tasks directly on host Python.

## Release-Blocking Rules

Treat these as release blockers:

- public Parquet inputs without source field policy;
- restricted, local-only, runtime-only, paid-experiment-only, or blocked inputs entering public
  Parquet;
- restricted inputs entering retrieval text, embeddings, or LLM judgment prompts;
- manifests without the current publishability policy versions;
- upload or snapshot-finalization paths that bypass manifest publishability validation.
