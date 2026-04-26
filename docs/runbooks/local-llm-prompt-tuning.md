# Local LLM Prompt-Tuning Runbook

Use this runbook to test local LLM inference while tuning judgment prompts. This is prompt evaluation, not model fine-tuning or training.

## Purpose

- Compare local models on versioned judgment fixtures.
- Catch JSON-shape failures and relationship-label mistakes before promoting a prompt recipe.
- Find the best prompt and parameter combo that lets the strongest practical local model act as the calibration baseline.
- Keep project execution inside Docker/Compose while allowing the local model server to run on the host or another machine.

## Inputs

- Relationship fixture: `benchmarks/fixtures/anime-chat-judgment-v1.jsonl`
- Inferred-facet fixture: `benchmarks/fixtures/media-facet-inference-judgment-v1.jsonl`
- Ollama harness: `scripts/benchmark_ollama_local.py`
- OpenAI-compatible local harness: `scripts/benchmark_openai_compat_local.py`
- Output root: `.mod/out/benchmarks/`

## Preconditions

1. Start or verify the local model server outside the project container.
2. Choose a small model list first.
3. Confirm any prompt or payload change has a clear recipe name in notes or code before comparing results across runs.
4. Do not publish local model outputs as source metadata; treat them as derived benchmark judgments.

## Local Measuring Stick

The local target is not the highest theoretical model quality. This Mac is not inference-optimized, so choose the best model that runs reliably enough to iterate on fixtures and prompt variants.

Use that local model, prompt recipe, and parameter set as the measuring stick for cloud variants:

- First, tune ambiguous relationship wording until the local model reliably separates meaningful dataset connections from loose thematic similarity.
- Then, freeze the local recipe name and parameters before comparing cloud providers.
- Treat a cloud model as interesting when it matches or beats the local measuring-stick recipe on the same fixtures, with better latency, reliability, cost, or policy posture.
- Do not promote a larger cloud model only because it handles an ambiguous prompt better; prefer the clearer prompt that lets lower-quality models extract the same relevant judgment.

## Ollama Path

On the host, confirm Ollama is reachable and the target model exists:

```sh
ollama list
ollama pull qwen3:4b
```

Run the benchmark through Compose so project Python stays containerized:

```sh
docker compose run --rm app uv run python scripts/benchmark_ollama_local.py \
  --case-file benchmarks/fixtures/anime-chat-judgment-v1.jsonl \
  --models qwen3:4b \
  --base-url http://host.docker.internal:11434 \
  --delay-seconds 1 \
  --output-dir .mod/out/benchmarks/ollama-local/qwen3-4b-prompt-baseline
```

Use a LAN URL instead of `host.docker.internal` when the Ollama server is not on the Docker host.

## OpenAI-Compatible Local Path

Use this path for LM Studio, llama.cpp server, vLLM, or another local OpenAI-compatible `/v1/chat/completions` server.

Run the benchmark through Compose:

```sh
docker compose run --rm app uv run python scripts/benchmark_openai_compat_local.py \
  --case-file benchmarks/fixtures/anime-chat-judgment-v1.jsonl \
  --models local-model-id \
  --base-url http://host.docker.internal:1234/v1 \
  --delay-seconds 1 \
  --output-dir .mod/out/benchmarks/openai-compat-local/local-model-id-prompt-baseline
```

## Review Outputs

Each run writes:

- `metadata.json`: model list, fixture path, generated time, provider, and endpoint.
- `results.jsonl`: one row per case/model attempt.
- `results.incremental.jsonl`: OpenAI-compatible local path only; useful for interrupted runs.
- `summary.md`: compact table of reachability, JSON validity, correctness, latency, and errors.

Check the summary first:

```sh
docker compose run --rm app sh -lc 'sed -n "1,120p" .mod/out/benchmarks/ollama-local/qwen3-4b-prompt-baseline/summary.md'
```

Then inspect failed rows:

```sh
docker compose run --rm app uv run python - <<'PY'
import json
from pathlib import Path

path = Path(".mod/out/benchmarks/ollama-local/qwen3-4b-prompt-baseline/results.jsonl")
for line in path.read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    if not row.get("valid_json") or not row.get("correct_relationship"):
        print(json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True))
PY
```

## Prompt-Tuning Loop

1. Change only one prompt or schema variable at a time.
2. Record the recipe name in the output directory, for example `relationship-rules-v2`.
3. Record the inference parameters with the run, especially temperature, context length, max tokens, and structured-output mode.
4. Rerun the same fixture and model list.
5. Compare valid JSON rate, relationship correctness, and latency.
6. Expand the fixture set before treating a prompt as generally better.
7. Record accepted prompt or model-selection changes in `docs/decisions.jsonl`.

## Validation

After editing benchmark code or fixtures, run the project gates inside the container:

```sh
docker compose run --rm app uv run ruff check .
docker compose run --rm app uv run pyright
docker compose run --rm app uv run pytest
```

## Failure Notes

- Connection refused from inside Docker usually means the base URL points at container localhost. Use `host.docker.internal` on Docker Desktop or a reachable LAN URL.
- Empty or prose responses mean the model or server may not honor structured output. Prefer OpenAI-compatible servers that support JSON schema, or keep the model out of prompt-comparison rankings.
- Slow first responses often include model load time. Repeat runs can be faster if the server keeps the model warm.
