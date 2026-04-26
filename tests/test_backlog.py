from __future__ import annotations

import json
from pathlib import Path

REQUIRED_FIELDS = {
    "id",
    "status",
    "priority",
    "lane",
    "title",
    "summary",
    "depends_on",
    "decision_refs",
    "doc_refs",
    "deliverables",
    "acceptance_criteria",
}


def test_backlog_jsonl_contract() -> None:
    backlog_path = Path("docs/backlog.jsonl")
    decision_ids = {
        json.loads(line)["id"]
        for line in Path("docs/decisions.jsonl").read_text(encoding="utf-8").splitlines()
    }

    ids: set[str] = set()
    dependency_ids: set[str] = set()

    for line_number, line in enumerate(backlog_path.read_text(encoding="utf-8").splitlines(), 1):
        record = json.loads(line)
        missing = REQUIRED_FIELDS - record.keys()
        assert not missing, f"line {line_number} missing fields: {sorted(missing)}"
        assert record["id"].startswith("B-")
        assert record["id"] not in ids, f"duplicate backlog id on line {line_number}"
        assert record["status"] in {"todo", "in_progress", "blocked", "done", "deferred"}
        assert record["priority"] in {"P0", "P1", "P2"}
        assert record["lane"]
        assert record["title"]
        assert record["summary"]
        assert isinstance(record["depends_on"], list)
        assert isinstance(record["decision_refs"], list)
        assert isinstance(record["doc_refs"], list)
        assert isinstance(record["deliverables"], list)
        assert isinstance(record["acceptance_criteria"], list)
        assert record["deliverables"], f"{record['id']} has no deliverables"
        assert record["acceptance_criteria"], f"{record['id']} has no acceptance criteria"

        for decision_ref in record["decision_refs"]:
            assert decision_ref in decision_ids, f"{record['id']} references missing {decision_ref}"

        for doc_ref in record["doc_refs"]:
            assert Path(doc_ref).exists(), f"{record['id']} references missing {doc_ref}"

        ids.add(record["id"])
        dependency_ids.update(record["depends_on"])

    assert dependency_ids <= ids
    assert ids
