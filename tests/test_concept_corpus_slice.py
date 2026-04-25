from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from media_offline_database.bootstrap import load_bootstrap_entities
from media_offline_database.cli import app
from media_offline_database.corpus_concept_search import search_corpus_by_concept

CONCEPT_SEED_PATH = Path("corpus/bootstrap-concept-romance-college-v1.jsonl")
runner = CliRunner()


def test_concept_seed_keeps_college_romance_anchors_queryable() -> None:
    entities = load_bootstrap_entities(CONCEPT_SEED_PATH)

    preview = search_corpus_by_concept(
        entities,
        query="romance anime where characters are in university/college",
        limit=5,
    )

    assert [entity.title for entity in entities] == [
        "Golden Time",
        "Honey and Clover",
        "Nodame Cantabile",
    ]
    assert [match.title for match in preview.matches] == [
        "Golden Time",
        "Honey and Clover",
        "Nodame Cantabile",
    ]
    assert preview.matches[0].matched_genres == ["Romance"]
    assert preview.matches[0].matched_tags == ["College", "Primarily Adult Cast"]


def test_corpus_concept_preview_cli_finds_golden_time_from_checked_in_seed() -> None:
    result = runner.invoke(
        app,
        [
            "corpus-concept-preview",
            "romance anime where characters are in university/college",
            "--input-path",
            str(CONCEPT_SEED_PATH),
            "--limit",
            "5",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["filters"]["original_query"] == (
        "romance anime where characters are in university/college"
    )
    assert payload["filters"]["genres"] == ["Romance"]
    assert payload["filters"]["tags"] == ["College", "Primarily Adult Cast"]
    assert [match["title"] for match in payload["matches"]] == [
        "Golden Time",
        "Honey and Clover",
        "Nodame Cantabile",
    ]
