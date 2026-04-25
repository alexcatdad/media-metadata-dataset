from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

OPENAI_COMPAT_BASE_URL = "http://127.0.0.1:1234/v1"
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
        return {
            "id": raw_case.get("id", default_id),
            "task": raw_case.get("task", "chat_json_judgment"),
            "source": raw_case.get("source", "unknown"),
            "record_a": raw_case["input"]["record_a"],
            "record_b": raw_case["input"]["record_b"],
            "expected": raw_case["expected"],
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
        relationship = case["expected"]["relationship"]
        if relationship not in RELATIONSHIP_LABELS:
            raise ValueError(f"Invalid relationship label {relationship!r} in {case['id']}")
    return cases


def build_prompt(case: dict[str, Any]) -> str:
    return f"""
You judge anime identity and relationship records.

Task:
Return whether record_a and record_b are the same anime database entity or separate entities,
and if separate, choose the best relationship label.

Use only the provided source records. Do not invent facts.

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


def response_json_schema() -> dict[str, Any]:
    return {
        "name": "anime_judgment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "same_entity": {"type": "boolean"},
                "relationship": {
                    "type": "string",
                    "enum": [
                        "same_entity",
                        "movie_related",
                        "special_related",
                        "sequel_prequel",
                        "remake_reboot",
                        "unrelated",
                        "uncertain",
                    ],
                },
                "confidence": {"type": "number"},
            },
            "required": ["same_entity", "relationship", "confidence"],
            "additionalProperties": False,
        },
    }


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
    base_url: str,
    model: str,
    case: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise JSON-only media metadata judge."},
            {"role": "user", "content": build_prompt(case)},
        ],
        "temperature": 0,
        "max_tokens": 300,
        "response_format": {
            "type": "json_schema",
            "json_schema": response_json_schema(),
        },
    }

    started = time.monotonic()
    try:
        response = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=300,
        )
    except httpx.TimeoutException as error:
        latency_ms = round((time.monotonic() - started) * 1000)
        return {
            "provider": "openai_compat_local",
            "case_id": case["id"],
            "model": model,
            "used_response_format": True,
            "latency_ms": latency_ms,
            "http_status": None,
            "reachable": False,
            "error_code": "timeout",
            "error_message": str(error),
            "error_status": "TIMEOUT",
        }
    except httpx.HTTPError as error:
        latency_ms = round((time.monotonic() - started) * 1000)
        return {
            "provider": "openai_compat_local",
            "case_id": case["id"],
            "model": model,
            "used_response_format": True,
            "latency_ms": latency_ms,
            "http_status": None,
            "reachable": False,
            "error_code": "http_error",
            "error_message": str(error),
            "error_status": "HTTP_ERROR",
        }

    latency_ms = round((time.monotonic() - started) * 1000)
    base = {
        "provider": "openai_compat_local",
        "case_id": case["id"],
        "model": model,
        "used_response_format": True,
        "latency_ms": latency_ms,
        "http_status": response.status_code,
    }

    if response.status_code >= 400:
        try:
            error = response.json().get("error")
        except json.JSONDecodeError:
            error = response.text[:500]
        return {
            **base,
            "reachable": False,
            "error_code": response.status_code,
            "error_message": error,
        }

    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        return {
            **base,
            "reachable": False,
            "error_code": "unexpected_response",
            "error_message": "Response did not include choices.",
            "response_keys": sorted(body.keys()),
        }

    content = choices[0].get("message", {}).get("content") or ""
    parsed = extract_json_object(content)
    scores = score_result(parsed, case["expected"])

    return {
        **base,
        "reachable": True,
        "content": content,
        "parsed": parsed,
        "finish_reason": choices[0].get("finish_reason"),
        "usage": body.get("usage"),
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
        "# OpenAI-Compatible Local Benchmark",
        "",
        f"Generated: {metadata['generated_at']}",
        f"Models tested: {metadata['model_count']}",
        f"Attempts: {len(rows)}",
        f"Cases tested: {metadata['case_count']}",
        f"Reachable: {len(reachable)}",
        f"Valid JSON: {len(valid)}",
        f"Correct: {len(correct)}",
        "",
        "| Case | Model | Reachable | JSON | Correct | Latency ms | Error |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        error = row.get("error_message") or ""
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
    parser.add_argument("--output-dir", type=Path, default=Path(".mod/out/benchmarks/openai-compat-local"))
    parser.add_argument("--models", required=True, help="Comma-separated model ids.")
    parser.add_argument("--base-url", default=OPENAI_COMPAT_BASE_URL)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_cases(args.case_file)
    models = [model.strip() for model in args.models.split(",") if model.strip()]
    if not models:
        raise SystemExit("At least one model is required")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    incremental_results_path = args.output_dir / "results.incremental.jsonl"
    incremental_results_path.unlink(missing_ok=True)

    with httpx.Client(timeout=30) as client:
        total_runs = len(models) * len(cases)
        run_index = 0
        for model in models:
            for case in cases:
                if run_index > 0 and args.delay_seconds > 0:
                    time.sleep(args.delay_seconds)
                run_index += 1
                print(f"[{run_index}/{total_runs}] {model} :: {case['id']}", flush=True)
                row = benchmark_model(
                    client=client,
                    base_url=args.base_url,
                    model=model,
                    case=case,
                )
                rows.append(row)
                append_jsonl(incremental_results_path, row)

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "case_file": str(args.case_file),
        "case_count": len(cases),
        "case_ids": [case["id"] for case in cases],
        "model_count": len(models),
        "provider": "openai_compat_local",
        "base_url": args.base_url,
        "models": models,
    }

    write_json(args.output_dir / "metadata.json", metadata)
    write_jsonl(args.output_dir / "results.jsonl", rows)
    write_json(args.output_dir / "results.json", rows)
    write_markdown_summary(args.output_dir / "summary.md", rows=rows, metadata=metadata)
    print(f"Wrote benchmark results to {args.output_dir}")


if __name__ == "__main__":
    main()
