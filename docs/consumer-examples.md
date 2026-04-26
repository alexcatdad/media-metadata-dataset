# Consumer Examples

These examples show how downstream consumers can use published files. They are not project pipeline
commands, and they do not define a project-owned API, app, DuckDB artifact, graph browser, RAG
service, or recommendation product.

The common pattern is:

1. Download or open a Hugging Face dataset revision.
2. Read the manifest.
3. Load the referenced Parquet tables into the consumer's own tool.
4. Resolve titles or external IDs to `entity_id`.
5. Join core, profile, facet, relationship, evidence, confidence, and provenance surfaces.
6. Apply consumer-owned ranking, filtering, UI, personalization, serving, or explanation logic.

## Minimal File Loader

This illustrative downstream code uses PyArrow to load table paths listed in the manifest:

```python
from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq


snapshot_dir = Path("/path/to/downloaded/hf-snapshot")
manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))

tables = {
    table["name"]: pq.read_table(snapshot_dir / table["path"])
    for table in manifest["tables"]
}

entities = tables["entities"]
titles = tables["titles"]
relationships = tables["relationships"]
facets = tables["facets"]
```

Consumers may then convert tables to Polars, pandas, DuckDB, SQLite, a graph store, a vector index,
or an application database. That conversion is a downstream choice.

## John: Building A The Expanse-Like App

John is building his own application outside this repo. His app wants to answer a query like:
"I just watched `The Expanse`; what else might feel similar?"

The dataset helps John resolve and explain candidates. It does not produce the final ranked
recommendation list.

### Flow

1. Pin a Hugging Face release tag or full commit SHA.
2. Read `manifest.json` and verify expected schema versions.
3. Load `entities`, `titles`, `external_ids`, `relationships`, `relationship_evidence`, `facets`,
   `retrieval_text`, `embeddings`, and `provenance` if present.
4. Resolve `The Expanse` through `titles` or `external_ids`.
5. Collect relationship neighbors such as adaptations, shared franchise links, source-material
   links, and derived similarity candidates if present.
6. Collect facets such as genre, setting, scope, source material, tone, and duration.
7. Use confidence, evidence strength, conflict status, quality flags, and provenance references to
   decide which signals John's app trusts.
8. Rank candidates in John's own code.

### Query Shape

```sql
-- Resolve the watched title.
select e.entity_id, e.domain, e.canonical_title
from titles t
join entities e on e.entity_id = t.entity_id
where lower(t.title) = lower('The Expanse');
```

```sql
-- Gather graph neighbors with evidence signals.
select
  r.target_entity_id,
  r.relationship_family,
  r.relationship_type,
  r.confidence_tier,
  ev.evidence_strength,
  ev.agreement_status,
  r.quality_flags
from relationships r
left join relationship_evidence ev on ev.evidence_id = r.evidence_id
where r.source_entity_id = :the_expanse_entity_id;
```

```sql
-- Gather reusable facets for consumer-owned ranking.
select facet_namespace, facet_key, facet_value, confidence_tier, quality_flags
from facets
where entity_id = :candidate_entity_id;
```

John's app might weight science-fiction genre, space setting, political scope, relationship
distance, source-material evidence, and embedding similarity. Those weights belong to John's app,
not this dataset.

## Alex: Golden Time And Adult University Anime

Alex wants anime discovery that preserves anime-specific taxonomy and concept-level signals. The
external tool may resolve `Golden Time`, or it may search for "adult university romance with a real
ending."

The dataset helps expose anime profiles, normalized facets, evidence, retrieval text, embeddings,
and confidence. It does not own the search UI or final recommendation policy.

### Flow

1. Pin a Hugging Face snapshot.
2. Read the manifest and check that `anime_profile`, `facets`, and relevant derived surfaces are
   present.
3. Resolve `Golden Time` through `titles`.
4. Join `anime_profile` for anime-specific fields such as format, season, and episode shape.
5. Query facets such as `cast_life_stage=adult`, `educational_setting=university`,
   `world_setting=contemporary_real_world`, `genre=romance`, and `narrative_closure=conclusive`
   when present.
6. Inspect evidence and confidence, especially for materialized inferred facets.
7. Rank candidates in the external anime tool using its own blend of filters, graph traversal,
   embeddings, and UI preferences.

### Query Shape

```sql
-- Resolve Golden Time.
select e.entity_id, e.canonical_title, ap.anime_format, ap.episode_count
from titles t
join entities e on e.entity_id = t.entity_id
left join anime_profile ap on ap.entity_id = e.entity_id
where lower(t.title) = lower('Golden Time');
```

```sql
-- Find anime with adult/university/contemporary signals.
select f.entity_id
from facets f
join entities e on e.entity_id = f.entity_id
where e.domain = 'anime'
  and (f.facet_key, f.facet_value) in (
    ('cast_life_stage', 'adult'),
    ('educational_setting', 'university'),
    ('world_setting', 'contemporary_real_world')
  )
  and f.confidence_tier in ('high', 'medium')
group by f.entity_id
having count(distinct f.facet_key) = 3;
```

```sql
-- Inspect whether a facet was source-backed or materialized from a judgment.
select
  f.entity_id,
  f.facet_key,
  f.facet_value,
  f.facet_origin,
  f.confidence_tier,
  f.quality_flags,
  ev.evidence_strength,
  ev.agreement_status
from facets f
left join relationship_evidence ev on ev.evidence_id = f.evidence_id
where f.entity_id = :candidate_entity_id;
```

If an adult-university signal came from an LLM-assisted judgment, the consumer should treat
`facet_origin`, `recipe_version`, `quality_flags`, and evidence links as part of the decision about
whether to show or down-rank the candidate.

## What Remains Out Of Scope

These examples intentionally stop at artifact consumption. This repo does not provide:

- hosted query endpoints;
- a recommendation API;
- a web or mobile application;
- a DuckDB database file as the dataset contract;
- final personalized rankings;
- consumer-side LLM prompts, RAG serving, or UI behavior.

The dataset should make those downstream systems easier to build by publishing stable files,
schemas, provenance, evidence, confidence, and version metadata.
