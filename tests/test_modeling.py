from __future__ import annotations

import pytest
from pydantic import ValidationError

from media_offline_database.modeling import (
    BudgetExhaustedError,
    ConfidenceProfile,
    DeterministicEmbeddingClient,
    JudgmentDecision,
    LlmEvidenceRef,
    LlmInputRef,
    LlmJudgment,
    LlmJudgmentCandidate,
    LlmJudgmentKind,
    LlmJudgmentRecord,
    LlmJudgmentStatus,
    LlmMaterializationRecipe,
    LlmMaterializationTarget,
    LlmRelationshipJudgment,
    ModelTask,
    RelationshipLabel,
    UsageBudget,
    evaluate_llm_materialization,
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


def test_llm_relationship_judgment_schema_is_strict() -> None:
    judgment = LlmRelationshipJudgment(
        relationship=RelationshipLabel.SEQUEL,
        confidence=0.73,
        reasoning="The movie is a direct continuation of the same adaptation line.",
    )

    assert judgment.relationship == RelationshipLabel.SEQUEL
    with pytest.raises(ValidationError):
        LlmRelationshipJudgment.model_validate(
            {
                "relationship": "not_a_real_label",
                "confidence": 0.5,
                "reasoning": "Nope",
            }
        )


def _publishable_input_ref() -> LlmInputRef:
    return LlmInputRef(
        ref_id="entity:one",
        ref_kind="entity",
        source_role="BACKBONE_SOURCE",
        policy_version="publishability-policy-v1",
        publishable=True,
        allowed_uses=["llm_judgment"],
    )


def _publishable_evidence_ref() -> LlmEvidenceRef:
    return LlmEvidenceRef(
        evidence_id="evidence:one",
        evidence_kind="relationship_evidence",
        claim="The source records declare a direct sequel relationship.",
        publishable=True,
    )


def _confidence_profile(*, confidence: float = 0.91) -> ConfidenceProfile:
    return ConfidenceProfile(
        confidence=confidence,
        confidence_tier="high",
        evidence_strength="model_with_publishable_relationship_evidence",
        agreement_status="confirmed",
        extraction_method="model_judgment",
        freshness_status="current",
        recipe_version="relationship-classification-v1",
    )


def _judgment_record(*, confidence: float = 0.91) -> LlmJudgmentRecord:
    return LlmJudgmentRecord(
        judgment_id="judgment:one",
        candidate_id="candidate:one",
        kind=LlmJudgmentKind.RELATIONSHIP_CLASSIFICATION,
        status=LlmJudgmentStatus.APPROVED,
        target_entity_ids=["entity:one", "entity:two"],
        provider="openrouter",
        model="test-model",
        prompt_version="relationship-classification-v1",
        parameters={"temperature": 0},
        input_refs=[_publishable_input_ref()],
        evidence_refs=[_publishable_evidence_ref()],
        output_schema_version="llm-relationship-judgment-output-v1",
        structured_output={"relationship": "sequel_prequel"},
        confidence_profile=_confidence_profile(confidence=confidence),
        quality_flags=["model_inferred"],
    )


def _materialization_recipe() -> LlmMaterializationRecipe:
    return LlmMaterializationRecipe(
        recipe_id="llm_relationship_materialization",
        recipe_version="relationship-materialization-v1",
        target_surface=LlmMaterializationTarget.RELATIONSHIPS,
        allowed_judgment_kinds=[LlmJudgmentKind.RELATIONSHIP_CLASSIFICATION],
        output_schema_version="llm-relationship-judgment-output-v1",
        publishability_policy_version="publishability-policy-v1",
        min_confidence=0.8,
        blocked_quality_flags=["low_confidence"],
        required_parameters={"temperature": 0},
    )


def test_llm_judgment_candidate_schema_requires_publishable_inputs() -> None:
    candidate = LlmJudgmentCandidate(
        candidate_id="candidate:one",
        kind=LlmJudgmentKind.INFERRED_FACET,
        recipe_version="facet-inference-v1",
        target_entity_ids=["anime:golden-time"],
        target_surface=LlmMaterializationTarget.FACETS,
        input_refs=[_publishable_input_ref()],
        evidence_refs=[_publishable_evidence_ref()],
        prompt_context={"title": "Golden Time", "signals": ["college", "romance"]},
        publishability_policy_version="publishability-policy-v1",
        output_schema_version="llm-inferred-facet-output-v1",
        target_eligible=False,
        quality_flags=["needs_materialization_gate"],
    )

    assert candidate.kind == LlmJudgmentKind.INFERRED_FACET
    with pytest.raises(ValidationError):
        LlmJudgmentCandidate.model_validate(
            {
                "candidate_id": "candidate:bad",
                "kind": "inferred_facet",
                "recipe_version": "facet-inference-v1",
                "target_entity_ids": [],
                "input_refs": [],
                "prompt_context": {},
                "publishability_policy_version": "publishability-policy-v1",
                "output_schema_version": "llm-inferred-facet-output-v1",
                "target_eligible": True,
            }
        )


def test_llm_materialization_gate_accepts_valid_relationship_judgment() -> None:
    decision = evaluate_llm_materialization(
        judgment=_judgment_record(),
        recipe=_materialization_recipe(),
    )

    assert decision.eligible is True
    assert decision.reasons == []
    assert decision.target_surface == LlmMaterializationTarget.RELATIONSHIPS


def test_llm_materialization_gate_rejects_invalid_or_unsupported_outputs() -> None:
    low_confidence = evaluate_llm_materialization(
        judgment=_judgment_record(confidence=0.42),
        recipe=_materialization_recipe(),
    )
    blocked_input_judgment = _judgment_record()
    blocked_input_judgment.input_refs[0].publishable = False

    blocked_input = evaluate_llm_materialization(
        judgment=blocked_input_judgment,
        recipe=_materialization_recipe(),
    )

    assert low_confidence.eligible is False
    assert "confidence_below_recipe_minimum" in low_confidence.reasons
    assert blocked_input.eligible is False
    assert "non_publishable_input_ref" in blocked_input.reasons
