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


def chat_judgment_models(contract: dict[str, Any]) -> list[str]:
    return [
        model["id"]
        for model in contract["models"]
        if model.get("task") == "chat_json_judgment"
        and model.get("free_tier") == "free_of_charge"
    ]


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


def response_json_schema(*, prompt_profile: str) -> dict[str, Any]:
    if prompt_profile not in PROMPT_PROFILES:
        raise ValueError(f"Unsupported prompt profile {prompt_profile!r}")

    if prompt_profile == "taxonomy_no_reasoning":
        return {
            "type": "object",
            "properties": {
                "same_entity": {
                    "type": "boolean",
                    "description": "True only when the two records describe the same database entity.",
                },
                "relationship": {
                    "type": "string",
                    "description": "Best relationship label between the two records.",
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
                "confidence": {
                    "type": "number",
                    "description": "Confidence from 0 to 1.",
                },
            },
            "required": ["same_entity", "relationship", "confidence"],
            "propertyOrdering": ["same_entity", "relationship", "confidence"],
        }

    return {
        "type": "object",
        "properties": {
            "same_entity": {
                "type": "boolean",
                "description": "True only when the two records describe the same database entity.",
            },
            "relationship": {
                "type": "string",
                "description": "Best relationship label between the two records.",
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
            "confidence": {
                "type": "number",
                "description": "Confidence from 0 to 1.",
            },
            "reasoning": {
                "type": "string",
                "description": "Short evidence-based explanation.",
            },
        },
        "required": ["same_entity", "relationship", "confidence", "reasoning"],
        "propertyOrdering": ["same_entity", "relationship", "confidence", "reasoning"],
    }


def build_payload(case: dict[str, Any], *, prompt_profile: str) -> dict[str, Any]:
    return {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Return only the JSON object matching the configured schema.\n\n"
                            + build_prompt(case, prompt_profile=prompt_profile)
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 500 if prompt_profile == "baseline" else 220,
            "responseMimeType": "application/json",
            "responseJsonSchema": response_json_schema(prompt_profile=prompt_profile),
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


def extract_text(body: dict[str, Any]) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts") or []
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "".join(texts)


def benchmark_model(
    *,
    client: httpx.Client,
    api_key: str,
    base_url: str,
    model: str,
    case: dict[str, Any],
    prompt_profile: str,
) -> dict[str, Any]:
    payload = build_payload(case, prompt_profile=prompt_profile)

    started = time.monotonic()
    try:
        response = client.post(
            f"{base_url.rstrip('/')}/models/{model}:generateContent",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json=payload,
            timeout=90,
        )
    except httpx.TimeoutException as error:
        latency_ms = round((time.monotonic() - started) * 1000)
        return {
            "provider": "gemini",
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
            "provider": "gemini",
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
        "provider": "gemini",
        "case_id": case["id"],
        "model": model,
        "used_response_format": True,
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
    content = extract_text(body)
    if not content:
        return {
            **base,
            "reachable": False,
            "error_code": "unexpected_response",
            "error_message": "Response did not include text content.",
            "response_keys": sorted(body.keys()),
        }

    parsed = extract_json_object(content)
    scores = score_result(parsed, case["expected"])

    return {
        **base,
        "reachable": True,
        "content": content,
        "parsed": parsed,
        **scores,
    }


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
        default=Path("benchmarks/providers/gemini.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path(".mod/out/benchmarks/gemini-free"))
    parser.add_argument("--models", default="")
    parser.add_argument("--base-url", default=os.environ.get("GEMINI_BASE_URL", GEMINI_BASE_URL))
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=float(os.environ.get("GEMINI_BENCHMARK_DELAY_SECONDS", "4")),
    )
    parser.add_argument("--prompt-profile", choices=sorted(PROMPT_PROFILES), default="baseline")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("GOOGLE_AI_STUDIO_API_KEY")
    if not api_key:
        raise SystemExit("GOOGLE_AI_STUDIO_API_KEY is required")

    cases = load_cases(args.case_file)
    contract = load_json(args.provider_contract)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    models = (
        [model.strip() for model in args.models.split(",") if model.strip()]
        if args.models
        else chat_judgment_models(contract)
    )
    per_run_budget = contract["limits"]["per_run_request_budget"]
    if not args.models and len(models) > per_run_budget:
        raise SystemExit(
            f"Refusing to run {len(models)} models; contract per-run budget is {per_run_budget}"
        )

    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=30) as client:
        total_runs = len(models) * len(cases)
        run_index = 0
        for model in models:
            for case in cases:
                if run_index > 0 and args.delay_seconds > 0:
                    time.sleep(args.delay_seconds)
                run_index += 1
                print(f"[{run_index}/{total_runs}] {model} :: {case['id']}", flush=True)
                rows.append(
                    benchmark_model(
                        client=client,
                        api_key=api_key,
                        base_url=args.base_url,
                        model=model,
                        case=case,
                        prompt_profile=args.prompt_profile,
                    )
                )

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "case_file": str(args.case_file),
        "case_count": len(cases),
        "case_ids": [case["id"] for case in cases],
        "model_count": len(models),
        "provider": "gemini",
        "documented_auth": "x-goog-api-key",
        "documented_free_tier_data_use": "free-tier content used to improve Google products",
        "models": models,
        "prompt_profile": args.prompt_profile,
    }

    write_json(args.output_dir / "metadata.json", metadata)
    write_jsonl(args.output_dir / "results.jsonl", rows)
    write_json(args.output_dir / "results.json", rows)
    print(f"Wrote benchmark results to {args.output_dir}")


if __name__ == "__main__":
    main()
