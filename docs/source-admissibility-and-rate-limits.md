# Source Admissibility And Rate Limits

Last reviewed: 2026-04-25.

This project is non-commercial and fully open, but that does not make every API response
redistributable. A provider can be useful for local evidence while still being unsafe for the
published dataset.

## Source Roles

- `BACKBONE_SOURCE`: can shape published artifacts.
- `ID_SOURCE`: can contribute stable URLs, IDs, and cross-reference evidence.
- `LOCAL_EVIDENCE`: can help local matching or QA, but raw data is not published.
- `RUNTIME_ONLY`: consumers should fetch it themselves under their own credentials.
- `BLOCKED`: do not integrate without direct permission or a better license path.

## Execution Boundary

Project tasks must not depend on host Python execution. Local development uses this computer as a
Docker host only; the same commands should run in GitHub Actions or Woodpecker without relying on
machine-specific state.

Allowed local execution:

- Docker image builds;
- Docker Compose services;
- `woodpecker-cli` runs against the same container image/steps used by CI;
- shell inspection commands such as `git`, `rg`, `jq`, `zstd`, and `duckdb` for viewing artifacts.

Avoid:

- running pipeline commands directly with host Python;
- relying on globally installed Python packages;
- writing pipeline state outside mounted cache/output directories;
- treating a successful host run as validation.

## Enforcement Rules

All network access must go through a provider-aware HTTP client. Provider adapters must not call
`httpx` directly.

The client enforces:

- per-provider token buckets from config;
- daily/weekly run guards for bulk dumps and release assets;
- persistent request cache keyed by provider, URL, request body hash, and auth-free request shape;
- `ETag`, `Last-Modified`, and conditional request headers where providers support them;
- `Retry-After` and provider reset headers on `429`;
- hard stop on daily budgets instead of retry storms;
- max concurrency per provider, defaulting to `1` unless explicitly raised;
- distinct local-only caches for sources that cannot be republished;
- audit rows for every remote fetch: provider, URL, status, cache hit, request hash, response hash,
  started_at, finished_at, and rate-limit bucket.

Scheduled GitHub Actions and Woodpecker runs should use the same containerized command surface as
local development. Local bootstrap can use larger mounted caches and personal tokens, but it still
must run inside Docker and obey provider caps.

## Current Source Plan

| Source | Role | Published use | Rate limit / fetch policy | Default cap | Evidence |
|---|---|---|---|---|---|
| manami anime-offline-database | `BACKBONE_SOURCE` | Anime facts, crossrefs, related anime, dead entries, subject to ODbL/DbCL and upstream review | Use GitHub releases, not repeated API scans | 1 release sync/day | [README/license](https://github.com/manami-project/anime-offline-database) |
| Wikidata dumps | `BACKBONE_SOURCE` | CC0 external-ID graph, adaptations, franchises, broad media links | Prefer dumps/incrementals over SPARQL/API | 1 dump sync/week | [Wikidata licensing](https://www.wikidata.org/wiki/Wikidata:Licensing) |
| TVmaze | `BACKBONE_SOURCE` | TV facts under CC BY-SA attribution/share-alike | API states at least 20 calls / 10 seconds; supports local cache/update endpoints | 10 calls / 10s | [TVmaze API](https://www.tvmaze.com/api) |
| Open Library | `BACKBONE_SOURCE` | Book/source-material links, works, editions, authors; covers separate caution | Monthly dumps; API asks for User-Agent and documents 1 req/s anonymous | 1 req/s | [Dumps](https://openlibrary.org/developers/dumps), [API](https://openlibrary.org/developers/api), [licensing](https://openlibrary.org/developers/licensing) |
| TMDB daily ID exports | `ID_SOURCE` | Valid TMDB IDs and high-level ID-export attrs only | Daily files, retained 3 months; not full exports | 1 export sync/day | [Daily exports](https://developer.themoviedb.org/docs/daily-id-exports) |
| TMDB API | `LOCAL_EVIDENCE` / `RUNTIME_ONLY` | IDs and matching evidence only; no durable mirror | Respect `429`; docs mention upper limit around 40 rps; terms cap caching at 6 months | 4 req/s | [Rate limits](https://developer.themoviedb.org/docs/rate-limiting), [terms](https://www.themoviedb.org/api-terms-of-use) |
| AniDB title dumps | `ID_SOURCE` | Anime title to AniDB AID lookup | Title dump no more than once/day | 1 sync/day | [AniDB API](https://wiki.anidb.net/API) |
| AniDB HTTP API | `LOCAL_EVIDENCE` | Local matching evidence only; do not download AniDB | Heavy cache; not more than 1 page every 2 seconds | 30 req/min | [HTTP API](https://wiki.anidb.net/HTTP_API_Definition) |
| AniList | `LOCAL_EVIDENCE` / `RUNTIME_ONLY` | IDs and relationship evidence only | Normal 90 req/min, currently degraded to 30 req/min; mass collection prohibited | 30 req/min | [rate limits](https://anilist.gitbook.io/anilist-apiv2-docs/docs/guide/rate-limiting), [terms](https://anilist.gitbook.io/anilist-apiv2-docs/docs/guide/terms-of-use) |
| MyAnimeList official API | `LOCAL_EVIDENCE` / `RUNTIME_ONLY` | IDs only unless terms are clarified | Public rate limit not clearly documented; use conservative cap and stop on `429` | 30 req/min | [API reference](https://myanimelist.net/apiconfig/references/api/v2) |
| Jikan | `LOCAL_EVIDENCE` | MAL lookup fallback only; unofficial scraper-backed API | 3 req/s and 60 req/min; MAL can still rate-limit upstream | 1 req/s, 60 req/min | [Jikan docs](https://www.postman.com/aqua5624/jikan-api/collection/m52ghbu/jikan-api-v4) |
| Kitsu | `LOCAL_EVIDENCE` | IDs/mappings only unless redistribution terms become clearer | No clear public rate limit found; conservative cap | 60 req/min | [Kitsu JSON:API docs](https://hummingbird-me.github.io/api-docs/) |
| Anime-Planet | `BLOCKED` | Only crossrefs already supplied by admissible sources | Terms prohibit automated collection/scraping | no direct fetch | [terms](https://www.anime-planet.com/termsofuse) |
| Anime News Network | `LOCAL_EVIDENCE` | Potential encyclopedia evidence; needs deeper permission before publish | No clear public rate limit found; use only targeted local checks | 30 req/min | [terms](https://www.animenewsnetwork.org/terms/) |
| Simkl | `LOCAL_EVIDENCE` / `RUNTIME_ONLY` | IDs/trending evidence only until redistribution terms are clear | Terms say fixed upper limits may be set at Simkl discretion | 60 req/min | [terms](https://simkl.com/about/policies/terms/) |
| TheTVDB | `ID_SOURCE` / `RUNTIME_ONLY` | IDs only unless licensed | No public fixed cap found; access model is project/licensed or user-supported | 60 req/min | [API info](https://thetvdb.com/api-information), [terms](https://www.thetvdb.com/tos) |
| IMDb datasets | `LOCAL_EVIDENCE` | Local research only; no public derived DB | Daily TSV datasets; no scraping; no republishing/repurposing into another DB | 1 sync/day local only | [datasets](https://developer.imdb.com/non-commercial-datasets/), [use terms](https://help.imdb.com/article/imdb/general-information/can-i-use-imdb-data-in-my-software/G5JTRESSHJBBHTGX) |
| Trakt | `LOCAL_EVIDENCE` / `RUNTIME_ONLY` | IDs/social/trending evidence only | Official fixed public cap was not confirmed; enforce conservative cap and `429` handling | 60 req/min | [API docs](https://trakt.docs.apiary.io/) |
| OMDb | `LOCAL_EVIDENCE` / `RUNTIME_ONLY` | IMDb-keyed lookup only; no copied index | Free key page lists 1,000 daily limit | 1,000 req/day | [API key page](https://www.omdbapi.com/apikey.aspx), [legal](https://www.omdbapi.com/legal.htm) |
| JustWatch | `RUNTIME_ONLY` | Availability/offers only at runtime or with partner agreement | Partner token required; branded links/attribution; no public scrape path | 60 req/min | [partner API](https://apis.justwatch.com/docs/api/), [terms](https://support.justwatch.com/hc/en-us/articles/9567105189405-JustWatch-s-Terms-of-Use) |

## CLI State On This Machine

Available:

- `uv` 0.10.6
- Python 3.12.12 via uv
- Python 3.14.4 via Homebrew
- Docker 29.4.0 via OrbStack, `aarch64`
- Docker Compose v5.1.2
- `woodpecker-cli` 3.13.0
- `gh` 2.91.0, authenticated as `alexcatdad`
- `zstd` 1.5.7
- `jq` 1.8.1
- `rg`
- `git`
- `curl`
- `bun` 1.3.13
- `node` 25.9.0
- `pipx`

Missing globally:

- `duckdb`
- `ruff`
- `pyright`

Use `uv` inside the project container for Python project tooling, so `ruff` and `pyright` should be
container/dev dependencies rather than global requirements. Install `duckdb` via Homebrew only if we
want the host CLI for ad-hoc local Parquet inspection; it must not be required for validation.
