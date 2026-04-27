# Derived Similarity Runbook

Use this runbook when designing or changing post-v1 `similarity_candidates` contracts, recipes, or
fixtures.

## Goals

- Keep similarity work post-v1 and separate from source ingest.
- Generate candidates from existing versioned artifact surfaces.
- Make recipe changes auditable and recomputable without source re-ingest.
- Preserve the boundary that downstream consumers own final ranking, vibe interpretation, and
  presentation.

## Contract Rules

`similarity_candidates` is a derived surface. It may use publishable, versioned outputs from core,
profile, relationship, facet, retrieval, embedding, judgment-materialization, evidence, provenance,
policy, and manifest surfaces.

The current executable contract is `DERIVED_TABLE_CONTRACTS["similarity_candidates"]`. It is a
post-v1 derived table contract, not a v1 readiness requirement, and it is intentionally absent from
the required core/profile v1 artifact tables.

Do not read raw source payloads, private experiment data, credentials-only provider data, or
runtime-only values directly into public candidate rows. If an input is useful for similarity, first
make it available through an accepted versioned surface and publishability gate.

Current public inputs are the implemented core/profile surfaces, relationship/evidence surfaces,
facets, provenance/source metadata, manifest metadata, and future retrieval/embedding surfaces once
they pass publishability. LLM materialized sidecars are not public similarity inputs until a later
accepted policy decision promotes them from private experiment output.

Candidate rows must record:

- source and target entity IDs;
- similarity recipe version;
- input surface versions or manifest references;
- recipe-local scores or dimensions;
- dimensional confidence profile and optional recipe-produced confidence tier;
- evidence, provenance, and quality flags;
- generation timestamp.

## Workflow

1. Confirm the relevant decisions in `docs/decisions.jsonl`, especially D-0028, D-0034, and D-0042.
2. List every intended input surface and version dependency before proposing fields or scoring.
3. Check that inputs are existing surfaces or explicitly future versioned surfaces, not source
   ingest shortcuts.
4. Define score dimensions as recipe-local signals. Do not describe them as universal
   recommendation quality or global confidence.
5. Define recompute behavior: which recipe or input changes require rebuilding
   `similarity_candidates`, and which source-ingest work is not required.
6. Update `docs/dataset-surfaces.md`, `docs/decisions.jsonl`, and `docs/backlog.jsonl` when the
   contract changes.
7. Run focused validation inside Docker:

```sh
docker compose run --rm app --extra dev pytest tests/test_backlog.py tests/test_decision_log.py tests/test_docs_policy.py
```

8. Commit and push the branch.

## Non-Goals

- Do not make `similarity_candidates` a v1 readiness gate.
- Do not implement a recommendation product or final ranking policy in this repo.
- Do not model `vibes` as canonical dataset fields.
- Do not replace source, evidence, relationship, facet, retrieval, embedding, judgment, provenance,
  or manifest surfaces with one similarity score.
