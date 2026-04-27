# Provider HTTP Runbook

Use this runbook when adding or changing source-provider HTTP access. Do not run project pipeline
tasks on host Python.

## Rule

Provider adapters in `src/media_offline_database` must not call `httpx` directly. Add or reuse a
`ProviderHttpClient` in `provider_http.py` and give it a provider-specific rate limit, retry policy,
and default headers.

## Current Clients

- AniList: 30 requests/minute, 1,000 remote attempts/day, transient retry, `Retry-After`, and
  `X-RateLimit-Reset`.
- TVmaze: 10 requests/10 seconds, 1,000 remote attempts/day, transient retry, and `Retry-After`.
- Wikidata query service: 1 request/second, 250 remote attempts/day, transient retry, and
  `Retry-After`.

Daily budget ledgers are stored under `.mod/cache/provider-http/budgets` by default. Set
`MOD_PROVIDER_HTTP_BUDGET_DIR` to move that ledger for tests or isolated runs.

Refresh run guards are stored under `.mod/cache/provider-http/locks` by default and prevent duplicate
active refresh scopes. Set `PROVIDER_RUN_GUARD_STALE_SECONDS` to tune stale-lock replacement.

## Adding A Provider

1. Classify the source in `docs/source-admissibility-and-rate-limits.md`.
2. Record or update the accepted rate-limit evidence and default cap.
3. Add a named `ProviderHttpClient` in `src/media_offline_database/provider_http.py`.
4. Route the adapter through that client instead of direct `httpx`.
5. Add tests for rate spacing, retry behavior, daily budget behavior, and any provider reset header.
6. Run validation in Docker:

```sh
docker compose run --rm app uv run --extra dev ruff check .
docker compose run --rm app uv run --extra dev pyright
docker compose run --rm app uv run pytest
```

## Current Limits

The shared client spaces request starts in-process, caps retries, honors `Retry-After`, supports
provider reset epoch headers, and persists daily request budget ledgers. Local refresh run guards
block duplicate active refresh scopes on the same mounted cache. Persistent response caching remains
future work because provider-run `request_count` and `cache_hit_count` must stay accurate.
