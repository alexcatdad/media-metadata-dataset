from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def redact_key_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if key in {"label", "creator_user_id"} else redact_key_metadata(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_key_metadata(item) for item in value]
    return value


def fetch_free_models(client: httpx.Client) -> list[dict[str, Any]]:
    response = client.get(f"{OPENROUTER_BASE_URL}/models")
    response.raise_for_status()
    models = response.json()["data"]
    free_models = [
        model
        for model in models
        if (
            model["id"].endswith(":free")
            or (
                model.get("pricing", {}).get("prompt") == "0"
                and model.get("pricing", {}).get("completion") == "0"
            )
        )
        and "text" in model.get("architecture", {}).get("output_modalities", [])
    ]
    return sorted(free_models, key=lambda model: model["id"])


def fetch_key_metadata(client: httpx.Client, api_key: str) -> dict[str, Any]:
    response = client.get(
        f"{OPENROUTER_BASE_URL}/key",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    response.raise_for_status()
    return redact_key_metadata(response.json()["data"])


def build_prompt(case: dict[str, Any]) -> str:
    return f"""
You judge anime identity and relationship records.

Return only a JSON object with this exact shape:
{{
  "same_entity": boolean,
  "relationship": "same_entity" | "movie_related" | "special_related" | "sequel_prequel" | "remake_reboot" | "unrelated" | "uncertain",
  "confidence": number,
  "reasoning": string
}}

Question:
Are record_a and record_b the same anime database entity, or separate related entities?

Use only the provided source records. Do not invent facts.

Case:
{stable_json(case)}
""".strip()


def extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def score_result(parsed: dict[str, Any] | None, expected: dict[str, Any]) -> dict[str, Any]:
    if parsed is None:
        return {"valid_json": False, "correct_same_entity": False, "correct_relationship": False}

    return {
        "valid_json": True,
        "correct_same_entity": parsed.get("same_entity") == expected["same_entity"],
        "correct_relationship": parsed.get("relationship") == expected["relationship"],
    }


def benchmark_model(
    *,
    client: httpx.Client,
    api_key: str,
    model: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any]:
    model_id = model["id"]
    supported_parameters = model.get("supported_parameters") or []
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a precise JSON-only media metadata judge."},
            {"role": "user", "content": build_prompt(case)},
        ],
        "max_tokens": 180,
        "temperature": 0,
    }
    if "response_format" in supported_parameters or "structured_outputs" in supported_parameters:
        payload["response_format"] = {"type": "json_object"}

    started = time.monotonic()
    response = client.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/alexcatdad/media-metadata-dataset",
            "X-Title": "media-metadata-dataset benchmark",
        },
        json=payload,
        timeout=60,
    )
    latency_ms = round((time.monotonic() - started) * 1000)

    base = {
        "model": model_id,
        "context_length": model.get("context_length"),
        "supported_parameters": supported_parameters,
        "used_response_format": "response_format" in payload,
        "latency_ms": latency_ms,
        "http_status": response.status_code,
    }

    if response.status_code >= 400:
        try:
            error = response.json().get("error", {})
        except json.JSONDecodeError:
            error = {"message": response.text[:500]}
        return {
            **base,
            "reachable": False,
            "error_code": error.get("code"),
            "error_message": error.get("message"),
            "provider_name": (error.get("metadata") or {}).get("provider_name"),
            "raw_error": (error.get("metadata") or {}).get("raw"),
        }

    body = response.json()
    if "choices" not in body:
        return {
            **base,
            "reachable": False,
            "error_code": "unexpected_response",
            "error_message": "Response did not include choices.",
            "response_keys": sorted(body.keys()),
        }

    content = body["choices"][0]["message"].get("content") or ""
    parsed = extract_json_object(content)
    scores = score_result(parsed, case["expected"])

    return {
        **base,
        "reachable": True,
        "content": content,
        "parsed": parsed,
        **scores,
    }


def write_markdown_summary(path: Path, *, rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    reachable = [row for row in rows if row["reachable"]]
    valid = [row for row in reachable if row.get("valid_json")]
    correct = [
        row
        for row in valid
        if row.get("correct_same_entity") and row.get("correct_relationship")
    ]

    lines = [
        "# OpenRouter Free Model Benchmark",
        "",
        f"Generated: {metadata['generated_at']}",
        f"Models tested: {len(rows)}",
        f"Reachable: {len(reachable)}",
        f"Valid JSON: {len(valid)}",
        f"Correct: {len(correct)}",
        "",
        "Documented free-model limits: 20 requests/minute; daily limits depend on account state.",
        "",
        "| Model | Reachable | JSON | Correct | Latency ms | Error |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        error = row.get("raw_error") or row.get("error_message") or ""
        if len(error) > 100:
            error = error[:97] + "..."
        lines.append(
            "| {model} | {reachable} | {valid_json} | {correct} | {latency} | {error} |".format(
                model=row["model"],
                reachable="yes" if row["reachable"] else "no",
                valid_json="yes" if row.get("valid_json") else "no",
                correct=(
                    "yes"
                    if row.get("correct_same_entity") and row.get("correct_relationship")
                    else "no"
                ),
                latency=row["latency_ms"],
                error=error.replace("|", "\\|").replace("\n", " "),
            )
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(".mod/out/benchmarks/openrouter-free"))
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum models tested. Default is intentionally small to respect free daily limits.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Test every discovered free model. Use only for explicit benchmark runs.",
    )
    parser.add_argument("--delay-seconds", type=float, default=4.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("OPENAI_COMPAT_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_COMPAT_API_KEY is required")

    case = load_json(args.case_file)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=30) as client:
        models = fetch_free_models(client)
        if not args.all:
            models = models[: args.limit]
        key_metadata = fetch_key_metadata(client, api_key)

        rows: list[dict[str, Any]] = []
        incremental_results_path = args.output_dir / "results.incremental.jsonl"
        incremental_results_path.unlink(missing_ok=True)
        for index, model in enumerate(models):
            if index > 0 and args.delay_seconds > 0:
                time.sleep(args.delay_seconds)
            print(f"[{index + 1}/{len(models)}] {model['id']}", flush=True)
            row = benchmark_model(client=client, api_key=api_key, model=model, case=case)
            rows.append(row)
            append_jsonl(incremental_results_path, row)

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "case_file": str(args.case_file),
        "key_metadata": key_metadata,
        "model_count": len(models),
        "documented_limits": {
            "free_models_requests_per_minute": 20,
            "free_models_requests_per_day_without_10_usd_credits": 50,
            "free_models_requests_per_day_with_10_usd_credits": 1000,
        },
    }

    write_json(args.output_dir / "metadata.json", metadata)
    write_json(args.output_dir / "free-models.json", models)
    write_jsonl(args.output_dir / "results.jsonl", rows)
    write_json(args.output_dir / "results.json", rows)
    write_markdown_summary(args.output_dir / "summary.md", rows=rows, metadata=metadata)
    print(f"Wrote benchmark results to {args.output_dir}")


if __name__ == "__main__":
    main()
