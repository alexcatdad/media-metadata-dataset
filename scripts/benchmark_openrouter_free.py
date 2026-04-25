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
PROMPT_PROFILES = {"baseline", "taxonomy_no_reasoning"}
RELATIONSHIP_LABELS = {
    "same_entity",
    "movie_related",
    "special_related",
    "sequel_prequel",
    "remake_reboot",
    "unrelated",
    "uncertain",
}


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


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


def normalize_case(raw_case: dict[str, Any], *, default_id: str) -> dict[str, Any]:
    if "input" in raw_case:
        record_a = raw_case["input"]["record_a"]
        record_b = raw_case["input"]["record_b"]
        expected = raw_case["expected"]
        return {
            "id": raw_case.get("id", default_id),
            "task": raw_case.get("task", "chat_json_judgment"),
            "source": raw_case.get("source", "unknown"),
            "record_a": record_a,
            "record_b": record_b,
            "expected": expected,
            "notes": raw_case.get("notes", ""),
        }

    return {
        "id": raw_case.get("id", default_id),
        "task": raw_case.get("task", "chat_json_judgment"),
        "source": raw_case.get("source", "unknown"),
        "record_a": raw_case["record_a"],
        "record_b": raw_case["record_b"],
        "expected": raw_case["expected"],
        "notes": raw_case.get("notes", ""),
    }


def load_cases(path: Path) -> list[dict[str, Any]]:
    raw_cases = load_jsonl(path) if path.suffix == ".jsonl" else [load_json(path)]
    cases = [normalize_case(raw_case, default_id=f"case-{index + 1}") for index, raw_case in enumerate(raw_cases)]
    for case in cases:
        expected = case["expected"]
        relationship = expected["relationship"]
        if relationship not in RELATIONSHIP_LABELS:
            raise ValueError(f"Invalid relationship label {relationship!r} in {case['id']}")
    return cases


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


def load_provider_contract(path: Path) -> dict[str, Any]:
    return load_json(path)


def qualified_models_from_contract(contract: dict[str, Any]) -> list[str]:
    return [
        model["id"]
        for model in contract["models"]
        if model.get("task") == "chat_json_judgment"
        and model.get("qualified_for_ranking") is True
    ]


def fetch_key_metadata(client: httpx.Client, api_key: str) -> dict[str, Any]:
    response = client.get(
        f"{OPENROUTER_BASE_URL}/key",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    response.raise_for_status()
    return redact_key_metadata(response.json()["data"])


def build_prompt(case: dict[str, Any], *, prompt_profile: str) -> str:
    if prompt_profile not in PROMPT_PROFILES:
        raise ValueError(f"Unsupported prompt profile {prompt_profile!r}")

    if prompt_profile == "taxonomy_no_reasoning":
        return f"""
You judge anime identity and relationship records.

Task:
Return whether record_a and record_b are the same anime database entity or separate entities,
and if separate, choose the best relationship label.

Use only the provided source records. Do not invent facts.

Return only a JSON object with this exact shape:
{{
  "same_entity": boolean,
  "relationship": "same_entity" | "movie_related" | "special_related" | "sequel_prequel" | "remake_reboot" | "unrelated" | "uncertain",
  "confidence": number
}}

Relationship rules:
- same_entity: same work, same release, same core record, maybe with different source subsets or synonym slices.
- movie_related: one entry is a MOVIE and the other is a non-movie entry from the same franchise.
- special_related: one entry is a SPECIAL and the other is the main TV/OVA/ONA entry from the same franchise.
- sequel_prequel: direct continuation or earlier/later installment of the same adaptation line.
- remake_reboot: alternate adaptation, reboot, retelling, or different adaptation line of the same core work.
- unrelated: similar words, tags, genres, or vibes are not enough; use this when they are different works.
- uncertain: only if the provided evidence is genuinely insufficient.

Decision rules:
- Do not use sequel_prequel as a generic "same franchise" bucket.
- If one entry is MOVIE and the other is not, prefer movie_related.
- If one entry is literally type SPECIAL and the other is a main entry, prefer special_related.
- movie_related requires an actual MOVIE type. special_related requires an actual SPECIAL type. OVA and ONA are neither by default.
- If titles indicate an alternate adaptation or branding like Brotherhood or Ultimate, prefer remake_reboot.
- If the records share only a word in the title or broad genre/tag overlap, prefer unrelated.
- same_entity should be strict: do not use it for movies, specials, sequels, or alternate adaptations.

Case:
{stable_json({
    "record_a": case["record_a"],
    "record_b": case["record_b"],
    "notes": case.get("notes", ""),
})}
""".strip()

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
{stable_json({
    "record_a": case["record_a"],
    "record_b": case["record_b"],
    "notes": case.get("notes", ""),
})}
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
    prompt_profile: str,
) -> dict[str, Any]:
    model_id = model["id"]
    supported_parameters = model.get("supported_parameters") or []
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a precise JSON-only media metadata judge."},
            {"role": "user", "content": build_prompt(case, prompt_profile=prompt_profile)},
        ],
        "max_tokens": 180 if prompt_profile == "baseline" else 120,
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
        "case_id": case["id"],
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
    unique_models = len({row["model"] for row in rows})

    lines = [
        "# OpenRouter Free Model Benchmark",
        "",
        f"Generated: {metadata['generated_at']}",
        f"Models tested: {unique_models}",
        f"Attempts: {len(rows)}",
        f"Cases tested: {metadata['case_count']}",
        f"Reachable: {len(reachable)}",
        f"Valid JSON: {len(valid)}",
        f"Correct: {len(correct)}",
        "",
        "Documented free-model limits: 20 requests/minute; daily limits depend on account state.",
        "",
        "| Case | Model | Reachable | JSON | Correct | Latency ms | Error |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        error = row.get("raw_error") or row.get("error_message") or ""
        if len(error) > 100:
            error = error[:97] + "..."
        lines.append(
            "| {case_id} | {model} | {reachable} | {valid_json} | {correct} | {latency} | {error} |".format(
                case_id=row["case_id"],
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
    parser.add_argument(
        "--case-file",
        type=Path,
        required=True,
        help="JSON fixture file or JSONL corpus file.",
    )
    parser.add_argument(
        "--provider-contract",
        type=Path,
        default=Path("benchmarks/providers/openrouter.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path(".mod/out/benchmarks/openrouter-free"))
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated explicit model ids to benchmark instead of the contract-qualified list.",
    )
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
    parser.add_argument("--prompt-profile", choices=sorted(PROMPT_PROFILES), default="baseline")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("OPENAI_COMPAT_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_COMPAT_API_KEY is required")

    cases = load_cases(args.case_file)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    contract = load_provider_contract(args.provider_contract)
    qualified_model_ids = set(qualified_models_from_contract(contract))

    with httpx.Client(timeout=30) as client:
        models = fetch_free_models(client)
        if args.models:
            requested_models = {model.strip() for model in args.models.split(",") if model.strip()}
            models = [model for model in models if model["id"] in requested_models]
        else:
            models = [model for model in models if model["id"] in qualified_model_ids]
        if not args.all and not args.models:
            models = models[: args.limit]
        key_metadata = fetch_key_metadata(client, api_key)

        rows: list[dict[str, Any]] = []
        incremental_results_path = args.output_dir / "results.incremental.jsonl"
        incremental_results_path.unlink(missing_ok=True)
        total_runs = len(models) * len(cases)
        run_index = 0
        for model in models:
            for case in cases:
                if run_index > 0 and args.delay_seconds > 0:
                    time.sleep(args.delay_seconds)
                run_index += 1
                print(
                    f"[{run_index}/{total_runs}] {model['id']} :: {case['id']}",
                    flush=True,
                )
                row = benchmark_model(
                    client=client,
                    api_key=api_key,
                    model=model,
                    case=case,
                    prompt_profile=args.prompt_profile,
                )
                rows.append(row)
                append_jsonl(incremental_results_path, row)

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "case_file": str(args.case_file),
        "case_count": len(cases),
        "case_ids": [case["id"] for case in cases],
        "key_metadata": key_metadata,
        "model_count": len(models),
        "prompt_profile": args.prompt_profile,
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
