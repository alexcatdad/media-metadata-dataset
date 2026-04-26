from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import polars as pl
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from media_offline_database.modeling import (
    ConfidenceProfile,
    LlmEvidenceRef,
    LlmInputRef,
    LlmJudgmentKind,
    LlmJudgmentRecord,
    LlmJudgmentStatus,
    LlmMaterializationRecipe,
    LlmMaterializationTarget,
    LlmRelationshipJudgment,
    ModelTask,
    evaluate_llm_materialization,
    model_cache_key,
    stable_json,
)
from media_offline_database.publishability import (
    PublishableUse,
    SourceFieldReference,
    validate_manifest_publishability,
    validate_text_inputs,
)

DEFAULT_LLM_PROVIDER = "openrouter"
DEFAULT_LLM_MODEL = "inclusionai/ling-2.6-flash:free"
DEFAULT_LLM_RECIPE_VERSION = "relationship-classification-v1"
DEFAULT_LLM_OUTPUT_SCHEMA_VERSION = "llm-relationship-judgment-output-v1"
DEFAULT_LLM_MATERIALIZATION_RECIPE_VERSION = "relationship-materialization-v1"
LLM_PRIVATE_EXPERIMENT_POLICY_VERSION = "llm-private-experiment-v1"


def _private_llm_sidecar_metadata() -> dict[str, str | bool]:
    return {
        "public": False,
        "publishability_status": "private_experiment_only",
        "publishability_policy_version": LLM_PRIVATE_EXPERIMENT_POLICY_VERSION,
        "compatibility_tier": "experimental",
    }


class LlmRelationshipCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_entity_id: str
    target_entity_id: str
    relationship: str
    source_domain: str
    target_domain: str
    source_title: str
    target_title: str
    source_original_title: str | None = None
    target_original_title: str | None = None
    source_media_type: str
    target_media_type: str
    source_release_year: int
    target_release_year: int
    source_genres: list[str] = Field(default_factory=list)
    target_genres: list[str] = Field(default_factory=list)
    source_studios: list[str] = Field(default_factory=list)
    target_studios: list[str] = Field(default_factory=list)
    source_creators: list[str] = Field(default_factory=list)
    target_creators: list[str] = Field(default_factory=list)
    relationship_confidence_score: float
    supporting_source_count: int
    supporting_provider_count: int
    supporting_urls: list[str] = Field(default_factory=list)
    previous_relationship: str | None = None
    previous_relationship_confidence_score: float | None = None
    changed_since_previous: bool = False
    input_fingerprint: str
    cache_key: str


class LlmCandidatePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_path: Path
    candidate_count: int
    candidates_path: Path
    summary_path: Path


class LlmDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_entity_id: str
    target_entity_id: str
    provider: str
    model: str
    recipe_version: str
    input_fingerprint: str
    cache_key: str
    raw_response: str | None = None
    judgment: LlmRelationshipJudgment | None = None
    status: Literal["ok", "parse_error", "api_error"]
    error_type: str | None = None
    error_message: str | None = None


class LlmExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_path: Path
    candidate_count: int
    executed_count: int
    decisions_path: Path
    summary_path: Path


class LlmApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_path: Path
    decisions_path: Path
    relationship_count: int
    eligible_decision_count: int
    applied_count: int
    unchanged_count: int
    materialized_path: Path
    summary_path: Path


class OpenAiClientLike(Protocol):
    chat: Any


def _row_allows_private_llm_judgment_input(row: dict[str, Any]) -> bool:
    return str(row.get("source_role") or "") == "BACKBONE_SOURCE"


def _manifest_files(manifest_path: Path) -> dict[str, Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest_publishability(manifest)
    return {file["kind"]: manifest_path.parent / file["path"] for file in manifest["files"]}


def _load_entity_rows(manifest_path: Path) -> dict[str, dict[str, Any]]:
    files = _manifest_files(manifest_path)
    frame = pl.read_parquet(files["entities"])
    rows: dict[str, dict[str, Any]] = {}
    for row in frame.iter_rows(named=True):
        rows[str(row["entity_id"])] = row
    return rows


def _load_relationship_rows(manifest_path: Path) -> list[dict[str, Any]]:
    files = _manifest_files(manifest_path)
    frame = pl.read_parquet(files["relationships"])
    return list(frame.iter_rows(named=True))


def _previous_index(manifest_path: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    if manifest_path is None:
        return {}
    return {
        (str(row["source_entity_id"]), str(row["target_entity_id"])): row
        for row in _load_relationship_rows(manifest_path)
    }


def _normalized_candidate_input(
    *,
    source_row: dict[str, Any],
    target_row: dict[str, Any],
    relationship_row: dict[str, Any],
    previous_row: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "source_entity_id": source_row["entity_id"],
        "target_entity_id": target_row["entity_id"],
        "source": {
            "domain": source_row["domain"],
            "title": source_row["title"],
            "original_title": source_row["original_title"],
            "media_type": source_row["media_type"],
            "release_year": source_row["release_year"],
            "genres": list(source_row.get("genres") or []),
            "studios": list(source_row.get("studios") or []),
            "creators": list(source_row.get("creators") or []),
        },
        "target": {
            "domain": target_row["domain"],
            "title": target_row["title"],
            "original_title": target_row["original_title"],
            "media_type": target_row["media_type"],
            "release_year": target_row["release_year"],
            "genres": list(target_row.get("genres") or []),
            "studios": list(target_row.get("studios") or []),
            "creators": list(target_row.get("creators") or []),
        },
        "relationship": {
            "current": relationship_row["relationship_type"],
            "confidence_score": relationship_row["relationship_confidence_score"],
            "supporting_source_count": relationship_row["supporting_source_count"],
            "supporting_provider_count": relationship_row["supporting_provider_count"],
            "supporting_urls": list(relationship_row.get("supporting_urls") or []),
            "previous": {
                "relationship": None if previous_row is None else previous_row["relationship_type"],
                "confidence_score": (
                    None
                    if previous_row is None
                    else previous_row["relationship_confidence_score"]
                ),
            },
        },
    }


def select_llm_relationship_candidates(
    *,
    manifest_path: Path,
    previous_manifest_path: Path | None = None,
    provider: str = DEFAULT_LLM_PROVIDER,
    model: str = DEFAULT_LLM_MODEL,
    recipe_version: str = DEFAULT_LLM_RECIPE_VERSION,
    confidence_threshold: float = 0.85,
) -> list[LlmRelationshipCandidate]:
    entity_rows = _load_entity_rows(manifest_path)
    previous_rows = _previous_index(previous_manifest_path)
    candidates: list[LlmRelationshipCandidate] = []

    for relationship_row in _load_relationship_rows(manifest_path):
        if float(relationship_row["relationship_confidence_score"]) >= confidence_threshold and str(
            relationship_row["relationship_type"]
        ) != "related_anime":
            continue

        source_entity_id = str(relationship_row["source_entity_id"])
        target_entity_id = str(relationship_row["target_entity_id"])
        source_row = entity_rows[source_entity_id]
        target_row = entity_rows[target_entity_id]
        if not (
            _row_allows_private_llm_judgment_input(source_row)
            and _row_allows_private_llm_judgment_input(target_row)
        ):
            continue

        previous_row = previous_rows.get((source_entity_id, target_entity_id))
        normalized_input = _normalized_candidate_input(
            source_row=source_row,
            target_row=target_row,
            relationship_row=relationship_row,
            previous_row=previous_row,
        )
        input_fingerprint = sha256(stable_json(normalized_input).encode("utf-8")).hexdigest()
        cache_key = model_cache_key(
            task=ModelTask.LLM_JUDGMENT,
            provider=provider,
            model=model,
            recipe_version=recipe_version,
            normalized_input=normalized_input,
        )

        changed_since_previous = previous_row is None or (
            previous_row["relationship_type"] != relationship_row["relationship_type"]
            or float(previous_row["relationship_confidence_score"])
            != float(relationship_row["relationship_confidence_score"])
        )

        candidates.append(
            LlmRelationshipCandidate(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relationship=str(relationship_row["relationship_type"]),
                source_domain=str(source_row["domain"]),
                target_domain=str(target_row["domain"]),
                source_title=str(source_row["title"]),
                target_title=str(target_row["title"]),
                source_original_title=(
                    None if source_row["original_title"] is None else str(source_row["original_title"])
                ),
                target_original_title=(
                    None if target_row["original_title"] is None else str(target_row["original_title"])
                ),
                source_media_type=str(source_row["media_type"]),
                target_media_type=str(target_row["media_type"]),
                source_release_year=int(source_row["release_year"]),
                target_release_year=int(target_row["release_year"]),
                source_genres=list(source_row.get("genres") or []),
                target_genres=list(target_row.get("genres") or []),
                source_studios=list(source_row.get("studios") or []),
                target_studios=list(target_row.get("studios") or []),
                source_creators=list(source_row.get("creators") or []),
                target_creators=list(target_row.get("creators") or []),
                relationship_confidence_score=float(relationship_row["relationship_confidence_score"]),
                supporting_source_count=int(relationship_row["supporting_source_count"]),
                supporting_provider_count=int(relationship_row["supporting_provider_count"]),
                supporting_urls=list(relationship_row.get("supporting_urls") or []),
                previous_relationship=(
                    None if previous_row is None else str(previous_row["relationship_type"])
                ),
                previous_relationship_confidence_score=(
                    None
                    if previous_row is None
                    else float(previous_row["relationship_confidence_score"])
                ),
                changed_since_previous=changed_since_previous,
                input_fingerprint=input_fingerprint,
                cache_key=cache_key,
            )
        )

    candidates.sort(
        key=lambda item: (
            item.relationship_confidence_score,
            -item.supporting_provider_count,
            item.source_entity_id,
            item.target_entity_id,
        )
    )
    return candidates


def write_llm_candidate_plan(
    *,
    manifest_path: Path,
    candidates: list[LlmRelationshipCandidate],
) -> LlmCandidatePlan:
    output_dir = manifest_path.parent
    candidates_path = output_dir / "llm-judgment-candidates.jsonl"
    summary_path = output_dir / "llm-judgment-summary.json"

    candidates_path.write_text(
        "\n".join(candidate.model_dump_json() for candidate in candidates)
        + ("\n" if candidates else ""),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(
            {
                "candidate_count": len(candidates),
                "manifest_path": str(manifest_path),
                "provider": DEFAULT_LLM_PROVIDER,
                "model": DEFAULT_LLM_MODEL,
                "public": False,
                "publishability_status": "private_experiment_only",
                "publishability_policy_version": LLM_PRIVATE_EXPERIMENT_POLICY_VERSION,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    _ensure_manifest_sidecars(
        manifest_path,
        entries=[
            {
                "path": candidates_path.name,
                "format": "jsonl",
                "kind": "llm_judgment_candidates",
                **_private_llm_sidecar_metadata(),
            },
            {
                "path": summary_path.name,
                "format": "json",
                "kind": "llm_judgment_summary",
                **_private_llm_sidecar_metadata(),
            },
        ],
    )

    return LlmCandidatePlan(
        manifest_path=manifest_path,
        candidate_count=len(candidates),
        candidates_path=candidates_path,
        summary_path=summary_path,
    )


def build_relationship_judgment_prompt(candidate: LlmRelationshipCandidate) -> str:
    validate_text_inputs(
        [
            SourceFieldReference(source_id="bootstrap_seed", field_name="title"),
            SourceFieldReference(source_id="bootstrap_seed", field_name="original_title"),
            SourceFieldReference(source_id="bootstrap_seed", field_name="media_type"),
            SourceFieldReference(source_id="bootstrap_seed", field_name="release_year"),
            SourceFieldReference(source_id="bootstrap_seed", field_name="genres"),
            SourceFieldReference(source_id="bootstrap_seed", field_name="studios"),
            SourceFieldReference(source_id="bootstrap_seed", field_name="creators"),
            SourceFieldReference(source_id="bootstrap_seed", field_name="relationship"),
            SourceFieldReference(source_id="bootstrap_seed", field_name="relationship_confidence"),
            SourceFieldReference(source_id="bootstrap_seed", field_name="supporting_urls"),
        ],
        artifact="llm-judgment",
        table="llm_judgments",
        column="prompt",
        use=PublishableUse.LLM_JUDGMENT_INPUT,
    )
    payload = {
        "source": {
            "entity_id": candidate.source_entity_id,
            "domain": candidate.source_domain,
            "title": candidate.source_title,
            "original_title": candidate.source_original_title,
            "media_type": candidate.source_media_type,
            "release_year": candidate.source_release_year,
            "genres": candidate.source_genres,
            "studios": candidate.source_studios,
            "creators": candidate.source_creators,
        },
        "target": {
            "entity_id": candidate.target_entity_id,
            "domain": candidate.target_domain,
            "title": candidate.target_title,
            "original_title": candidate.target_original_title,
            "media_type": candidate.target_media_type,
            "release_year": candidate.target_release_year,
            "genres": candidate.target_genres,
            "studios": candidate.target_studios,
            "creators": candidate.target_creators,
        },
        "current_relationship": candidate.relationship,
        "current_confidence_score": candidate.relationship_confidence_score,
        "previous_relationship": candidate.previous_relationship,
        "previous_confidence_score": candidate.previous_relationship_confidence_score,
        "supporting_source_count": candidate.supporting_source_count,
        "supporting_provider_count": candidate.supporting_provider_count,
        "supporting_urls": candidate.supporting_urls,
    }
    return f"""
You judge whether two media entities have the correct relationship label.

Return only a JSON object with this exact shape:
{{
  "relationship": "same_entity" | "sequel" | "prequel" | "continuation" | "spinoff" | "side_story" | "special" | "recap" | "compilation" | "movie_tie_in" | "remake" | "reboot" | "retelling" | "alternate_adaptation" | "adaptation_of" | "adapted_by" | "source_material" | "same_franchise" | "shared_universe" | "similar_to" | "unrelated" | "uncertain",
  "confidence": number,
  "reasoning": string
}}

Rules:
- same_entity is strict: same work, same release, same core record.
- sequel and prequel preserve direction from source entity to target entity.
- movie_tie_in needs an actual MOVIE/non-MOVIE pairing in the same franchise.
- special, recap, compilation, and side_story are episode-context labels, not broad franchise labels.
- remake, reboot, retelling, and alternate_adaptation require evidence of a distinct version line.
- adaptation_of and adapted_by preserve cross-medium source/adaptation direction.
- same_franchise and shared_universe are broad labels only when a tighter label is not justified.
- unrelated means shared words, broad genres, or vibes are not enough.
- uncertain only if the evidence is genuinely insufficient.

Case:
{stable_json(payload)}
""".strip()


def extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed_dict = cast(dict[object, Any], parsed)
            return {str(key): value for key, value in parsed_dict.items()}
        return None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            parsed_dict = cast(dict[object, Any], parsed)
            return {str(key): value for key, value in parsed_dict.items()}
        return None
    except json.JSONDecodeError:
        return None


def load_llm_candidates(candidates_path: Path) -> list[LlmRelationshipCandidate]:
    candidates: list[LlmRelationshipCandidate] = []
    for line in candidates_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        candidates.append(LlmRelationshipCandidate.model_validate_json(line))
    return candidates


def execute_llm_relationship_candidates(
    *,
    candidates_path: Path,
    manifest_path: Path,
    api_key: str,
    base_url: str,
    provider: str = DEFAULT_LLM_PROVIDER,
    model: str = DEFAULT_LLM_MODEL,
    recipe_version: str = DEFAULT_LLM_RECIPE_VERSION,
    client: OpenAiClientLike | None = None,
) -> LlmExecutionResult:
    resolved_client = client or OpenAI(api_key=api_key, base_url=base_url)
    candidates = load_llm_candidates(candidates_path)
    decisions: list[LlmDecisionRecord] = []

    for candidate in candidates:
        try:
            response = resolved_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Return only valid JSON."},
                    {"role": "user", "content": build_relationship_judgment_prompt(candidate)},
                ],
                temperature=0,
                max_tokens=300,
            )
            content = response.choices[0].message.content or ""
            parsed = extract_json_object(content)
            if parsed is None:
                decisions.append(
                    LlmDecisionRecord(
                        source_entity_id=candidate.source_entity_id,
                        target_entity_id=candidate.target_entity_id,
                        provider=provider,
                        model=model,
                        recipe_version=recipe_version,
                        input_fingerprint=candidate.input_fingerprint,
                        cache_key=candidate.cache_key,
                        raw_response=content,
                        status="parse_error",
                        error_type="json_parse_error",
                        error_message="Response did not contain a valid JSON object",
                    )
                )
                continue

            judgment = LlmRelationshipJudgment.model_validate(parsed)
            decisions.append(
                LlmDecisionRecord(
                    source_entity_id=candidate.source_entity_id,
                    target_entity_id=candidate.target_entity_id,
                    provider=provider,
                    model=model,
                    recipe_version=recipe_version,
                    input_fingerprint=candidate.input_fingerprint,
                    cache_key=candidate.cache_key,
                    raw_response=content,
                    judgment=judgment,
                    status="ok",
                )
            )
        except Exception as exc:
            decisions.append(
                LlmDecisionRecord(
                    source_entity_id=candidate.source_entity_id,
                    target_entity_id=candidate.target_entity_id,
                    provider=provider,
                    model=model,
                    recipe_version=recipe_version,
                    input_fingerprint=candidate.input_fingerprint,
                    cache_key=candidate.cache_key,
                    status="api_error",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )

    output_dir = manifest_path.parent
    decisions_path = output_dir / "llm-judgment-decisions.jsonl"
    summary_path = output_dir / "llm-judgment-execution-summary.json"

    decisions_path.write_text(
        "\n".join(decision.model_dump_json() for decision in decisions)
        + ("\n" if decisions else ""),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(
            {
                "candidate_count": len(candidates),
                "executed_count": len(decisions),
                "ok_count": sum(1 for decision in decisions if decision.status == "ok"),
                "parse_error_count": sum(
                    1 for decision in decisions if decision.status == "parse_error"
                ),
                "api_error_count": sum(1 for decision in decisions if decision.status == "api_error"),
                "provider": provider,
                "model": model,
                "recipe_version": recipe_version,
                "public": False,
                "publishability_status": "private_experiment_only",
                "publishability_policy_version": LLM_PRIVATE_EXPERIMENT_POLICY_VERSION,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    _ensure_manifest_sidecars(
        manifest_path,
        entries=[
            {
                "path": decisions_path.name,
                "format": "jsonl",
                "kind": "llm_judgment_decisions",
                **_private_llm_sidecar_metadata(),
            },
            {
                "path": summary_path.name,
                "format": "json",
                "kind": "llm_judgment_execution_summary",
                **_private_llm_sidecar_metadata(),
            },
        ],
    )

    return LlmExecutionResult(
        manifest_path=manifest_path,
        candidate_count=len(candidates),
        executed_count=len(decisions),
        decisions_path=decisions_path,
        summary_path=summary_path,
    )


def default_relationship_materialization_recipe(
    *,
    min_confidence: float = 0.8,
) -> LlmMaterializationRecipe:
    return LlmMaterializationRecipe(
        recipe_id="llm_relationship_materialization",
        recipe_version=DEFAULT_LLM_MATERIALIZATION_RECIPE_VERSION,
        target_surface=LlmMaterializationTarget.RELATIONSHIPS,
        allowed_judgment_kinds=[LlmJudgmentKind.RELATIONSHIP_CLASSIFICATION],
        output_schema_version=DEFAULT_LLM_OUTPUT_SCHEMA_VERSION,
        publishability_policy_version="publishability-policy-v1",
        min_confidence=min_confidence,
        min_publishable_evidence_refs=1,
        blocked_quality_flags=[
            "low_confidence",
            "non_publishable_input",
            "unsupported_relationship",
        ],
        required_parameters={"temperature": 0},
    )


def _row_is_publishable_input(row: dict[str, Any]) -> bool:
    return _row_allows_private_llm_judgment_input(row)


def _relationship_evidence_is_publishable(
    *,
    relationship_row: dict[str, Any],
    input_refs: list[LlmInputRef],
) -> bool:
    return (
        all(input_ref.publishable for input_ref in input_refs)
        and int(relationship_row.get("supporting_source_count") or 0) > 0
        and int(relationship_row.get("supporting_provider_count") or 0) > 0
    )


def _legacy_decision_to_judgment_record(
    *,
    decision: LlmDecisionRecord,
    relationship_row: dict[str, Any],
    entity_rows: dict[str, dict[str, Any]],
) -> LlmJudgmentRecord | None:
    if decision.status != "ok" or decision.judgment is None:
        return None

    source_row = entity_rows.get(decision.source_entity_id)
    target_row = entity_rows.get(decision.target_entity_id)
    if source_row is None or target_row is None:
        return None

    input_refs = [
        LlmInputRef(
            ref_id=decision.source_entity_id,
            ref_kind="entity",
            source_role=str(source_row.get("source_role") or "unknown"),
            policy_version="publishability-policy-v1",
            publishable=_row_is_publishable_input(source_row),
            allowed_uses=["llm_judgment"] if _row_is_publishable_input(source_row) else [],
        ),
        LlmInputRef(
            ref_id=decision.target_entity_id,
            ref_kind="entity",
            source_role=str(target_row.get("source_role") or "unknown"),
            policy_version="publishability-policy-v1",
            publishable=_row_is_publishable_input(target_row),
            allowed_uses=["llm_judgment"] if _row_is_publishable_input(target_row) else [],
        ),
    ]
    evidence_refs = [
        LlmEvidenceRef(
            evidence_id=f"{decision.cache_key}:supporting_url:{index}",
            evidence_kind="relationship_supporting_url",
            claim=str(url),
            publishable=_relationship_evidence_is_publishable(
                relationship_row=relationship_row,
                input_refs=input_refs,
            ),
        )
        for index, url in enumerate(list(relationship_row.get("supporting_urls") or []), start=1)
    ]
    quality_flags = ["model_inferred"]
    if decision.judgment.relationship.value == "uncertain":
        quality_flags.append("unsupported_relationship")
    if not all(input_ref.publishable for input_ref in input_refs):
        quality_flags.append("non_publishable_input")

    confidence = float(decision.judgment.confidence)
    confidence_tier: Literal["high", "medium", "low", "unknown"]
    if confidence >= 0.9:
        confidence_tier = "high"
    elif confidence >= 0.8:
        confidence_tier = "medium"
    else:
        confidence_tier = "low"

    return LlmJudgmentRecord(
        judgment_id=decision.cache_key,
        candidate_id=f"{decision.source_entity_id}:{decision.target_entity_id}:{decision.input_fingerprint}",
        kind=LlmJudgmentKind.RELATIONSHIP_CLASSIFICATION,
        status=LlmJudgmentStatus.APPROVED,
        target_entity_ids=[decision.source_entity_id, decision.target_entity_id],
        provider=decision.provider,
        model=decision.model,
        prompt_version=decision.recipe_version,
        parameters={"temperature": 0, "max_tokens": 300},
        input_refs=input_refs,
        evidence_refs=evidence_refs,
        output_schema_version=DEFAULT_LLM_OUTPUT_SCHEMA_VERSION,
        structured_output=decision.judgment.model_dump(mode="json"),
        confidence_profile=ConfidenceProfile(
            confidence=confidence,
            confidence_tier=confidence_tier,
            evidence_strength="model_with_publishable_relationship_evidence",
            agreement_status="unverified",
            extraction_method="model_judgment",
            freshness_status="unknown",
            recipe_version=decision.recipe_version,
        ),
        quality_flags=quality_flags,
        raw_response_ref=None if decision.raw_response is None else decision.cache_key,
    )


def _empty_materialized_relationships() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "source_entity_id": pl.String,
            "target_entity_id": pl.String,
            "relationship_type": pl.String,
            "relationship_confidence_score": pl.Float64,
            "judgment_id": pl.String,
            "materialization_recipe_id": pl.String,
            "materialization_recipe_version": pl.String,
            "confidence_profile_json": pl.String,
            "quality_flags": pl.List(pl.String),
            "evidence_ref_ids": pl.List(pl.String),
        }
    )


def apply_llm_relationship_judgments(
    *,
    manifest_path: Path,
    decisions_path: Path,
    min_confidence: float = 0.8,
) -> LlmApplyResult:
    files = _manifest_files(manifest_path)
    relationship_frame = pl.read_parquet(files["relationships"])
    entity_rows = _load_entity_rows(manifest_path)
    relationship_rows_by_pair = {
        (str(row["source_entity_id"]), str(row["target_entity_id"])): row
        for row in relationship_frame.iter_rows(named=True)
    }

    decisions: list[LlmDecisionRecord] = []
    for line in decisions_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        decisions.append(LlmDecisionRecord.model_validate_json(line))

    recipe = default_relationship_materialization_recipe(min_confidence=min_confidence)
    materialized_rows: list[dict[str, Any]] = []
    gate_decisions: list[dict[str, Any]] = []
    for decision in decisions:
        relationship_row = relationship_rows_by_pair.get(
            (decision.source_entity_id, decision.target_entity_id)
        )
        if relationship_row is None:
            continue
        judgment_record = _legacy_decision_to_judgment_record(
            decision=decision,
            relationship_row=relationship_row,
            entity_rows=entity_rows,
        )
        if judgment_record is None:
            continue

        gate_decision = evaluate_llm_materialization(
            judgment=judgment_record,
            recipe=recipe,
        )
        gate_decisions.append(gate_decision.model_dump(mode="json"))
        if not gate_decision.eligible:
            continue

        materialized_rows.append(
            {
                "source_entity_id": judgment_record.target_entity_ids[0],
                "target_entity_id": judgment_record.target_entity_ids[1],
                "relationship_type": str(judgment_record.structured_output["relationship"]),
                "relationship_confidence_score": judgment_record.confidence_profile.confidence,
                "judgment_id": judgment_record.judgment_id,
                "materialization_recipe_id": recipe.recipe_id,
                "materialization_recipe_version": recipe.recipe_version,
                "confidence_profile_json": judgment_record.confidence_profile.model_dump_json(),
                "quality_flags": judgment_record.quality_flags,
                "evidence_ref_ids": [
                    evidence_ref.evidence_id for evidence_ref in judgment_record.evidence_refs
                ],
            }
        )

    materialized_path = manifest_path.parent / "llm-materialized-relationships.parquet"
    materialized_frame = (
        pl.DataFrame(materialized_rows)
        if materialized_rows
        else _empty_materialized_relationships()
    )
    materialized_frame.write_parquet(materialized_path, compression="zstd")
    summary_path = manifest_path.parent / "llm-judgment-apply-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "manifest_path": str(manifest_path),
                "decisions_path": str(decisions_path),
                "relationship_count": relationship_frame.height,
                "eligible_decision_count": sum(
                    1 for gate_decision in gate_decisions if gate_decision["eligible"]
                ),
                "applied_count": len(materialized_rows),
                "unchanged_count": relationship_frame.height,
                "min_confidence": min_confidence,
                "materialized_path": materialized_path.name,
                "materialization_recipe_id": recipe.recipe_id,
                "materialization_recipe_version": recipe.recipe_version,
                "public": False,
                "publishability_status": "private_experiment_only",
                "publishability_policy_version": LLM_PRIVATE_EXPERIMENT_POLICY_VERSION,
                "gate_decisions": gate_decisions,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    _ensure_manifest_sidecars(
        manifest_path,
        entries=[
            {
                "path": summary_path.name,
                "format": "json",
                "kind": "llm_judgment_apply_summary",
                **_private_llm_sidecar_metadata(),
            },
            {
                "path": materialized_path.name,
                "format": "parquet",
                "kind": "llm_materialized_relationships",
                "schema_version": DEFAULT_LLM_OUTPUT_SCHEMA_VERSION,
                "recipe_version": recipe.recipe_version,
                **_private_llm_sidecar_metadata(),
            }
        ],
    )

    return LlmApplyResult(
        manifest_path=manifest_path,
        decisions_path=decisions_path,
        relationship_count=relationship_frame.height,
        eligible_decision_count=sum(
            1 for gate_decision in gate_decisions if gate_decision["eligible"]
        ),
        applied_count=len(materialized_rows),
        unchanged_count=relationship_frame.height,
        materialized_path=materialized_path,
        summary_path=summary_path,
    )


def _ensure_manifest_sidecars(manifest_path: Path, *, entries: list[dict[str, Any]]) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest["files"]
    by_path = {str(entry["path"]): entry for entry in files}
    for entry in entries:
        if entry["path"] in by_path:
            continue
        files.append(entry)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
