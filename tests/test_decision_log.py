from __future__ import annotations

import json
from pathlib import Path


def test_decision_log_is_valid_jsonl() -> None:
    decision_log = Path("docs/decisions.jsonl")

    ids: set[str] = set()
    for line_number, line in enumerate(decision_log.read_text(encoding="utf-8").splitlines(), 1):
        record = json.loads(line)
        assert record["id"] not in ids, f"duplicate decision id on line {line_number}"
        assert record["status"] in {"accepted", "superseded", "rejected"}
        assert record["date"]
        assert record["title"]
        assert record["decision"]
        ids.add(record["id"])
