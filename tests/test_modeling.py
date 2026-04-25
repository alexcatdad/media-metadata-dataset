from __future__ import annotations

import pytest
from pydantic import ValidationError

from media_offline_database.modeling import (
    BudgetExhaustedError,
    DeterministicEmbeddingClient,
    JudgmentDecision,
    LlmJudgment,
    ModelTask,
    UsageBudget,
    model_cache_key,
)


def test_model_cache_key_is_stable_and_recipe_sensitive() -> None:
    first_key = model_cache_key(
        task=ModelTask.EMBEDDING,
        provider="cloudflare_workers_ai",
        model="@cf/baai/bge-m3",
        recipe_version="v1",
        normalized_input={"title": "The Expanse", "domain": "tv"},
    )
    second_key = model_cache_key(
        task=ModelTask.EMBEDDING,
        provider="cloudflare_workers_ai",
        model="@cf/baai/bge-m3",
        recipe_version="v1",
        normalized_input={"domain": "tv", "title": "The Expanse"},
    )
    changed_recipe_key = model_cache_key(
        task=ModelTask.EMBEDDING,
        provider="cloudflare_workers_ai",
        model="@cf/baai/bge-m3",
        recipe_version="v2",
        normalized_input={"title": "The Expanse", "domain": "tv"},
    )

    assert first_key == second_key
    assert first_key != changed_recipe_key


def test_usage_budget_stops_before_exceeding_limit() -> None:
    budget = UsageBudget(limit=10).reserve(4).reserve(6)

    assert budget.used == 10
    with pytest.raises(BudgetExhaustedError):
        budget.reserve(1)


def test_deterministic_embedding_client_returns_stable_vectors() -> None:
    client = DeterministicEmbeddingClient(dimensions=4)

    first_vector = client.embed(["The Expanse"])[0]
    second_vector = client.embed(["The Expanse"])[0]
    other_vector = client.embed(["Cowboy Bebop"])[0]

    assert first_vector == second_vector
    assert first_vector != other_vector
    assert len(first_vector) == 4


def test_llm_judgment_schema_is_strict() -> None:
    judgment = LlmJudgment(
        decision=JudgmentDecision.UNCERTAIN,
        confidence=0.42,
        reasoning="Insufficient relationship evidence.",
    )

    assert judgment.decision == JudgmentDecision.UNCERTAIN
    with pytest.raises(ValidationError):
        LlmJudgment.model_validate(
            {
                "decision": JudgmentDecision.MERGE,
                "confidence": 1.2,
                "reasoning": "Too confident.",
                "extra_field": "not allowed",
            }
        )
