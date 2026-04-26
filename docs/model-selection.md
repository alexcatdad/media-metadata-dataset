# Model Selection

Last reviewed: 2026-04-26.

The project prefers free-access model providers for canonical runs. This is not only a cost
preference: it keeps the pipeline reproducible by ordinary contributors and avoids making public
artifacts look like privileged derivative works built from paid access.

Free access does not make a provider legally safe by itself. Inputs must still be allowed by source
policy, and all model calls must be cached, budgeted, and auditable.

Local inference is the prompt-calibration baseline, not the canonical publication backend. The best
model that runs reliably on the local Mac should be used as the measuring stick for relationship
prompt and parameter tuning before comparing cloud variants. If clearer prompt wording lets smaller
or lower-quality local models recover the same relevant relationship judgments as larger cloud
models, prefer the clearer prompt over relying on more tokens or larger hosted models.

## Canonical Defaults

| Task | Provider | Model | Why |
|---|---|---|---|
| Entity/document embeddings | Cloudflare Workers AI | `@cf/baai/bge-m3` | Free daily allocation, cloud CI friendly, multilingual, long context, documented embedding API, and Cloudflare says Workers AI customer content is not used to train or improve models/services without explicit consent. |
| LLM structured judgment | Pending | TBD after more fixtures | The fresh qualified rerun cleaned up the benchmark lane, but one Cowboy Bebop-derived case is still too small to lock a canonical judgment model. The current leaderboard is useful evidence, not final policy. |

## Current Qualified Judgment Leaderboard

These are the best results from the fresh qualified rerun. They are the models we should keep
testing first as the fixture corpus grows.

| Rank | Provider | Model | Why |
|---:|---|---|---|
| 1 | OpenRouter | `liquid/lfm-2.5-1.2b-instruct:free` | Fastest correct valid JSON result in the clean rerun at 831 ms. Keep a caution flag because advertised structured-output support is still unclear. |
| 2 | Gemini API free tier | `gemini-2.5-flash-lite` | Best Gemini result in the clean rerun at 1210 ms. Benchmark-only because Google documents that free-tier content is used to improve products. |
| 3 | Gemini API free tier | `gemma-4-26b-a4b-it` | Correct valid JSON in the direct Gemini lane at 2387 ms. This is a much more intuitive Gemma result than the earlier mixed-lane picture. |
| 4 | Gemini API free tier | `gemma-4-31b-it` | Correct valid JSON in the direct Gemini lane at 3089 ms. |
| 5 | OpenRouter | `openai/gpt-oss-20b:free` | Correct valid JSON with a more comfortable stability posture than preview models, at 3996 ms. |

Do not use `openrouter/free` for canonical decisions because it selects from free models dynamically.
It is acceptable for experiments and smoke tests where model identity is not part of the artifact.

Do not promote Z.ai `glm-4.7-flash` to primary until a later benchmark proves availability. The first
direct Z.ai GLM run returned service overload for `glm-4.7-flash`; `glm-4.5-flash` was reachable,
valid JSON, and correct, but slower than the current OpenRouter primary on the first Manami-derived
case.

Do not promote Gemini free-tier models to canonical use without a policy decision. `gemini-2.5-flash-lite`
is empirically strong on the first Manami-derived judgment fixture, but Google documents that free-tier
content is used to improve products.

## Secondary / Benchmark Routes

| Task | Provider | Model | Status |
|---|---|---|---|
| Embedding benchmark | Gemini API free tier | `gemini-embedding-001` | Strong free text embedding option, but Google documents that free-tier content is used to improve products. Use only for benchmark lanes or explicitly source-safe public text unless a later decision promotes it. |
| Multimodal embedding benchmark | Gemini API free tier | `gemini-embedding-2` | Free standard tier for text/image/audio/video embeddings. First latency baseline returned 3072 dimensions in 323 ms, faster than `gemini-embedding-001` on the same tiny input. Keep benchmark-only unless policy changes. |
| Embedding fallback/benchmark | Jina AI | provider default / configured Jina embedding model | Good free limits and multilingual models. Use for comparison and fallback after we review data usage terms in more detail. |
| Embedding fallback/experiment | Hugging Face Inference Providers | configured feature-extraction model | Useful for portability checks, but free credits are too small for canonical bulk runs. |
| Embedding fallback/experiment | OpenRouter embeddings | `nvidia/llama-nemotron-embed-vl-1b-v2:free` | Current free embedding model surfaced by OpenRouter. Use only after confirming availability at run time. |
| LLM judgment benchmark/preferred candidate | Z.ai | `glm-4.7-flash` | Free for account/API-key users and concurrency-limited rather than daily request-limited, but still not promotable after overload responses in direct tests. |
| LLM judgment benchmark/preferred candidate | Z.ai | `glm-4.5-flash` | Correct valid JSON in the clean direct rerun, but slower than the leading OpenRouter models. |
| LLM judgment benchmark | Gemini API free tier | `gemini-2.5-flash-lite` | Correct, valid JSON, and fast in the clean rerun. Benchmark-only until policy says otherwise. |
| LLM judgment benchmark | Gemini API free tier | `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | Both direct Gemma 4 models produced correct valid JSON in the Gemini lane once the real model ids were discovered via `listModels`. |
| LLM judgment benchmark | Gemini API free tier | `gemma-3-1b-it`, `gemma-3-4b-it`, `gemma-3-12b-it`, `gemma-3-27b-it`, `gemma-3n-e4b-it`, `gemma-3n-e2b-it` | Exposed for the key, but Gemini JSON mode is not enabled for them, so they are not usable for the current structured-output benchmark recipe. |
| LLM judgment benchmark | Gemini API free tier | `gemini-3.1-flash-lite-preview` | Correct and valid JSON in the clean rerun, but materially slower than `gemini-2.5-flash-lite`. |
| LLM judgment benchmark | Gemini API free tier | `gemini-3-flash-preview` | Correct and valid JSON in the clean rerun after the fixed recipe. Strong candidate, just slower on the current fixture. |
| LLM judgment benchmark | Gemini API free tier | `gemini-2.5-flash` | Still failed the clean rerun by truncating JSON, so it drops out of the qualified lane for now. |
| LLM judgment benchmark | Gemini API free tier | `gemini-2.5-pro`, `gemma-4`, `gemini-2.5-flash-lite-preview-09-2025` | Listed/priced as interesting free candidates, but not usable yet due quota or model-id/API support errors. |
| LLM judgment benchmark | OpenRouter free models | `google/gemma-4-26b-a4b-it:free`, `google/gemma-4-31b-it:free`, `qwen/qwen3-coder:free` | Still in the qualified candidate pool, but the fresh rerun hit upstream 429s, so there is no useful ranking evidence yet. |
| LLM judgment benchmark | OpenRouter free models | `nvidia/nemotron-3-super-120b-a12b:free`, `nvidia/nemotron-3-nano-30b-a3b:free`, `nvidia/nemotron-nano-9b-v2:free`, `z-ai/glm-4.5-air:free` | Reachable in the fresh rerun, but returned truncated or empty responses on this recipe. Keep as candidates, not current leaders. |

## Runtime Rules

- Cache every model call by task, provider, model, prompt/input recipe version, and normalized input
  hash.
- Tune prompt and inference parameters against the strongest practical local model first, then compare
  cloud providers against that frozen local measuring-stick recipe.
- Qualified rankings only include models whose provider contract marks them `qualified_for_ranking=true`
  for that task. Preview, discovery, unstable, unavailable, or task-misaligned models stay in
  exploration artifacts only.
- Store provider, model, endpoint family, prompt/input recipe version, dimensions, and generated_at
  in artifact metadata.
- Never re-embed unchanged rows.
- Enforce daily request/token/neuron budgets before making calls.
- Stop cleanly and leave queued work when budgets are exhausted.
- Re-evaluate model choices before publishing the first public dataset and whenever provider free
  offerings change.
- Human corrections become eval cases before changing canonical LLM models.

## Current Free-Tier Notes

- Cloudflare Workers AI has a free daily allocation and lists `@cf/baai/bge-m3` at a low per-token
  rate above free allocation.
- Cloudflare Workers AI supports OpenAI-compatible `/v1/embeddings`.
- OpenRouter free models are capped and availability may change. Current no-credit accounts are
  documented at 50 free-model requests/day and 20 requests/minute.
- Full-catalog benchmarks must be explicit and rare. The benchmark script defaults to five models,
  waits between calls, and requires `--all` before testing every free model.
- Z.ai's general endpoint is `https://api.z.ai/api/paas/v4/`, with OpenAI-compatible chat
  completions under `/chat/completions`. The project stores split `Z_AI_API_KEY_ID` /
  `Z_AI_API_KEY_SECRET` fields. If the secret value is already the joined `id.secret` API key, the
  runner uses it directly; otherwise it joins the id and secret half. Requests use
  `Authorization: Bearer <ZAI_API_KEY>`. Keep `Z_AI_MAX_CONCURRENCY=1` unless their account-level
  limits change.
- Gemini API free tier includes `gemini-embedding-001`, but free-tier content is used to improve
  Google products. First direct latency baseline: `gemini-embedding-001` returned one 3072-d vector
  in 485 ms; `gemini-embedding-2` returned one 3072-d vector in 323 ms.
- Gemini REST benchmark calls use `x-goog-api-key` and `generateContent`; no JWT/OAuth/OpenAI-compatible
  auth assumptions are allowed for this lane.
- Gemini 3 Flash needed a simpler structured-output payload and a larger output cap. The fixed
  payload removes `systemInstruction`, puts the JSON-only instruction in the user content, adds
  schema descriptions/property ordering, and uses `maxOutputTokens=500`.
- Hugging Face Inference Providers support feature extraction, but the free user credit pool is too
  small to treat as the canonical bulk embedding backend.
