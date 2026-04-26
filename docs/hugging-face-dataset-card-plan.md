# Hugging Face Dataset Card Plan

This is the planned structure for the Hugging Face dataset card. The card should describe published
files and consumer expectations, not an API, hosted app, DuckDB artifact, graph browser, RAG
service, or recommendation product.

## Card Goals

- Make the artifact contract obvious: Parquet tables plus a manifest.
- Tell consumers how to pin snapshots through Hugging Face commits or tags.
- Explain source policy, publishability, and limitations without implying redistribution rights
  from credentials or public access.
- Show John and Alex style downstream use cases while keeping ranking, UI, personalization, and
  serving outside this repo.

## Proposed Card Structure

### Dataset Summary

State that this is an open, non-commercial dataset compiler output for narrative screen media
discovery. It publishes reusable dataset artifacts for anime, TV, and movies with identity links,
relationship edges, provenance, safe factual metadata, retrieval-ready surfaces, embeddings, and
auditable judgments where allowed.

Required wording:

> This dataset is distributed as Parquet tables plus a manifest. It is not an API, hosted service,
> application, DuckDB database artifact, recommendation engine, graph browser, or RAG serving layer.

### Scope

In scope:

- anime as a first-class domain;
- TV;
- movies;
- identity and source-link graphs;
- relationship graphs;
- provenance, evidence, confidence, facets, retrieval text, embeddings, and judgments when
  publishability policy allows them.

Out of scope:

- music;
- games, podcasts, and books as full browse domains;
- copied closed-provider metadata;
- hosted APIs, direct applications, search endpoints, consumption layers, or personalized
  recommendations.

### Artifact Layout

List the manifest and table families:

- `manifest.json`;
- core tables such as `entities`, `titles`, `external_ids`, `relationships`,
  `relationship_evidence`, `facets`, and `provenance`;
- profile tables such as `anime_profile`, `tv_profile`, and `movie_profile`;
- derived tables such as `retrieval_text`, `embeddings`, and `llm_judgments`;
- experimental tables only when the manifest marks them as experimental.

Explain that consumers should read the manifest first and then load the referenced Parquet files.
Consumers may load those files into DuckDB, a search index, a graph store, a notebook, or an
application database, but those choices are downstream.

### Versioning And Snapshot Pinning

Use this language:

- Hugging Face Dataset Hub is the publication and continuity host.
- `main` is the moving latest pointer.
- Supported releases are tagged.
- Exact consumers should pin a full Hugging Face commit SHA recorded in the manifest.
- The manifest bridges dataset version, schema versions, source snapshots, recipe versions, policy
  versions, row counts, and the physical Hugging Face revision.

### Source Policy And Publishability

Include the source role vocabulary exactly:

- `BACKBONE_SOURCE`
- `ID_SOURCE`
- `LOCAL_EVIDENCE`
- `RUNTIME_ONLY`
- `PAID_EXPERIMENT_ONLY`
- `BLOCKED`

Required wording:

> Credentials, API tokens, public endpoints, and local access authorize reading only when allowed by
> the provider. They do not imply redistribution rights.

Explain that source policy, field policy, transform policy, and artifact policy decide what can
appear in public Parquet tables, retrieval text, embeddings, judgments, and manifests.

### Intended Use

Describe uses as downstream possibilities:

- building search or discovery tools;
- loading a relationship graph;
- building a recommendation application;
- creating a RAG or vector-search index;
- inspecting provenance and confidence for media facts and relationships.

Avoid wording that says the dataset itself recommends what to watch. The card should say that the
dataset exposes reusable surfaces and downstream consumers own interpretation, ranking,
personalization, UI, and serving.

### Consumer Examples

Link to `docs/consumer-examples.md` and summarize:

- John loads the manifest and Parquet files, resolves `The Expanse`, and combines relationships,
  facets, embeddings, and confidence in his own app.
- Alex or an external anime tool resolves `Golden Time` and facet queries such as adult university
  contemporary anime, then ranks candidates externally.

### Limitations

Cover these points:

- The project is in architecture/bootstrap until the v1 source paths and schema contracts are
  implemented.
- V1 is not anime-only; it requires meaningful anime, TV, and movie source paths.
- Some records may be partially enriched. Consumers should inspect enrichment status.
- Source coverage depends on provider rights, publishability policy, and rate limits.
- LLM outputs are judgments and must pass materialization gates before becoming queryable facets or
  relationships.
- Confidence is dimensional and recipe-specific; do not compare tiers as one universal score.

### Licenses And Attribution

Use a conservative placeholder until publishable source policy and dataset licensing are finalized:

> License and attribution requirements are snapshot-specific and are recorded in the manifest and
> source policy surfaces. Consumers are responsible for preserving required attribution from the
> published snapshot.

Do not claim a broad permissive license until source composition and rights evidence support it.

### Citation

Include a placeholder citation section that tells users to cite the Hugging Face dataset repo,
release tag or commit SHA, and manifest dataset version.

## Pre-Publish Checklist

- Manifest exists and validates.
- Manifest records Hugging Face repo ID and full commit SHA for the publish.
- Table paths, row counts, schema versions, policy versions, source coverage, and recipe versions
  are recorded.
- Experimental surfaces are marked.
- Source and field publishability checks passed.
- Dataset card does not describe an API, app, DuckDB artifact, or recommendation product.
- Known limitations and attribution requirements match the published manifest.
