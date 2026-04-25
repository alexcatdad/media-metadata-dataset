# Benchmark Architecture

The benchmark suite is a long-running safety system, not a one-off model shootout.
It exists to keep model and provider choices evidence-led as free offerings change.

## Goals

- Compare LLM judgment and embedding providers against versioned media fixtures.
- Reuse cached results by default so cron jobs do not waste free-tier capacity.
- Make provider auth, limits, and data-use terms explicit before any live request is allowed.
- Produce auditable artifacts that can justify model selection changes.

## Non-Goals

- Exhaustively benchmark every free model every day.
- Hide provider differences behind clever generic auth.
- Promote free-tier models to canonical use without recording data-use and provenance caveats.

## Fixture Model

Fixtures live under `benchmarks/fixtures/` as JSONL. Each row is one test case with:

- `id`: stable fixture id.
- `task`: `chat_json_judgment`, `embedding_similarity`, or a future task type.
- `domain`: media domain, such as `anime`, `movies`, or `tv`.
- `prompt_version` or `recipe_version`: stable scoring recipe identifier.
- `input`: provider-neutral input payload.
- `expected`: scoring target.
- `source`: where the fixture came from and whether it is safe to send to free-tier providers.

The first judgment fixture should be the Manami-derived Cowboy Bebop TV/movie case. Embedding
fixtures should include both positive similarity pairs and false-positive traps, such as near-title
entities that are not the same work.

## Provider Contracts

Provider contracts live under `benchmarks/providers/`. A provider cannot be enabled in cron until
its contract declares:

- Official docs URLs for pricing, authentication, and model/API reference.
- Auth scheme and exact header/query usage.
- Supported tasks.
- Models to test.
- Free-tier pricing status.
- Free-tier data-use caveats.
- Request limits, daily budgets, and maximum concurrency.
- Whether the provider may be used for canonical decisions or only benchmark lanes.
- Per-model capability and policy flags for the benchmark task:
  `supports_structured_output`, `supports_generate_content`/`supports_chat_completions`,
  `qualified_for_ranking`, and a stability classification.

Provider adapters must follow the contract exactly. Shared benchmark code may handle caching,
scoring, redaction, and scheduling, but auth/request construction stays provider-specific.

Qualified rankings must only include models with explicit task support and `qualified_for_ranking=true`.
Everything else belongs in the exploration log, not the selection table.

## Auth Rules

- Read secrets only from environment variables or CI secrets.
- Never print, persist, or include secret-derived tokens in artifacts.
- Do not infer auth schemes from key shape.
- Add a redacted request-shape test for every provider adapter.
- Prefer direct documented REST calls for benchmark adapters so auth and payloads remain visible.

Examples:

- OpenRouter: `Authorization: Bearer <OPENAI_COMPAT_API_KEY>`.
- Z.ai: `Authorization: Bearer <ZAI_API_KEY>` against `https://api.z.ai/api/paas/v4/`.
- Gemini API: `x-goog-api-key: <GOOGLE_AI_STUDIO_API_KEY>` against Gemini REST endpoints.

## Rate Safety

Cron jobs must be polite by default:

- Maximum concurrency defaults to `1` unless official docs and our account state justify more.
- Every provider has per-run request budgets.
- Every model call has a cache key:
  `provider + model + task + fixture_id + recipe_version + normalized_input_hash`.
- Cached results are reused unless `--refresh` is explicit.
- `429` responses are recorded and do not trigger retry storms.
- Full-provider discovery runs are manual or rare scheduled jobs, not daily defaults.

## Suggested Schedule

- Daily: small cached smoke against current top candidates and one rotating provider/model.
- Weekly: refresh top candidates across the current fixture corpus.
- Monthly/manual: broader discovery across new free-tier offerings.
- On provider contract changes: run only the affected provider/models.
- On fixture changes: run current top candidates against the new fixtures.

## Gemini / Google Scope

Gemini free tier is valuable but has a strong data-use caveat: free-tier content is used to improve
Google products. Gemini results therefore start as benchmark evidence, not canonical defaults.

Initial Gemini benchmark lanes:

- `chat_json_judgment`: free-of-charge text `generateContent` models from the pricing page.
- `embedding_similarity`: `gemini-embedding-001` and `gemini-embedding-2`.

Exclude Live API, TTS, image generation, robotics, computer-use, and deprecated Gemini 2.0 models
from the first judgment benchmark unless a fixture specifically targets that modality.
