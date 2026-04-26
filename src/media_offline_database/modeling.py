from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelTask(StrEnum):
    """Model task families that participate in cache keys and budgets."""

    EMBEDDING = "embedding"
    LLM_JUDGMENT = "llm_judgment"


class JudgmentDecision(StrEnum):
    """Allowed structured LLM judgment decisions."""

    MERGE = "merge"
    NO_MERGE = "no_merge"
    UNCERTAIN = "uncertain"


class RelationshipLabel(StrEnum):
    """Allowed cross-domain relationship labels for entity-pair judgments."""

    SAME_ENTITY = "same_entity"
    SEQUEL = "sequel"
    PREQUEL = "prequel"
    CONTINUATION = "continuation"
    SPINOFF = "spinoff"
    SIDE_STORY = "side_story"
    SPECIAL = "special"
    RECAP = "recap"
    COMPILATION = "compilation"
    MOVIE_TIE_IN = "movie_tie_in"
    REMAKE = "remake"
    REBOOT = "reboot"
    RETELLING = "retelling"
    ALTERNATE_ADAPTATION = "alternate_adaptation"
    ADAPTATION_OF = "adaptation_of"
    ADAPTED_BY = "adapted_by"
    SOURCE_MATERIAL = "source_material"
    SAME_FRANCHISE = "same_franchise"
    SHARED_UNIVERSE = "shared_universe"
    SIMILAR_TO = "similar_to"
    UNRELATED = "unrelated"
    UNCERTAIN = "uncertain"


class LlmJudgmentKind(StrEnum):
    """LLM-assisted judgment families stored before any materialization."""

    IDENTITY = "identity"
    RELATIONSHIP_CLASSIFICATION = "relationship_classification"
    TAG_FACET_NORMALIZATION = "tag_facet_normalization"
    INFERRED_FACET = "inferred_facet"
    CONFLICT_FLAG = "conflict_flag"
    QA = "qa"


class LlmJudgmentStatus(StrEnum):
    """Lifecycle status for a structured judgment row."""

    APPROVED = "approved"
    REJECTED = "rejected"
    INVALID = "invalid"
    NEEDS_REVIEW = "needs_review"


class LlmMaterializationTarget(StrEnum):
    """Queryable surfaces that can receive approved judgment outputs."""

    RELATIONSHIPS = "relationships"
    FACETS = "facets"
    PROFILE_FIELDS = "profile_fields"
    QUALITY_FLAGS = "quality_flags"
    CONFIDENCE_PROFILES = "confidence_profiles"


class LlmInputRef(BaseModel):
    """Reference to a publishability-reviewed input used in a model call."""

    model_config = ConfigDict(extra="forbid")

    ref_id: str = Field(min_length=1)
    ref_kind: str = Field(min_length=1)
    source_role: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    publishable: bool
    allowed_uses: list[str] = Field(default_factory=list)


class LlmEvidenceRef(BaseModel):
    """Reference to source, deterministic, or judgment evidence."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    evidence_kind: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    publishable: bool


def _empty_llm_evidence_refs() -> list[LlmEvidenceRef]:
    return []


class ConfidenceProfile(BaseModel):
    """Dimensional, recipe-specific confidence profile."""

    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(ge=0.0, le=1.0)
    confidence_tier: Literal["high", "medium", "low", "unknown"]
    evidence_strength: str = Field(min_length=1)
    agreement_status: str = Field(min_length=1)
    extraction_method: str = Field(min_length=1)
    freshness_status: str = Field(min_length=1)
    recipe_version: str = Field(min_length=1)


class LlmJudgmentCandidate(BaseModel):
    """Versioned candidate row queued for model, human, or complex review."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    kind: LlmJudgmentKind
    recipe_version: str = Field(min_length=1)
    target_entity_ids: list[str] = Field(min_length=1)
    target_surface: LlmMaterializationTarget | None = None
    input_refs: list[LlmInputRef] = Field(min_length=1)
    evidence_refs: list[LlmEvidenceRef] = Field(default_factory=_empty_llm_evidence_refs)
    prompt_context: dict[str, Any]
    publishability_policy_version: str = Field(min_length=1)
    output_schema_version: str = Field(min_length=1)
    target_eligible: bool
    quality_flags: list[str] = Field(default_factory=list)


class LlmJudgmentRecord(BaseModel):
    """Auditable structured LLM judgment artifact."""

    model_config = ConfigDict(extra="forbid")

    judgment_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    kind: LlmJudgmentKind
    status: LlmJudgmentStatus
    target_entity_ids: list[str] = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    parameters: dict[str, Any]
    input_refs: list[LlmInputRef] = Field(min_length=1)
    evidence_refs: list[LlmEvidenceRef] = Field(default_factory=_empty_llm_evidence_refs)
    output_schema_version: str = Field(min_length=1)
    structured_output: dict[str, Any]
    confidence_profile: ConfidenceProfile
    quality_flags: list[str] = Field(default_factory=list)
    raw_response_ref: str | None = None


class LlmMaterializationRecipe(BaseModel):
    """Versioned gate that permits specific judgment outputs onto queryable surfaces."""

    model_config = ConfigDict(extra="forbid")

    recipe_id: str = Field(min_length=1)
    recipe_version: str = Field(min_length=1)
    target_surface: LlmMaterializationTarget
    allowed_judgment_kinds: list[LlmJudgmentKind] = Field(min_length=1)
    output_schema_version: str = Field(min_length=1)
    publishability_policy_version: str = Field(min_length=1)
    min_confidence: float = Field(ge=0.0, le=1.0)
    required_input_use: str = Field(default="llm_judgment")
    min_publishable_evidence_refs: int = Field(default=1, ge=0)
    blocked_quality_flags: list[str] = Field(default_factory=list)
    required_provider: str | None = None
    required_model: str | None = None
    required_prompt_version: str | None = None
    required_parameters: dict[str, Any] = Field(default_factory=dict)


class LlmMaterializationDecision(BaseModel):
    """Gate result explaining whether a judgment can materialize."""

    model_config = ConfigDict(extra="forbid")

    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    judgment_id: str
    recipe_id: str
    recipe_version: str
    target_surface: LlmMaterializationTarget


def evaluate_llm_materialization(
    *,
    judgment: LlmJudgmentRecord,
    recipe: LlmMaterializationRecipe,
) -> LlmMaterializationDecision:
    """Validate whether a judgment may produce a queryable derived row."""

    reasons: list[str] = []
    if judgment.status != LlmJudgmentStatus.APPROVED:
        reasons.append("judgment_status_not_approved")
    if judgment.kind not in recipe.allowed_judgment_kinds:
        reasons.append("judgment_kind_not_allowed")
    if judgment.output_schema_version != recipe.output_schema_version:
        reasons.append("output_schema_version_mismatch")
    if judgment.confidence_profile.confidence < recipe.min_confidence:
        reasons.append("confidence_below_recipe_minimum")
    if recipe.required_provider is not None and judgment.provider != recipe.required_provider:
        reasons.append("provider_mismatch")
    if recipe.required_model is not None and judgment.model != recipe.required_model:
        reasons.append("model_mismatch")
    if (
        recipe.required_prompt_version is not None
        and judgment.prompt_version != recipe.required_prompt_version
    ):
        reasons.append("prompt_version_mismatch")
    for key, expected_value in recipe.required_parameters.items():
        if judgment.parameters.get(key) != expected_value:
            reasons.append(f"parameter_mismatch:{key}")

    blocked_flags = set(recipe.blocked_quality_flags) & set(judgment.quality_flags)
    if blocked_flags:
        reasons.extend(f"blocked_quality_flag:{flag}" for flag in sorted(blocked_flags))

    if not all(input_ref.publishable for input_ref in judgment.input_refs):
        reasons.append("non_publishable_input_ref")
    if not all(
        recipe.required_input_use in input_ref.allowed_uses for input_ref in judgment.input_refs
    ):
        reasons.append("input_use_not_allowed")

    publishable_evidence_count = sum(
        1 for evidence_ref in judgment.evidence_refs if evidence_ref.publishable
    )
    if publishable_evidence_count < recipe.min_publishable_evidence_refs:
        reasons.append("insufficient_publishable_evidence_refs")

    return LlmMaterializationDecision(
        eligible=not reasons,
        reasons=reasons,
        judgment_id=judgment.judgment_id,
        recipe_id=recipe.recipe_id,
        recipe_version=recipe.recipe_version,
        target_surface=recipe.target_surface,
    )


class LlmJudgment(BaseModel):
    """Strict structured output shape for model-assisted judgments."""

    model_config = ConfigDict(extra="forbid")

    decision: JudgmentDecision
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1)


class LlmRelationshipJudgment(BaseModel):
    """Strict structured output for relationship classification judgments."""

    model_config = ConfigDict(extra="forbid")

    relationship: RelationshipLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1)


class BudgetExhaustedError(RuntimeError):
    """Raised when a model/provider budget would be exceeded."""


@dataclass(frozen=True)
class UsageBudget:
    """Immutable budget ledger for deterministic tests and provider gates."""

    limit: int
    used: int = 0

    def reserve(self, amount: int) -> UsageBudget:
        if amount < 0:
            raise ValueError("amount must be non-negative")

        next_used = self.used + amount
        if next_used > self.limit:
            raise BudgetExhaustedError("budget exhausted")

        return UsageBudget(limit=self.limit, used=next_used)


def stable_json(value: Any) -> str:
    """Serialize model inputs in a deterministic, hashable form."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def model_cache_key(
    *,
    task: ModelTask,
    provider: str,
    model: str,
    recipe_version: str,
    normalized_input: Any,
) -> str:
    """Build a reproducible cache key for model calls."""

    payload = {
        "model": model,
        "normalized_input": normalized_input,
        "provider": provider,
        "recipe_version": recipe_version,
        "task": task.value,
    }
    digest = hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()
    return f"{task.value}:{digest}"


@dataclass(frozen=True)
class DeterministicEmbeddingClient:
    """Keyless embedding test double with stable vectors."""

    dimensions: int = 8

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []

        for index in range(self.dimensions):
            byte = digest[index % len(digest)]
            values.append(round((byte / 255.0) * 2.0 - 1.0, 6))

        return values
