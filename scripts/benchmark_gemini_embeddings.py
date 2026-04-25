from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TEXT = "Cowboy Bebop is a space western anime about bounty hunters aboard the Bebop."


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


def embedding_models(contract: dict[str, Any]) -> list[str]:
    return [
        model["id"]
        for model in contract["models"]
        if model.get("task") == "embedding_similarity"
        and model.get("free_tier") == "free_of_charge"
    ]


def build_payload(model: str, text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": {
            "parts": [
                {
                    "text": text,
                }
            ]
        }
    }
    if model == "gemini-embedding-001":
        payload["taskType"] = "SEMANTIC_SIMILARITY"
    return payload


def extract_embedding_count_and_dimensions(body: dict[str, Any]) -> tuple[int, int | None]:
    embeddings = body.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        values = embeddings[0].get("values") if isinstance(embeddings[0], dict) else None
        return len(embeddings), len(values) if isinstance(values, list) else None

    embedding = body.get("embedding")
    if isinstance(embedding, dict):
        values = embedding.get("values")
        return 1, len(values) if isinstance(values, list) else None

    return 0, None


def benchmark_model(
    *,
    client: httpx.Client,
    api_key: str,
    base_url: str,
    model: str,
    text: str,
) -> dict[str, Any]:
    payload = build_payload(model, text)

    started = time.monotonic()
    response = client.post(
        f"{base_url.rstrip('/')}/models/{model}:embedContent",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        json=payload,
        timeout=60,
    )
    latency_ms = round((time.monotonic() - started) * 1000)

    base = {
        "provider": "gemini",
        "model": model,
        "task": "embedding_latency",
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
            "error_status": error.get("status"),
        }

    body = response.json()
    embedding_count, dimensions = extract_embedding_count_and_dimensions(body)

    return {
        **base,
        "reachable": embedding_count > 0 and dimensions is not None,
        "embedding_count": embedding_count,
        "dimensions": dimensions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider-contract",
        type=Path,
        default=Path("benchmarks/providers/gemini.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".mod/out/benchmarks/gemini-embeddings"),
    )
    parser.add_argument("--models", default="")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--base-url", default=os.environ.get("GEMINI_BASE_URL", GEMINI_BASE_URL))
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=float(os.environ.get("GEMINI_BENCHMARK_DELAY_SECONDS", "4")),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("GOOGLE_AI_STUDIO_API_KEY")
    if not api_key:
        raise SystemExit("GOOGLE_AI_STUDIO_API_KEY is required")

    contract = load_json(args.provider_contract)
    models = (
        [model.strip() for model in args.models.split(",") if model.strip()]
        if args.models
        else embedding_models(contract)
    )
    per_run_budget = contract["limits"]["per_run_request_budget"]
    if len(models) > per_run_budget:
        raise SystemExit(
            f"Refusing to run {len(models)} models; contract per-run budget is {per_run_budget}"
        )

    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=30) as client:
        for index, model in enumerate(models):
            if index > 0 and args.delay_seconds > 0:
                time.sleep(args.delay_seconds)
            print(f"[{index + 1}/{len(models)}] {model}", flush=True)
            rows.append(
                benchmark_model(
                    client=client,
                    api_key=api_key,
                    base_url=args.base_url,
                    model=model,
                    text=args.text,
                )
            )

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_count": len(models),
        "provider": "gemini",
        "task": "embedding_latency",
        "documented_auth": "x-goog-api-key",
        "text_length": len(args.text),
        "models": models,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "metadata.json", metadata)
    write_jsonl(args.output_dir / "results.jsonl", rows)
    write_json(args.output_dir / "results.json", rows)
    print(f"Wrote embedding benchmark results to {args.output_dir}")


if __name__ == "__main__":
    main()
