# Model Selection

Last reviewed: 2026-04-25.

The project prefers free-access model providers for canonical runs. This is not only a cost
preference: it keeps the pipeline reproducible by ordinary contributors and avoids making public
artifacts look like privileged derivative works built from paid access.

Free access does not make a provider legally safe by itself. Inputs must still be allowed by source
policy, and all model calls must be cached, budgeted, and auditable.

## Canonical Defaults

| Task | Provider | Model | Why |
|---|---|---|---|
| Entity/document embeddings | Cloudflare Workers AI | `@cf/baai/bge-m3` | Free daily allocation, cloud CI friendly, multilingual, long context, documented embedding API, and Cloudflare says Workers AI customer content is not used to train or improve models/services without explicit consent. |
| LLM structured judgment | OpenRouter free model | `inclusionai/ling-2.6-flash:free` | Empirical benchmark winner for the first Manami-derived identity/relationship task: reachable, valid JSON, correct, structured-output capable, and low latency. |
| LLM judgment fallback | OpenRouter free model | `inclusionai/ling-2.6-1t:free` | Correct JSON result in benchmark with structured-output support and moderate latency. |
| LLM judgment fallback | OpenRouter free model | `liquid/lfm-2.5-1.2b-instruct:free` | Fastest correct JSON result in benchmark, but lacks advertised structured-output support, so keep as fallback rather than primary. |
| LLM judgment fallback | OpenRouter free model | `openai/gpt-oss-20b:free` | Correct JSON result in benchmark with moderate latency. |
| LLM judgment fallback | OpenRouter free model | `baidu/qianfan-ocr-fast:free` | Correct JSON result in benchmark; surprising but usable as a late fallback. |

Do not use `openrouter/free` for canonical decisions because it selects from free models dynamically.
It is acceptable for experiments and smoke tests where model identity is not part of the artifact.

Do not use `qwen/qwen3-next-80b-a3b-instruct:free` as the primary until a later benchmark proves it
is reliably reachable. It looked strong in docs/catalog metadata but was upstream rate-limited in the
first real benchmark.

## Secondary / Benchmark Routes

| Task | Provider | Model | Status |
|---|---|---|---|
| Embedding benchmark | Gemini API free tier | `gemini-embedding-001` | Strong free text embedding option, but Google documents that free-tier content is used to improve products. Use only for benchmark lanes or explicitly source-safe public text unless a later decision promotes it. |
| Multimodal embedding benchmark | Gemini API free tier | `gemini-embedding-2` | Free standard tier for text/image/audio/video embeddings. Keep experimental until we actually need multimodal. |
| Embedding fallback/benchmark | Jina AI | provider default / configured Jina embedding model | Good free limits and multilingual models. Use for comparison and fallback after we review data usage terms in more detail. |
| Embedding fallback/experiment | Hugging Face Inference Providers | configured feature-extraction model | Useful for portability checks, but free credits are too small for canonical bulk runs. |
| Embedding fallback/experiment | OpenRouter embeddings | `nvidia/llama-nemotron-embed-vl-1b-v2:free` | Current free embedding model surfaced by OpenRouter. Use only after confirming availability at run time. |

## Runtime Rules

- Cache every model call by task, provider, model, prompt/input recipe version, and normalized input
  hash.
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
- Gemini API free tier includes `gemini-embedding-001`, but free-tier content is used to improve
  Google products.
- Hugging Face Inference Providers support feature extraction, but the free user credit pool is too
  small to treat as the canonical bulk embedding backend.
