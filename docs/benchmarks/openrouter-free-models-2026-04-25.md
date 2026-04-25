# OpenRouter Free Model Benchmark, 2026-04-25

Benchmark input used a Manami `2026-14` release case:

- record A: `Cowboy Bebop`, TV, 1998, 26 episodes
- record B: `Cowboy Bebop: Tengoku no Tobira`, movie, 2001, 1 episode
- expected output: `same_entity=false`, `relationship=movie_related`

Prompt required a JSON object with `same_entity`, `relationship`, `confidence`, and `reasoning`.

## Rate Limits

OpenRouter docs currently describe free-model limits as 20 requests/minute. Daily free-model limits
depend on account state: 50 requests/day without at least 10 USD purchased credits and 1000
requests/day after that threshold.

The API key metadata endpoint returned a deprecated key-level `rate_limit` field and did not expose
reliable per-model free capacity. Per-model/provider availability must therefore be treated as an
observed runtime property. This run recorded multiple upstream 429s even though requests were paced
with a 2-second delay.

## Summary

- Models discovered as free text-output routes: 30
- Reachable: 13
- Valid JSON: 6
- Correct JSON answer: 6

| Model | Reachable | Valid JSON | Correct | Latency ms | Note |
|---|---:|---:|---:|---:|---|
| `liquid/lfm-2.5-1.2b-instruct:free` | yes | yes | yes | 793 | Fastest correct result, but no advertised structured-output support. |
| `inclusionai/ling-2.6-flash:free` | yes | yes | yes | 1417 | Best primary candidate: correct, reachable, structured-output capable. |
| `inclusionai/ling-2.6-1t:free` | yes | yes | yes | 2628 | Correct with structured-output support. |
| `baidu/qianfan-ocr-fast:free` | yes | yes | yes | 2678 | Correct despite OCR-oriented catalog label. |
| `openai/gpt-oss-20b:free` | yes | yes | yes | 4239 | Correct fallback. |
| `openai/gpt-oss-120b:free` | yes | yes | yes | 5713 | Correct but slower than 20b. |
| `nvidia/nemotron-3-super-120b-a12b:free` | yes | no | no | 8225 | Began correct JSON but truncated before completion under benchmark max-token settings. |
| `qwen/qwen3-next-80b-a3b-instruct:free` | no | no | no | 407 | Upstream provider 429 via Venice. |
| `qwen/qwen3-coder:free` | no | no | no | 330 | Upstream provider 429 via Venice. |
| `openrouter/free` | yes | no | no | 1724 | Dynamic router is not suitable for canonical decisions. |

## Decision Impact

The previous docs-based choice of `qwen/qwen3-next-80b-a3b-instruct:free` should not remain the
primary model. It may be revisited later, but current real-world availability is poor.

Use this order for now:

1. `inclusionai/ling-2.6-flash:free`
2. `inclusionai/ling-2.6-1t:free`
3. `liquid/lfm-2.5-1.2b-instruct:free`
4. `openai/gpt-oss-20b:free`
5. `baidu/qianfan-ocr-fast:free`

Raw local run artifacts were written under `.mod/out/benchmarks/openrouter-free/`.
