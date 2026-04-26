from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

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
