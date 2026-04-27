# Provider HTTP Runbook

Use this runbook when adding or changing source-provider HTTP access. Do not run project pipeline
tasks on host Python.

## Rule

Provider adapters in `src/media_offline_database` must not call `httpx` directly. Add or reuse a
`ProviderHttpClient` in `provider_http.py` and give it a provider-specific rate limit, retry policy,
and default headers.

## Current Clients

- AniList: 30 requests/minute, transient retry, `Retry-After`, and `X-RateLimit-Reset`.
- TVmaze: 10 requests/10 seconds, transient retry, and `Retry-After`.
- Wikidata query service: 1 request/second, transient retry, and `Retry-After`.

## Adding A Provider

1. Classify the source in `docs/source-admissibility-and-rate-limits.md`.
2. Record or update the accepted rate-limit evidence and default cap.
3. Add a named `ProviderHttpClient` in `src/media_offline_database/provider_http.py`.
4. Route the adapter through that client instead of direct `httpx`.
5. Add tests for rate spacing, retry behavior, and any provider reset header.
6. Run validation in Docker:

```sh
docker compose run --rm app uv run --extra dev ruff check .
docker compose run --rm app uv run --extra dev pyright
docker compose run --rm app uv run pytest
```

## Current Limits

The shared client is an in-process control. It spaces request starts, caps retries, honors
`Retry-After`, and supports provider reset epoch headers. Persistent cache, budget ledgers, and
cross-process concurrency guards remain future work before large scheduled crawls.
