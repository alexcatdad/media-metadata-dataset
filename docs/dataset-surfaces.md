# Dataset Surfaces

This project publishes data artifacts, not recommendations, APIs, or applications. A downstream
consumer can use the artifacts to build search, recommendation, graph, or RAG experiences.

## V1 Surfaces

V1 should focus on stable, reusable surfaces:

- `entities`: canonical media works with stable dataset IDs.
- `titles`: canonical titles, aliases, original titles, and source-backed title variants.
- `external_ids`: source-specific IDs and URLs.
- `relationships`: source-backed or derived edges between entities.
- `relationship_evidence`: evidence records supporting relationship edges.
- `facets`: normalized searchable attributes such as genre, setting, cast life stage, format,
  themes, duration, and domain-specific profile fields.
- `retrieval_text`: safe, provenance-aware text assembled for search, embeddings, and RAG indexing.
- `embeddings`: recipe-versioned vectors for supported retrieval text or facet bundles.
- `llm_judgments`: auditable model-assisted judgments for ambiguous cases.
- `provenance`: source, field, fetch, and transformation metadata.
- `manifest`: artifact files, row counts, schema versions, recipe versions, and snapshot metadata.

These surfaces should be useful even when some enrichment stages are incomplete.

## V1 Readiness Gate

V1 is cross-domain. Anime can be the first implementation spine and can remain the richest early
domain, but an anime-only artifact is not v1.

To count as v1, the dataset must include at least:

- one meaningful anime source path;
- one meaningful TV source path;
- one meaningful movie source path;
- the shared core surfaces needed to consume those domains through one primary interface;
- domain profile coverage for the fields each included source can publish safely;
- source roles, provider-review evidence, and publishable-field policy for each included source.

Meaningful source path means more than a placeholder domain or empty table. It must ingest or derive
enough publishable records, titles, external IDs, provenance, and domain-appropriate profile data to
exercise the shared core schema for that domain.

Anime TV series and anime movies do not satisfy the required TV and movie source paths. Identifier
stubs, runtime-only lookups, and empty future profile tables also do not satisfy the requirement.

## Progressive Enhancement

V1 should allow partial enrichment. An entity does not need to pass through every enrichment stage
before it can appear in a published snapshot, as long as the artifact clearly reports what is
present, missing, pending, or derived.

Operational stages:

1. Source ingest: admissible source records, source IDs, fetch metadata, and source snapshot IDs.
2. Identity normalization: canonical dataset entities, titles, aliases, and external IDs.
3. Relationship extraction: source-backed or deterministic relationships plus evidence.
4. Facet normalization: direct source tags and fields mapped into normalized query facets.
5. Judgment candidate selection: ambiguous or high-value claims queued for model, human, or complex
   deterministic review.
6. Judgment application: inferred claims stored in judgment surfaces and optionally materialized
   into facets under explicit rules.
7. Retrieval enhancement: retrieval text and embeddings generated from safe, versioned inputs.
8. Derived enhancements: post-v1 tables such as `similarity_candidates`.

Each stage should be additive or recomputable when practical. Later snapshots can add better
evidence, facets, relationships, judgments, embeddings, or derived tables without re-ingesting
sources or rebuilding unrelated base surfaces.

Artifacts should expose enrichment status at useful levels, such as entity, table, recipe, and
snapshot metadata. Downstream consumers should be able to tell whether a record is source-ingested
only, facet-enhanced, judgment-enhanced, embedding-enhanced, or included in a derived enhancement
recipe.

## Shared Core And Domain Profiles

The dataset should expose one shared core interface across media types, plus domain profiles for
fields that only make sense in a specific domain.

The shared core should support cross-domain consumption:

- canonical entity IDs;
- domains such as `anime`, `tv`, and `movie`;
- titles and aliases;
- external source IDs;
- release dates or years where safely available;
- high-level media type and status;
- relationships;
- evidence, provenance, facets, retrieval text, embeddings, judgments, and manifests.

Domain profiles preserve domain-specific taxonomy without forcing every consumer to handle entirely
separate dataset shapes.

Examples:

- `anime_profile`: anime format such as TV, movie, OVA, ONA, or special; anime season/year;
  cour/season shape where available; source demographic; anime-specific relationship hints.
- `tv_profile`: season count, episode count, show status, network/platform, and TV-specific release
  shape where publishable.
- `movie_profile`: runtime, release year/date, collection/franchise hints, and movie-specific
  release shape where publishable.

Cross-domain concepts such as setting, tone, cast life stage, themes, scope, duration, and source
material should generally be modeled as facets when they can apply across domains. Domain-specific
facts should remain in domain profiles when forcing them into the core would make the shared
interface noisy or misleading.

## Tags, Facets, And Judgments

The dataset should keep source tags, normalized facets, and inferred judgments separate.

`source_tags` are provider-supplied labels or lightly normalized source labels. They preserve where
the label came from and should not be treated as the dataset's final taxonomy by themselves.

`facets` are normalized, queryable dataset attributes. They are designed for downstream search and
filtering, such as `educational_setting=university`, `cast_life_stage=adult`, or
`world_setting=contemporary_real_world`.

`judgments` are inferred claims that require interpretation beyond a direct source field or simple
mapping. Examples include narrative closure, large-scale thematic similarity, relationship
classification in ambiguous cases, or other claims produced by model-assisted, human, or complex
deterministic review.

Inferred values must live in a judgment table first. They may later be normalized or materialized
into facets only through explicit materialization rules, confidence thresholds, provenance links,
and recipe versions. This keeps queryable facets useful without hiding which values were inferred.

## Relationship Taxonomy

Relationships are a core value of the dataset. A small or overly generic taxonomy would collapse the
signal that downstream consumers need.

The dataset should use rich, precise relationship types where evidence supports them. Relationship
edges should also expose a broader `relationship_family` so consumers can group precise types
without losing detail.

Examples of relationship families:

- `identity`: same work/entity resolution.
- `continuity`: sequel, prequel, continuation, previous installment.
- `adaptation`: source material, adaptation, alternate adaptation, same source work.
- `variant`: remake, reboot, retelling, alternate cut, compilation.
- `franchise`: shared franchise, shared universe, spinoff.
- `episode_context`: special, OVA/ONA side story, recap, movie tie-in, pilot.
- `similarity`: soft similarity or discovery adjacency, usually post-v1 or derived.
- `uncertain`: insufficient evidence or unresolved classification.

Examples of precise relationship types:

- `same_entity`
- `sequel`
- `prequel`
- `continuation`
- `spinoff`
- `side_story`
- `special`
- `recap`
- `compilation`
- `movie_tie_in`
- `remake`
- `reboot`
- `retelling`
- `alternate_adaptation`
- `adaptation_of`
- `adapted_by`
- `source_material`
- `same_franchise`
- `shared_universe`
- `similar_to`
- `unrelated`
- `uncertain`

Directional relationships should preserve direction where it matters, with inverse mappings or
paired edges where useful. For example, `adaptation_of` and `adapted_by` should not be collapsed
into one ambiguous label if direction can be known. Generic families are acceptable for grouping and
fallback, but they should not replace precise types when evidence supports a richer edge.

## Vibes And Soft Similarity

`Vibes` are consumer-side interpretation, not a deterministic dataset field. A user may describe a
desired feeling in normal prose, such as "adult university romance with a real ending" or "large
scope political space sci-fi." The external application may use an LLM to interpret that prose and
then run RAG, vector search, graph traversal, filters, or a blended ranking strategy against the
dataset.

This project should not store one canonical `vibe` answer or decide the final ranking for such
queries. Its responsibility is to expose enough structured and retrieval-ready information for
consumer systems to build those interpretations:

- normalized facets;
- rich relationships and relationship evidence;
- source tags where publishable;
- retrieval text;
- embeddings;
- judgments and materialized inferred facets where approved;
- provenance and confidence metadata.

The dataset can support vibe-like discovery by making these surfaces complete, explainable, and
queryable. The LLM interpretation of a user's prose query, the RAG prompt, the ranking policy, and
the final recommendation presentation belong to the consuming system.

## Post-V1 Surface: Similarity Candidates

`similarity_candidates` is a post-v1 progressive enhancement. It should not block the v1 dataset,
and it should not require full source re-ingest or rebuilding the base dataset from scratch.

The table should be derived from existing surfaces such as relationships, facets, retrieval text,
embeddings, evidence, and graph distance. Consumers may use it as a candidate list or explanation
input, but they still own final ranking and presentation.

Possible fields:

- `source_entity_id`
- `target_entity_id`
- `recipe_version`
- `score_overall`
- dimension scores such as `score_genre`, `score_setting`, `score_tone`, `score_scope`,
  `score_cast_life_stage`, `score_graph_distance`, and `score_embedding`
- `evidence_refs`
- `generated_at`

## Recompute Contract

Derived surfaces must be recipe-versioned. When a similarity recipe changes, the project accepts the
cost of recomputing the affected derived table. That recomputation should use existing versioned
artifacts wherever possible instead of repeating source fetches or rebuilding unrelated base tables.

This contract keeps expensive or experimental similarity work separate from the durable base
dataset. It also lets downstream consumers choose whether to use a new similarity recipe without
losing access to stable entity, relationship, facet, and provenance data.
