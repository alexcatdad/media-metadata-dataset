from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path, *, provider: str) -> list[dict[str, Any]]:
    rows = load_json(path)
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON array")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append({"provider": provider, **row})
    return normalized


def is_correct(row: dict[str, Any]) -> bool:
    return bool(row.get("correct_same_entity") and row.get("correct_relationship"))


def rank_key(row: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        0 if is_correct(row) else 1,
        0 if row.get("valid_json") else 1,
        0 if row.get("reachable") else 1,
        int(row.get("latency_ms") or 999_999_999),
    )


def write_markdown(path: Path, *, rows: list[dict[str, Any]]) -> None:
    ranked = sorted(rows, key=rank_key)
    correct = [row for row in ranked if is_correct(row)]
    reachable = [row for row in ranked if row.get("reachable")]
    valid = [row for row in reachable if row.get("valid_json")]

    lines = [
        "# LLM Judgment Benchmark Rerank",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Models compared: {len(ranked)}",
        f"Reachable: {len(reachable)}",
        f"Valid JSON: {len(valid)}",
        f"Correct: {len(correct)}",
        "",
        "Ranking sorts by correct result, valid JSON, reachability, then latency.",
        "",
        "| Rank | Provider | Model | Reachable | JSON | Correct | Latency ms | Notes |",
        "|---:|---|---|---:|---:|---:|---:|---|",
    ]

    for index, row in enumerate(ranked, start=1):
        notes = row.get("raw_error") or row.get("error_message") or ""
        if isinstance(notes, dict):
            notes = json.dumps(notes, ensure_ascii=False, sort_keys=True)
        if len(str(notes)) > 100:
            notes = str(notes)[:97] + "..."
        lines.append(
            "| {rank} | {provider} | {model} | {reachable} | {valid_json} | {correct} | {latency} | {notes} |".format(
                rank=index,
                provider=row.get("provider", ""),
                model=row["model"],
                reachable="yes" if row.get("reachable") else "no",
                valid_json="yes" if row.get("valid_json") else "no",
                correct="yes" if is_correct(row) else "no",
                latency=row.get("latency_ms", ""),
                notes=str(notes).replace("|", "\\|").replace("\n", " "),
            )
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--openrouter-results",
        type=Path,
        default=Path(".mod/out/benchmarks/openrouter-free/results.json"),
    )
    parser.add_argument(
        "--z-ai-results",
        type=Path,
        default=Path(".mod/out/benchmarks/z-ai-glm/results.json"),
    )
    parser.add_argument(
        "--gemini-results",
        type=Path,
        default=Path(".mod/out/benchmarks/gemini-free/results.json"),
    )
    parser.add_argument(
        "--extra-results",
        action="append",
        default=[],
        help="Additional provider:path pair to include, for example gemini:.mod/out/x/results.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/benchmarks/llm-judgment-rerank-2026-04-25.md"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = [
        *load_rows(args.openrouter_results, provider="openrouter"),
        *load_rows(args.z_ai_results, provider="z.ai"),
    ]
    if args.gemini_results.exists():
        rows.extend(load_rows(args.gemini_results, provider="gemini"))
    for item in args.extra_results:
        provider, path = item.split(":", maxsplit=1)
        rows.extend(load_rows(Path(path), provider=provider))
    write_markdown(args.output, rows=rows)
    print(f"Wrote rerank report to {args.output}")


if __name__ == "__main__":
    main()
