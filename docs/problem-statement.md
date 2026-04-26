# Problem Statement

People discover narrative media through fragmented data. A person looking for a TV show, anime,
movie, or related media work usually has to move between separate databases, APIs, recommendation
systems, search engines, watch providers, and community pages. Those systems expose useful public
facts, but they rarely assemble durable identity links, relationship edges, provenance, and
recommendation-ready context in one reproducible dataset.

Existing tools tend to query sources just in time. If they identify relationships at all, they often
rebuild them per request, lose the reasoning trail, or depend on a single provider's partial view.
That makes recommendations and search brittle: sequels, remakes, specials, source-material links,
same-franchise relationships, false title matches, and cross-domain relationships are difficult to
inspect, cache, audit, or reuse.

This project exists to build an open, repeatable dataset compiler for narrative screen media. The
compiler should collect admissible public information from classified sources, preserve provenance,
normalize identity and relationship graphs, generate useful embeddings, and record auditable
LLM-assisted judgments only where deterministic evidence is not enough.

The project should respect the providers that make this information available. Its value is in
collating admissible source data, preserving provenance, and making scattered facts usable in modern
query and retrieval workflows, not in bypassing provider rights or copying data that cannot be
republished.

The intended output is not an API, hosted recommendation service, search application, RAG
application, graph browser, DuckDB database artifact, or consumption layer. It is a reusable dataset
artifact published as Parquet tables plus a manifest. Other implementers may choose to build
applications on top of it, but this project stops at compiling, versioning, publishing, and
documenting the data.

## Initial Scope

The v1 dataset focuses on:

- anime as a first-class domain;
- TV;
- movies;
- source links and cross-references;
- identity resolution;
- relationship edges;
- recommendation and retrieval-ready context;
- provenance and auditability.

V1 is anime-first, not anime-only. A v1 published dataset must include meaningful TV and movie
coverage from admissible sources, not only TV/movie-shaped anime records, identifier stubs, or empty
future schema profiles.

Books and source material may be used as relationship evidence, but books are not a full v1 browse
domain. The schema should leave room for books to become a future progressive domain through a later
accepted decision. Music, games, podcasts, hosted APIs, direct applications, personalized
recommendations, consumption layers, and copied closed-provider metadata remain out of scope unless
later accepted decisions change that.

## Core Problem

The core problem is not that media facts are unavailable. The problem is that public facts are
spread across sources with different schemas, rights, identifiers, update cadences, and relationship
quality. Downstream tools need a durable, source-aware dataset that makes those facts and
relationships available for their own query, retrieval, recommendation, or application layers
without reconstructing the graph from scratch every time.

Some provider signals are also noisy or underpowered for discovery on their own: keywords can be
too broad, typo-prone, sparse, or over-specific, and provider recommendation lists can mix useful
neighbors with generic genre overlap. See [`source-signal-showcases.md`](source-signal-showcases.md)
for concrete examples that motivate normalized facets, evidence, and derived judgments.

## Success Shape

A successful version of this project publishes data that lets a downstream tool, outside this repo,
ask about a specific anime, TV show, or movie and receive enough structured context to:

- identify the work across source systems;
- distinguish same-entity matches from related works and false positives;
- inspect sequels, prequels, specials, movies, remakes, adaptations, source-material evidence, and
  same-franchise relationships;
- retrieve recommendation-ready neighboring works;
- feed structured and textual context into a RAG system;
- explain where each fact or judgment came from.

The dataset should be reproducible by ordinary contributors, auditable from source inputs through
derived judgments, and safe to publish under the source-admissibility rules recorded in this repo.

The project itself does not provide the asking, searching, recommending, or RAG-serving interface.
Those are consumer responsibilities.

See the downstream-consumer personas for journeys that motivate the dataset shape:

- [`John, Downstream App Developer`](personas/john-downstream-app-developer.md)
- [`Alex, Anime Discovery Power User`](personas/alex-anime-discovery.md)

See [`dataset-surfaces.md`](dataset-surfaces.md) for the current artifact-surface framing.
