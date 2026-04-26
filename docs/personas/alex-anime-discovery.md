# Persona: Alex, Anime Discovery Power User

Alex has spent years talking with friends about how hard it is to find shows that are similar in the
ways that actually matter. Simple tags are not enough. The same broad tags can describe works that
feel nothing alike, while the most important discovery signals may be buried in synopsis text,
community discussions, relationship pages, or domain-specific metadata.

Alex may build or integrate a separate tool later, but that tool is outside this repo. This project
only needs to publish dataset artifacts that make such a tool possible.

## Situation

Alex watched `Golden Time`, a Japanese anime. The appeal is not merely that it is tagged as romance,
drama, or slice of life. The useful discovery signals are more specific:

- the main characters are adults;
- the setting is university rather than middle school or high school;
- the cast does not center on children;
- the story has emotional continuity and a conclusion;
- the world is contemporary and close to our own;
- related concepts such as amnesia may matter for some searches;
- the recommendation should account for anime-specific taxonomy rather than treating anime as a
  generic TV subtype.

Today, Alex searches across many APIs, databases, lists, and recommendation threads. Even strong
projects such as Manami help normalize anime identity and cross-references, but finding a work with
the same appeal still requires manual reading, guessing, and detective work.

The repo already has a tiny concept seed at
[`corpus/bootstrap-concept-romance-college-v1.jsonl`](../../corpus/bootstrap-concept-romance-college-v1.jsonl)
with `Golden Time`, `Honey and Clover`, and `Nodame Cantabile`. That seed is useful as an early
fixture, but the persona requires richer, refreshable dataset surfaces than this small handpicked
slice.

## Journey

1. Alex wants either "shows like `Golden Time`" or "shows where the main characters are adults in
   university."
2. Alex tries existing APIs and datasets, but the available fields and tags do not reliably express
   the difference between adult university stories and superficially similar school romance shows.
3. Alex finds this dataset and inspects its anime entities, titles, relationships, evidence,
   provenance, facets, and retrieval-ready text.
4. Alex uses the dataset in an external search or media-management tool, such as an Overseerr-style
   request/search experience or a custom local discovery tool.
5. The external tool resolves `Golden Time` or the plain-language concept to dataset entities and
   facets.
6. The tool ranks candidates using the dataset's structured signals, relationship graph, evidence,
   embeddings, and confidence metadata.
7. The tool can surface `Golden Time` for the concept query, and can also surface other works that
   share the important adult/university/contemporary/conclusive-story signals.

This repo does not build that search tool, magic-button experience, or recommendation UI. It
publishes the data that lets another tool build those experiences.

## Progressive Enhancement Scenario

A new anime is released years after `Golden Time`. It also follows university students, may involve
amnesia, is set in a world like ours, and has enough similar structure that Alex would want it to be
discoverable from the same query later.

The dataset should support that path:

1. A scheduled or manual source refresh ingests the new work from admissible sources.
2. Deterministic normalization attaches source IDs, titles, aliases, dates, format, and available
   source facts.
3. Domain-specific anime facets capture or derive signals such as university setting, adult cast,
   contemporary setting, themes, and relevant narrative markers where evidence supports them.
4. Relationship and similarity candidates are produced from source links, tags, text, embeddings,
   and graph proximity.
5. Ambiguous candidates can be queued for auditable LLM judgment or human review.
6. A new versioned dataset snapshot exposes the new work and its evidence.
7. Future external tools using the dataset can now return the new show for the same Golden
   Time-like discovery request.

## What Alex Needs From The Dataset

- Anime-aware fields and facets instead of flattening anime into generic TV metadata.
- Searchable and explainable signals for cast life stage, educational setting, world setting,
  narrative closure, themes, tone, and source-derived tags.
- Identity and relationship data that distinguishes same work, sequels, specials, remakes, source
  material, franchise links, and similarity.
- Evidence and provenance for derived facets, especially when a field is inferred from tags,
  summaries, source relations, or model-assisted judgments.
- Versioned snapshots that progressively improve as new shows and better evidence are added.
- Retrieval-ready text and embeddings that can support plain-language queries in external tools.

## Dataset Implications

This persona implies the dataset should prioritize:

- domain profiles, with anime-specific taxonomy preserved;
- faceted discovery surfaces beyond broad tags;
- progressive enhancement for new releases and newly discovered evidence;
- audit trails for inferred or model-assisted facets;
- relationship and similarity weights that downstream tools can combine differently;
- stable snapshots so external tools can update without losing reproducibility.
