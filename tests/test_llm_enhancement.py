from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from media_offline_database.cli import app
from media_offline_database.llm_enhancement import (
    LlmExecutionResult,
    build_relationship_judgment_prompt,
    execute_llm_relationship_candidates,
    load_llm_candidates,
    select_llm_relationship_candidates,
    write_llm_candidate_plan,
)

runner = CliRunner()


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> FakeResponse:
        self.calls.append(dict(kwargs))
        return FakeResponse(self._responses.pop(0))


class FakeChat:
    def __init__(self, responses: list[str]) -> None:
        self.completions = FakeCompletions(responses)


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.chat = FakeChat(responses)


def _write_manifest(
    base_dir: Path,
    *,
    stem: str,
    relationship: str,
    relationship_confidence: float,
) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    entities_path = base_dir / f"{stem}-entities.parquet"
    relationships_path = base_dir / f"{stem}-relationships.parquet"
    manifest_path = base_dir / f"{stem}-manifest.json"

    pl.DataFrame(
        [
            {
                "entity_id": "anime:one",
                "domain": "anime",
                "canonical_source": "https://example.com/anime/one",
                "source_role": "BACKBONE_SOURCE",
                "record_source": "fixture",
                "title": "Made in Abyss",
                "original_title": "メイドインアビス",
                "media_type": "TV",
                "status": "FINISHED",
                "release_year": 2017,
                "episodes": 13,
                "synonyms": [],
                "sources": ["https://example.com/anime/one"],
                "genres": ["Adventure", "Drama"],
                "studios": ["Kinema Citrus"],
                "creators": ["Akihito Tsukushi"],
                "tags": ["Adventure"],
                "field_sources_json": "{}",
            },
            {
                "entity_id": "anime:two",
                "domain": "anime",
                "canonical_source": "https://example.com/anime/two",
                "source_role": "BACKBONE_SOURCE",
                "record_source": "fixture",
                "title": "Made in Abyss Movie 3",
                "original_title": None,
                "media_type": "MOVIE",
                "status": "FINISHED",
                "release_year": 2020,
                "episodes": 1,
                "synonyms": [],
                "sources": ["https://example.com/anime/two"],
                "genres": ["Adventure"],
                "studios": ["Kinema Citrus"],
                "creators": ["Akihito Tsukushi"],
                "tags": ["Adventure"],
                "field_sources_json": "{}",
            },
        ]
    ).write_parquet(entities_path)

    pl.DataFrame(
        [
            {
                "source_entity_id": "anime:one",
                "target_entity_id": "anime:two",
                "relationship": relationship,
                "target_url": "https://example.com/anime/two",
                "supporting_urls": ["https://example.com/anime/two"],
                "supporting_source_count": 1,
                "supporting_provider_count": 1,
                "relationship_confidence": relationship_confidence,
            }
        ]
    ).write_parquet(relationships_path)

    manifest_path.write_text(
        json.dumps(
            {
                "artifact": "bootstrap-corpus",
                "files": [
                    {"path": entities_path.name, "kind": "entities"},
                    {"path": relationships_path.name, "kind": "relationships"},
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_select_llm_relationship_candidates_marks_changes_against_previous(tmp_path: Path) -> None:
    previous_manifest = _write_manifest(
        tmp_path / "previous",
        stem="previous",
        relationship="related_anime",
        relationship_confidence=0.35,
    )
    current_manifest = _write_manifest(
        tmp_path / "current",
        stem="current",
        relationship="sequel_prequel",
        relationship_confidence=0.61,
    )

    candidates = select_llm_relationship_candidates(
        manifest_path=current_manifest,
        previous_manifest_path=previous_manifest,
        confidence_threshold=0.85,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.relationship == "sequel_prequel"
    assert candidate.previous_relationship == "related_anime"
    assert candidate.changed_since_previous is True
    assert candidate.source_title == "Made in Abyss"
    assert candidate.target_title == "Made in Abyss Movie 3"
    assert candidate.cache_key.startswith("llm_judgment:")


def test_write_llm_candidate_plan_updates_manifest(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path / "current",
        stem="current",
        relationship="related_anime",
        relationship_confidence=0.42,
    )
    candidates = select_llm_relationship_candidates(manifest_path=manifest_path)

    plan = write_llm_candidate_plan(
        manifest_path=manifest_path,
        candidates=candidates,
    )

    assert plan.candidate_count == 1
    assert plan.candidates_path.exists()
    assert plan.summary_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    file_kinds = {entry["kind"] for entry in manifest["files"]}
    assert "llm_judgment_candidates" in file_kinds
    assert "llm_judgment_summary" in file_kinds


def test_execute_llm_relationship_candidates_writes_decisions(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path / "current",
        stem="current",
        relationship="related_anime",
        relationship_confidence=0.42,
    )
    candidates = select_llm_relationship_candidates(manifest_path=manifest_path)
    plan = write_llm_candidate_plan(
        manifest_path=manifest_path,
        candidates=candidates,
    )
    fake_client = FakeClient(
        [
            json.dumps(
                {
                    "relationship": "sequel_prequel",
                    "confidence": 0.81,
                    "reasoning": "The movie is presented as the next installment in the same line.",
                }
            )
        ]
    )

    result = execute_llm_relationship_candidates(
        candidates_path=plan.candidates_path,
        manifest_path=manifest_path,
        api_key="test",
        base_url="https://example.invalid/v1",
        client=fake_client,  # type: ignore[arg-type]
    )

    assert result.candidate_count == 1
    assert result.executed_count == 1
    decisions = [
        json.loads(line)
        for line in result.decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert decisions[0]["status"] == "ok"
    assert decisions[0]["judgment"]["relationship"] == "sequel_prequel"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    file_kinds = {entry["kind"] for entry in manifest["files"]}
    assert "llm_judgment_decisions" in file_kinds
    assert "llm_judgment_execution_summary" in file_kinds


def test_build_relationship_judgment_prompt_mentions_current_relationship(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path / "current",
        stem="current",
        relationship="related_anime",
        relationship_confidence=0.42,
    )
    candidate = select_llm_relationship_candidates(manifest_path=manifest_path)[0]

    prompt = build_relationship_judgment_prompt(candidate)

    assert "current_relationship" in prompt
    assert "related_anime" in prompt
    assert "Made in Abyss" in prompt


def test_llm_prepare_candidates_cli_writes_sidecars(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path / "current",
        stem="current",
        relationship="related_anime",
        relationship_confidence=0.42,
    )

    result = runner.invoke(
        app,
        [
            "llm-prepare-candidates",
            str(manifest_path),
            "--confidence-threshold",
            "0.85",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["candidate_count"] == 1
    assert (manifest_path.parent / "llm-judgment-candidates.jsonl").exists()


def test_llm_execute_candidates_cli_runs_with_settings_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _write_manifest(
        tmp_path / "current",
        stem="current",
        relationship="related_anime",
        relationship_confidence=0.42,
    )
    candidates = select_llm_relationship_candidates(manifest_path=manifest_path)
    plan = write_llm_candidate_plan(manifest_path=manifest_path, candidates=candidates)

    expected_result = LlmExecutionResult(
        manifest_path=manifest_path,
        candidate_count=1,
        executed_count=1,
        decisions_path=manifest_path.parent / "llm-judgment-decisions.jsonl",
        summary_path=manifest_path.parent / "llm-judgment-execution-summary.json",
    )

    def fake_execute(
        *,
        candidates_path: Path,
        manifest_path: Path,
        api_key: str,
        base_url: str,
        provider: str,
        model: str,
    ) -> LlmExecutionResult:
        assert candidates_path == plan.candidates_path
        assert manifest_path == expected_result.manifest_path
        assert api_key == "test-key"
        assert base_url == "https://example.invalid/v1"
        assert provider == "openrouter"
        assert model == "test-model"
        return expected_result

    monkeypatch.setattr(
        "media_offline_database.cli.execute_llm_relationship_candidates",
        fake_execute,
    )

    result = runner.invoke(
        app,
        [
            "llm-execute-candidates",
            str(plan.candidates_path),
            str(manifest_path),
        ],
        env={
            "OPENAI_COMPAT_API_KEY": "test-key",
            "OPENAI_COMPAT_BASE_URL": "https://example.invalid/v1",
            "OPENAI_COMPAT_DEFAULT_MODEL": "test-model",
        },
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["executed_count"] == 1
    assert payload["candidate_count"] == 1


def test_load_llm_candidates_round_trips_plan_file(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path / "current",
        stem="current",
        relationship="related_anime",
        relationship_confidence=0.42,
    )
    candidates = select_llm_relationship_candidates(manifest_path=manifest_path)
    plan = write_llm_candidate_plan(manifest_path=manifest_path, candidates=candidates)

    loaded = load_llm_candidates(plan.candidates_path)

    assert len(loaded) == 1
    assert loaded[0].source_entity_id == "anime:one"
