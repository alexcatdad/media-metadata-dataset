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
- `provenance`: separate joinable source, fetch, policy, and transformation metadata.
- `manifest`: artifact files, row counts, schema versions, recipe versions, and snapshot metadata.

These surfaces should be useful even when some enrichment stages are incomplete.

## Artifact Format Contract

The canonical published dataset is a set of Parquet tables plus a manifest. Downstream systems
should consume the dataset by reading the manifest and loading the referenced Parquet artifacts.

The manifest should describe artifact paths, table names, schema versions, row counts, snapshot
metadata, recipe versions, source coverage, and enrichment status. Parquet tables should carry the
durable surfaces that external applications, notebooks, search indexes, graph loaders, or RAG
pipelines can ingest.

This project should not publish a hosted API, GraphQL endpoint, application-specific query service,
or DuckDB database artifact as the consumption contract. Consumers can choose to load the Parquet
artifacts into DuckDB, a database, a graph store, a search index, or an application-specific format,
but those are downstream implementation choices.

JSONL remains appropriate for append-only project records such as decisions, logs, fixtures, or
debug traces. It is not the primary dataset consumption format.

## Hugging Face Publication And Versioning

The preferred public host is Hugging Face Dataset Hub. It is the publication and continuity host
for dataset artifacts, not a query layer owned by this project.

Each publish to the Hugging Face dataset repo should be treated as a physical snapshot commit.
`main` is the moving latest pointer. Supported releases should be tagged, such as `v0.1.0` or
`v1.0.0`, so consumers can pin to a stable revision. Consumers that need exact reproducibility
should pin the full Hugging Face commit SHA rather than relying on `main`.

The manifest should record artifact paths, schema versions, source snapshot IDs, recipe versions,
row counts, published timestamp, and compatibility notes. Publication tooling returns the full
Hugging Face commit SHA for exact pinning and can create supported release tags. The manifest does
not try to contain the SHA of the commit that contains itself; that self-referential contract is not
stable on Git-backed dataset hosts.

Do not duplicate every historical snapshot as dated folders on `main`. The current branch should
contain the current Parquet tables and current manifest; Hugging Face Git history, tags, and commit
SHAs provide older snapshot identities.

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

Human review is a manual intervention path, not a required scheduled pipeline gate. The dataset
should be able to run scheduled refresh and enhancement jobs without waiting on human approval.
Manual corrections or reviews can still be captured as explicit judgment or correction artifacts
when they exist.

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
- Future `book_profile`: source-material work metadata if and when books become a full domain.

Cross-domain concepts such as setting, tone, cast life stage, themes, scope, duration, and source
material should generally be modeled as facets when they can apply across domains. Domain-specific
facts should remain in domain profiles when forcing them into the core would make the shared
interface noisy or misleading.

Books and source material can be represented as relationship evidence in v1. They should not become
a full browse domain until a later accepted decision promotes books and defines a meaningful source
path, profile surface, provider review, and progressive enhancement plan.

## Schema Compatibility Tiers

The shared core schema is the stable public contract across snapshots within a major dataset
version. It should remain backward-compatible so downstream consumers can build one interface across
anime, TV, and movies.

Within a major version, shared core changes should be additive and safe to ignore. Do not remove
core fields, change core field meanings, or change core field types in a breaking way. New core
fields should be nullable or defaultable. Breaking shared-core changes require a new major schema or
dataset version and a manifest compatibility notice.

Domain profiles and extended surfaces can evolve faster than the shared core, but they must not
break silently. Each profile or extension should declare its own schema or recipe version in the
manifest. Breaking profile changes are allowed when explicitly versioned and documented, and
consumers should be able to ignore unknown profile fields or skip unsupported profile versions.

Compatibility tiers:

- `core`: stable and backward-compatible within a major version.
- `profile`: independently versioned per domain; additive changes preferred, breaking changes
  allowed with explicit version bumps and manifest notices.
- `derived`: recipe-versioned and recomputable; breaking changes allowed with manifest notices.
- `experimental`: no compatibility guarantee; must be clearly marked as experimental or unstable.

Snapshot compatibility validation compares manifests before release. Core table removal or core
major-schema movement is an error. Profile and derived version movement is reported as a warning so
the manifest or release notes can declare the change. Experimental surfaces are reported
informationally and carry no compatibility guarantee.

## Entity Identity Contract

Entity IDs are durable within a dataset line. Once an `entity_id` is published, it must not be
reused for a different conceptual work. Downstream consumers should be able to store IDs, join
against them, and resolve older IDs forward through explicit identity-change metadata.

Normal identity corrections should be modeled rather than hidden:

- If two published entities are later found to be the same work, keep one canonical entity ID and
  redirect or merge the other ID into it.
- If one published entity is later found to contain multiple works, keep the old ID as deprecated or
  ambiguous and mint new canonical IDs for the split works.
- If an entity was published in error, do not reuse its ID. Mark it as deprecated, withdrawn, or
  superseded with an explicit reason.
- Preserve identity-change history so consumers can migrate older references.

The artifact contract should include an identity-change surface or manifest-linked table for merges,
splits, redirects, deprecations, withdrawals, and supersessions. Identity changes should include old
ID, new ID or IDs where applicable, change type, evidence or reason, effective snapshot, and
provenance.

ID stability applies within a valid dataset line. If implementation work or later evidence shows
that the identity model or core premise is fundamentally broken, the project may start a new dataset
line, repository, or version family instead of forcing compatibility with the broken premise. The
old dataset line should remain published for existing consumers, while new development moves to the
corrected line.

## Provenance, Evidence, And Confidence

Provenance should be available as separate joinable artifact surfaces, not inline field-level
metadata by default. Core consumption tables should stay clean and should expose practical trust
signals such as confidence, evidence count, conflict status, quality flags, evidence IDs, provenance
IDs, and recipe versions.

The intended consumer-facing signal is usually confidence or evidence quality, not a full source
lineage trail. A downstream application can decide whether `confidence`, `evidence_count`,
`conflict_status`, or `quality_flags` are enough for its UI, and can join into provenance or
evidence tables only when it needs audit or debugging detail.

Examples of separate supporting surfaces:

- `source_records`
- `source_snapshots`
- `provider_runs`
- `evidence`
- `provenance`
- `recipe_runs`

Source snapshot surfaces should use one normalized contract across adapters:

- `source_snapshots`: source ID, source role, snapshot kind, source/fetch timestamps, fetch window,
  policy versions, record counts, content hash, and manifest URI where applicable.
- `provider_runs`: adapter name/version, source ID, optional source snapshot ID, timestamps,
  request/cache counts, status, auth shape, and secret name references only.
- `source_records`: source record ID, source snapshot ID or provider run ID, source role,
  provisional source-path field class, optional source URL, and optional source record hash.

Every ingested row should be able to join to a source snapshot or provider run. Provider run records
must not expose secret values, tokens, authorization headers, or copied restricted payload fields.
The provisional source-path field class is a planning hint only and must be replaced by the shared
field-policy contract before public artifact writing.

Field-level provenance is not required by default. It should be reserved for exceptional audit,
debug, or conflict-resolution surfaces where the extra complexity has clear value. The default
artifact contract is row-level lightweight references plus separate provenance/evidence tables.

Confidence should not be represented as one universal normalized score. Different claims need
different confidence context: a title match, relationship type, normalized facet, LLM judgment,
identity merge, and embedding-derived candidate are not directly comparable.

Confidence should be dimensional and recipe-specific. Core tables may expose a compact
`confidence_tier`, such as `high`, `medium`, `low`, or `unknown`, but that tier must be produced by
an explicit recipe and should not pretend to be mathematically comparable across all surfaces.

Useful confidence dimensions include:

- `source_role`: the classified role of the source that contributed the claim.
- `evidence_strength`: whether the claim is direct, source-declared, multi-source, derived, or
  inferred.
- `agreement_status`: whether evidence is confirmed, conflicting, ambiguous, or unverified.
- `extraction_method`: direct source field, deterministic rule, model judgment, or manual
  correction.
- `freshness_status`: whether the supporting source snapshot is current, stale, or unknown.
- `quality_flags`: machine-readable warnings such as title conflict, date conflict, low evidence,
  model inferred, or needs more evidence.
- `recipe_version`: the confidence recipe, prompt, or rule version that produced the tier or
  dimensional profile.

## Publishability Controls

Published artifacts must be written through a publishability policy layer. Source roles describe
which providers can participate in the project, but field-level policy and artifact policy decide
what may appear in public Parquet tables and manifests.

Core tables should be shaped only from fields whose source policy permits the intended published
use, plus derived outputs whose transform recipe is allowed to consume those inputs. Restricted or
local-only sources may support matching, QA, or confidence decisions, but their restricted values
must not leak into public tables, retrieval text, embeddings, judgments, or manifests.

The manifest should record policy versions for source policy, field policy, artifact policy, and
publishability validation. This policy can evolve over time, but the artifact writer should treat
publishability failures as release blockers.

## Tags, Facets, And Judgments

The dataset should keep source tags, normalized facets, and inferred judgments separate.

`source_tags` are provider-supplied labels or lightly normalized source labels. They preserve where
the label came from and should not be treated as the dataset's final taxonomy by themselves.
Provider tags may be broad, sparse, misspelled, or overly specific to one record. They are evidence
inputs for normalization, not proof that a canonical facet or similarity axis exists.

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

Source signal showcases in [`source-signal-showcases.md`](source-signal-showcases.md) document cases
where raw provider fields are useful evidence but not sufficient as durable taxonomy.

## LLM Judgment Boundary

LLM outputs are derived judgments, not source metadata. They should not write directly into
canonical entities, titles, external IDs, source facts, profile fields, facets, or relationship
edges.

Allowed direct LLM destinations:

- `llm_judgments`
- `judgment_candidates`
- `conflict_flags`
- benchmark and evaluation artifacts
- retrieval-text segments only when generated from publishable inputs and recipe-versioned

LLM-derived values can become queryable data only through a versioned materialization recipe. Before
materialization, the pipeline must validate that:

- all inputs were allowed by publishability policy;
- provider, model, prompt, parameters, and recipe versions are recorded;
- output is structured and schema-valid;
- evidence or input references are retained;
- a confidence profile or tier is produced by the materialization recipe;
- quality flags are attached where relevant;
- the target surface is explicitly allowed for that materialization recipe.

Invalid, failed, low-confidence, or unsupported judgments should remain in judgment artifacts and
must not materialize into queryable core, profile, relationship, or facet data.

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

`similarity_candidates` is a derived artifact, not a source-ingest or canonical metadata surface.
It must be generated by a named recipe from versioned input artifacts that already passed their own
publishability, materialization, and confidence gates. A recipe change may change candidate
coverage, ordering inputs, scores, or confidence tiers, but it should require recomputing only this
derived table and its manifest entry.

Schema draft:

- `source_entity_id`
- `target_entity_id`
- `candidate_id`
- `candidate_direction`: `directed`, `symmetric`, or recipe-defined where the distinction matters
- `recipe_version`
- `input_surface_versions`: versions or manifest references for every consumed table
- `candidate_reasons`: compact reason codes such as `shared_facets`, `embedding_neighbor`,
  `relationship_neighborhood`, or `judgment_materialized_facet`
- `score_overall`: recipe-local candidate strength, not a global truth score
- `score_dimensions`: recipe-local dimensions such as `genre`, `setting`, `tone`, `scope`,
  `cast_life_stage`, `graph_distance`, and `embedding`
- `confidence_profile`: dimensional recipe-specific confidence, including `source_role`,
  `evidence_strength`, `agreement_status`, `extraction_method`, `freshness_status`,
  `quality_flags`, and the confidence recipe version
- `confidence_tier`: optional recipe-produced convenience tier, not comparable across all surfaces
- `evidence_refs`
- `provenance_refs`
- `quality_flags`
- `generated_at`

Recipe inputs:

- `entities`, to validate durable source and target entity IDs;
- `relationships` and `relationship_evidence`, to derive graph-neighborhood signals;
- `facets`, including materialized inferred facets when approved by their recipe;
- publishable source tags or normalized tag-derived facets where policy allows them;
- `retrieval_text`, for text-derived candidate generation or explanations;
- `embeddings`, for nearest-neighbor candidates tied to embedding recipe versions;
- `llm_judgments` only through approved materialized surfaces;
- provenance, source snapshot, policy, and manifest metadata needed to audit inputs and versions.

Recipes must exclude blocked, private, local-only, or non-publishable source values from public
candidate rows. Source credentials or private experiment access do not make an input eligible.

## Recompute Contract

Derived surfaces must be recipe-versioned. When a similarity recipe changes, the project accepts the
cost of recomputing the affected derived table. That recomputation should use existing versioned
artifacts wherever possible instead of repeating source fetches or rebuilding unrelated base tables.

This contract keeps expensive or experimental similarity work separate from the durable base
dataset. It also lets downstream consumers choose whether to use a new similarity recipe without
losing access to stable entity, relationship, facet, and provenance data.

A recompute should record the input manifest revision, input surface versions, policy versions,
confidence recipe version, similarity recipe version, row count, generated timestamp, and
compatibility notice in the manifest. If an input surface is refreshed without changing the
similarity recipe, the derived table can still be recomputed to produce a new snapshot-scoped
candidate table while preserving the recipe identity.
