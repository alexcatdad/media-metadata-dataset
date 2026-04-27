# Schema Documentation

This page turns the current architecture decisions into contributor-facing schema guidance. The
published contract is Parquet tables plus a manifest. It is not an API, hosted service,
application, DuckDB artifact, recommendation product, graph browser, or RAG serving layer.

The manifest is the entry point. Consumers read the manifest, inspect table paths, versions,
compatibility tiers, row counts, source coverage, policy versions, recipe versions, and enrichment
status, then load the referenced Parquet files into their own tools.

## Compatibility Tiers

| Tier | Purpose | Compatibility rule | Examples |
|---|---|---|---|
| `core` | Shared cross-domain public contract | Backward-compatible within a major version | `entities`, `titles`, `external_ids`, `relationships`, `relationship_evidence`, `facets`, `provenance`, `source_records`, `source_snapshots`, `provider_runs` |
| `profile` | Domain-specific fields | Independently versioned by profile | `anime_profile`, `tv_profile`, `movie_profile` |
| `derived` | Recomputable enhancement output | Recipe-versioned; breaking changes require manifest notices | `retrieval_text`, `embeddings`, materialized inferred facets, future `similarity_candidates` |
| `experimental` | Trial surfaces | No stability guarantee; must be clearly marked | candidate queues, exploratory judgments, benchmark-only outputs |

Core tables should use stable IDs and additive evolution. Profile and derived tables can move
faster, but consumers must be able to see their versions and compatibility notices in the manifest.

## Core Tables

The exact physical schemas will be implemented by the schema-manifest lane, but contributors should
shape fields around these contracts.

### `entities`

Canonical media works with stable dataset IDs.

| Field | Purpose |
|---|---|
| `entity_id` | Durable dataset ID. Never reuse within a dataset line. |
| `domain` | Initial values are `anime`, `tv`, and `movie`. |
| `canonical_title` | Convenience title from publishable inputs. Full title history lives in `titles`. |
| `media_type` | High-level type such as series, film, special, OVA, or ONA where safely known. |
| `release_year` | Coarse release year when publishable. |
| `enrichment_status` | Compact status for available stages. |
| `confidence_tier` | Recipe-produced convenience tier, not a universal score. |
| `evidence_count` | Count or compact signal for supporting evidence. |
| `conflict_status` | Machine-readable conflict state. |
| `quality_flags` | Array of warnings such as `low_evidence` or `title_conflict`. |
| `provenance_id` | Join key into provenance surfaces. |
| `schema_version` | Version for this table contract. |

Example row:

```json
{
  "entity_id": "mdm:entity:anime:golden-time",
  "domain": "anime",
  "canonical_title": "Golden Time",
  "media_type": "tv_series",
  "release_year": 2013,
  "enrichment_status": "facet_enhanced",
  "confidence_tier": "high",
  "evidence_count": 3,
  "conflict_status": "none",
  "quality_flags": [],
  "provenance_id": "prov:entity:golden-time:v1",
  "schema_version": "core-1"
}
```

### `titles`

Canonical titles, aliases, original titles, romanizations, and source-backed title variants.

| Field | Purpose |
|---|---|
| `title_id` | Stable title-row ID. |
| `entity_id` | Join key to `entities`. |
| `title` | Publishable title string. |
| `title_kind` | `canonical`, `alias`, `original`, `localized`, or source-specific kind. |
| `language` | BCP 47 language tag when known. |
| `source_role` | Role of the contributing source, when relevant. |
| `confidence_tier` | Recipe-produced title confidence. |
| `evidence_id` | Join key to evidence. |
| `provenance_id` | Join key to provenance. |

### `external_ids`

Source-specific IDs and URLs. This table supports resolution and cross-reference without copying
restricted provider metadata.

| Field | Purpose |
|---|---|
| `entity_id` | Join key to `entities`. |
| `source` | Provider or source namespace. |
| `source_id` | Provider ID, URL slug, or stable external key. |
| `id_kind` | `primary`, `crossref`, `url`, or provider-specific classification. |
| `source_role` | `BACKBONE_SOURCE`, `ID_SOURCE`, `LOCAL_EVIDENCE`, or other reviewed role. |
| `publishability_class` | Field policy class used by artifact validation. |
| `evidence_id` | Evidence for the mapping. |

### `relationships`

Source-backed or derived edges between entities. Preserve precise relationship types where evidence
supports them, and expose a broader family for grouping.

| Field | Purpose |
|---|---|
| `relationship_id` | Stable edge ID within a snapshot. |
| `source_entity_id` | Directional source node. |
| `target_entity_id` | Directional target node. |
| `relationship_family` | `identity`, `continuity`, `adaptation`, `variant`, `franchise`, `episode_context`, `similarity`, or `uncertain`. |
| `relationship_type` | Precise type such as `sequel`, `adaptation_of`, `remake`, or `similar_to`. |
| `directionality` | Whether direction is meaningful, paired, inverse, or symmetric. |
| `confidence_tier` | Edge confidence from the relationship recipe. |
| `evidence_count` | Supporting evidence count. |
| `conflict_status` | Agreement or conflict state. |
| `evidence_id` | Primary evidence reference. |
| `recipe_version` | Rule, judgment, or extraction recipe. |

### `relationship_evidence`

Evidence records supporting relationship edges.

| Field | Purpose |
|---|---|
| `evidence_id` | Join key from relationship or other claim tables. |
| `claim_type` | Relationship, identity, facet, profile, or other supported claim type. |
| `claim_id` | ID of the claim row when applicable. |
| `source_role` | Source role used by the evidence. |
| `evidence_strength` | `direct`, `source_declared`, `multi_source`, `derived`, or `inferred`. |
| `agreement_status` | `confirmed`, `conflicting`, `ambiguous`, or `unverified`. |
| `provenance_id` | Join key into provenance. |

### `facets`

Normalized searchable attributes for cross-domain discovery. Facets should contain normalized
queryable values, not raw provider taxonomies by default.

| Field | Purpose |
|---|---|
| `entity_id` | Join key to `entities`. |
| `facet_namespace` | Domain such as `setting`, `cast`, `theme`, `tone`, `format`, or `source_material`. |
| `facet_key` | Normalized key, for example `educational_setting`. |
| `facet_value` | Normalized value, for example `university`. |
| `facet_origin` | `source_tag`, `deterministic_mapping`, `materialized_judgment`, or `manual_correction`. |
| `confidence_tier` | Facet confidence from a versioned recipe. |
| `quality_flags` | Warnings such as `model_inferred` or `needs_more_evidence`. |
| `evidence_id` | Join key into evidence. |
| `recipe_version` | Facet normalization or materialization recipe. |

`source_tags`, normalized `facets`, and inferred `judgments` stay separate. Inferred values must
enter judgment surfaces first and may become facets only through an explicit materialization
recipe, confidence threshold, provenance link, and publishability validation.

### `source_snapshots`

Source snapshot audit rows make source versioning and refresh windows queryable instead of only
manifest-level metadata.

| Field | Purpose |
|---|---|
| `source_snapshot_id` | Stable snapshot ID referenced by provenance and source records. |
| `source_id` | Reviewed source namespace such as `manami`, `tvmaze`, or `wikidata`. |
| `source_role` | Reviewed source role used for publishability. |
| `snapshot_kind` | Release file, API fetch window, SPARQL query window, or other adapter kind. |
| `fetched_at` | Timestamp when the source snapshot was fetched or compiled. |
| `source_published_at` | Source-published timestamp where applicable. |
| `fetch_window_started_at` / `fetch_window_finished_at` | Window covered by an API/query run. |
| `source_version` | Source-native version or release marker. |
| `policy_version` | Source policy version applied. |
| `publishable_field_policy_version` | Field policy version applied. |
| `artifact_policy_version` | Artifact policy version applied. |
| `record_count` | Number of normalized source records covered. |
| `content_hash` | Hash of the normalized source-backed rows when available. |
| `manifest_uri` | Source manifest URI or local release path where applicable. |

### `provider_runs`

Provider run audit rows describe adapter execution without storing credentials or raw restricted
payloads.

| Field | Purpose |
|---|---|
| `provider_run_id` | Stable run ID referenced by provenance and source records. |
| `source_id` | Reviewed source namespace. |
| `source_snapshot_id` | Snapshot produced or consumed by the run. |
| `adapter_name` | Adapter or normalizer name. |
| `adapter_version` | Adapter implementation version. |
| `started_at` / `finished_at` | Execution timestamps. |
| `request_count` | Public request count or equivalent source access count. |
| `cache_hit_count` | Cache-hit count when tracked. |
| `status` | Run status such as `completed` or `failed`. |
| `auth_shape` | Auth mode shape such as `none`, `api_key`, or `bearer`; never the value. |
| `secret_refs` | Secret names only, never tokens, authorization headers, or secret values. |
| `notes` | Human-readable audit note without restricted payload fields. |

## Domain Profiles

Profiles preserve domain-specific facts without forcing the shared core to become noisy or
anime-shaped.

| Profile | Example fields |
|---|---|
| `anime_profile` | `entity_id`, `anime_format`, `season_year`, `season_name`, `cour_count`, `episode_count`, `source_demographic`, `anime_profile_version`, confidence and provenance references |
| `tv_profile` | `entity_id`, `season_count`, `episode_count`, `show_status`, `network_or_platform`, `release_shape`, `tv_profile_version`, confidence and provenance references |
| `movie_profile` | `entity_id`, `runtime_minutes`, `release_year`, `collection_hint`, `franchise_hint`, `movie_profile_version`, confidence and provenance references |

Anime is first class, but v1 is not anime-only. V1 requires meaningful anime, TV, and movie source
paths through the shared core schema.

## Provenance, Evidence, And Confidence

Provenance is separate and joinable rather than inline field-level metadata by default. Core tables
carry lightweight references and practical trust signals; audit detail lives in supporting tables.

Use:

- `confidence_tier` for a compact recipe-produced trust signal;
- `evidence_count`, `evidence_id`, and `relationship_evidence` for support strength;
- `conflict_status` and `quality_flags` for consumer-facing caution;
- `provenance_id`, `source_snapshots`, `provider_runs`, and `recipe_runs` for audit.

Do not publish one universal normalized confidence score. Confidence is dimensional and
recipe-specific. A title match, relationship edge, inferred adult-cast facet, identity merge, and
embedding-derived candidate are different claim types and should not be compared as one global
number.

## LLM Materialization

LLM outputs are derived judgments, not source metadata. They may write directly to judgment,
candidate, conflict, benchmark, evaluation, and tightly controlled retrieval-text surfaces. They
must not write directly into canonical entities, titles, external IDs, source facts, profiles,
facets, or relationship edges.

Before an LLM-derived claim becomes queryable data, a materialization recipe must validate:

- publishable inputs;
- provider, model, prompt, parameter, and recipe identity;
- structured schema-valid output;
- retained evidence or input references;
- confidence profile and quality flags;
- target-surface eligibility.

Invalid, failed, low-confidence, or unsupported judgments remain in judgment artifacts.

## Common Joins

Resolve a user title to an entity:

```sql
select e.entity_id, e.domain, e.canonical_title, t.title_kind, t.confidence_tier
from titles t
join entities e on e.entity_id = t.entity_id
where lower(t.title) = lower(:query_title);
```

Find relationship neighbors with evidence:

```sql
select
  r.source_entity_id,
  r.target_entity_id,
  r.relationship_family,
  r.relationship_type,
  r.confidence_tier,
  ev.evidence_strength,
  ev.agreement_status
from relationships r
left join relationship_evidence ev on ev.evidence_id = r.evidence_id
where r.source_entity_id = :entity_id;
```

Find anime matching Alex-style facets:

```sql
select f.entity_id
from facets f
where (f.facet_key, f.facet_value) in (
  ('cast_life_stage', 'adult'),
  ('educational_setting', 'university'),
  ('world_setting', 'contemporary_real_world')
)
group by f.entity_id
having count(distinct f.facet_key) = 3;
```

These examples show consumption patterns over files after consumers load Parquet tables into their
own environment. They do not define a project-owned API, app, database artifact, recommendation
engine, or serving layer.
