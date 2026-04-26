# Source Signal Showcases

This document records small provider observations that explain why the dataset needs normalized
facets, evidence, confidence, and derived judgments instead of treating provider tags or provider
recommendations as the final taxonomy.

These examples are not source integrations by themselves. They are local evidence notes used to
shape schemas, fixtures, backlog work, and provider review. Before any provider value is copied into
public artifacts, the source role and field-level publishability policy still apply.

## TMDB TV 280948: Spring Fever

Observed locally on 2026-04-26 through the TMDB API using the project read token. TMDB API remains
classified as `LOCAL_EVIDENCE` / `RUNTIME_ONLY`; this note is a source-quality showcase, not approval
to mirror TMDB metadata.

Entity:

- TMDB TV ID: `280948`
- Title: `Spring Fever`
- Original title: `스프링 피버`
- Original language/country: Korean / South Korea
- Format: miniseries
- Episodes: 12
- Genres: Comedy, Drama
- Networks: tvN, Prime Video
- External IDs observed: IMDb, TVDB, Wikidata
- Source-material evidence observed: keyword `based on web novel` and a writing credit with job
  `Novel`

Provider keywords observed:

| Keyword | Approximate TMDB TV matches observed | Signal quality |
| --- | ---: | --- |
| `romance` | 6918 | Too broad to be useful alone. |
| `drama` | 192 | Duplicates genre-like metadata and is weak alone. |
| `based on web novel` | 421 | Useful as `source_material`, weak as similarity alone. |
| `school setting` | 29 | Potentially useful if normalized into setting facets. |
| `uncle nephew relationship` | 21 | Specific relationship-context signal, not broad similarity. |
| `countryside setting` | 3 | Useful but sparse; should be normalized with evidence. |
| `comdey` | 1 | Typo; should not become a canonical facet spelling. |
| `teacher female lead` | 1 | Potentially useful character-role evidence, but dead-end as a raw tag. |
| `warm male lead` | 1 | Potentially useful tone/character evidence, but dead-end as a raw tag. |
| `tattooed male lead` | 1 | Very specific character evidence, not a general discovery axis alone. |

Provider recommendation/similar surfaces were also noisy. The recommendations included a plausible
nearby Korean rural romance result, but also broad cross-language comedy/drama matches and older
sitcom/drama entries. The similar list mixed unrelated countries, languages, dates, and genres.

### Why This Matters

This example shows several failure modes the dataset should fix:

- Provider keywords can be broad, sparse, typo-prone, or over-specific.
- A keyword can be valid evidence without being a useful similarity axis by itself.
- Provider recommendation lists can mix plausible neighbors with generic genre overlap.
- Structured fields outside keywords can be more useful than keywords; here, the `Novel` writing
  credit reinforces the `based on web novel` source-material signal.
- The dataset should preserve raw provider signals only where policy allows, then normalize them
  into auditable facets, evidence, judgments, or derived candidate surfaces.

### Dataset Implication

For this kind of record, the dataset should aim to expose normalized and evidence-backed surfaces
such as:

- `source_material=web_novel`
- `country=KR`
- `language=ko`
- `format=miniseries`
- `genre=romantic_comedy` where supported by an accepted recipe or judgment
- `setting=countryside`
- `setting=school`
- character or relationship-context evidence such as female teacher lead or rough-edged/warm male
  lead only through a normalized facet or judgment recipe

Raw provider keywords should be treated as source evidence. They should not become the dataset's
canonical taxonomy without normalization, publishability review, and confidence/evidence metadata.
