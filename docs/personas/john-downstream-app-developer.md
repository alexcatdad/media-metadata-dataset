# Persona: John, Downstream App Developer

John is a developer building a small mobile or web application for someone close to him. His
application is outside this repo. He wants to help that person answer a familiar question: "I just
watched this show and want something that gives me a similar feeling. What should I watch next?"

John is not looking for this project to host an API, build a recommendation engine, or provide an
end-user product. He needs a reusable dataset with enough structure, provenance, and relationship
signals that he can build his own application on top of it.

## Situation

John's girlfriend has just watched `The Expanse`, a science-fiction show, and wants to find something
with a similar feeling. "Feeling" is not a single field. It may come from a combination of:

- genre and subgenre;
- setting, such as space, planets, future society, political systems, or exploration;
- narrative scale, such as local, planetary, interplanetary, or civilization-wide stakes;
- character ensemble shape and character progression;
- source-material relationships;
- creator, studio, network, or production relationships;
- themes, tone, and pacing;
- commitment length, such as episode count, seasons, movie runtime, or franchise size;
- graph distance from known related works;
- evidence quality and confidence.

John first looks at existing APIs and databases. He finds useful pieces, but no durable dataset that
pulls identity links, media relationships, similarity evidence, and provenance into a clear artifact.
He can search the web manually, but that is not deterministic enough for an application.

## Journey

1. John finds this dataset and reads the artifact documentation.
2. He downloads the current versioned dataset artifacts.
3. He loads entities, titles, external IDs, relationships, evidence, embeddings, and provenance into
   his own local database or application index.
4. His app receives the query: "I just watched `The Expanse`; show me similar things."
5. His app resolves `The Expanse` to a canonical entity using titles and external IDs.
6. His app inspects the dataset's relationship and similarity surfaces for that entity.
7. His app chooses its own ranking strategy, potentially combining graph neighbors, shared tags,
   embeddings, duration, source material, creator data, and relationship confidence.
8. His app presents recommendations and explanations to the user.

For example, John's app may decide that `Altered Carbon` is a useful recommendation candidate
because both works may share science-fiction signals, large-scale speculative worldbuilding, future
society themes, and enough scope that the recommendation feels broader than a single-location
procedural. This project should not hard-code that final recommendation. It should expose the
structured surfaces that let John's application make, weight, explain, or reject that comparison.

## What John Needs From The Dataset

- A stable entity table with canonical IDs and source-specific external IDs.
- Title and alias data that lets his app resolve user queries.
- Relationship edges that distinguish identity, adaptation, sequel/prequel, remake/reboot,
  franchise, source-material, and similarity-style links.
- Evidence and provenance for every meaningful fact or derived judgment.
- Similarity-ready features such as genres, tags, themes, creators, source material, setting hints,
  duration, and embeddings.
- Confidence or scoring metadata so his app can decide how much to trust each relationship.
- Versioned artifacts that can be refreshed without breaking his application unexpectedly.

## Product Boundary

This repo does not build John's app. It does not decide the final recommendation list for his user.
It does not provide a hosted API, search endpoint, mobile UI, web UI, personalized recommender, or
RAG-serving interface.

This repo provides the dataset that makes John's application easier to build.

## Dataset Implications

This persona implies the dataset should prioritize:

- clear artifact schemas over application-specific behavior;
- relationship explainability over opaque recommendations;
- graph and retrieval surfaces over one final "similarity score";
- source-aware provenance over untraceable aggregation;
- progressive enhancement, so partial data remains useful while richer surfaces improve over time.
