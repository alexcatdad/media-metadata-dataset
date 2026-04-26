from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlparse

_HOST_TO_PROVIDER = {
    "anidb.net": "anidb",
    "anilist.co": "anilist",
    "myanimelist.net": "myanimelist",
    "kitsu.app": "kitsu",
    "simkl.com": "simkl",
    "anime-planet.com": "anime-planet",
}


class RelationshipEdgeLike(Protocol):
    relationship: str
    target_url: str
    supporting_urls: list[str]


class RelationshipFamily(StrEnum):
    IDENTITY = "identity"
    CONTINUITY = "continuity"
    ADAPTATION = "adaptation"
    VARIANT = "variant"
    FRANCHISE = "franchise"
    EPISODE_CONTEXT = "episode_context"
    SIMILARITY = "similarity"
    UNCERTAIN = "uncertain"


class RelationshipDirection(StrEnum):
    DIRECTED = "directed"
    UNDIRECTED = "undirected"
    PAIRED = "paired"
    UNKNOWN = "unknown"


class RelationshipQualityFlag(StrEnum):
    SOURCE_BACKED = "source_backed"
    DETERMINISTIC_RECIPE = "deterministic_recipe"
    LEGACY_BROAD_TYPE = "legacy_broad_type"
    JUDGMENT_CANDIDATE = "judgment_candidate"


class ConfidenceTier(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REVIEW = "review"


@dataclass(frozen=True)
class RelationshipTypeContract:
    relationship: str
    family: RelationshipFamily
    direction: RelationshipDirection
    inverse_relationship: str | None
    deterministic: bool


@dataclass(frozen=True)
class RelationshipRecipeResult:
    relationship: str | None
    recipe_version: str
    evidence_refs: tuple[str, ...]
    judgment_candidate_reason: str | None = None


RELATIONSHIP_RECIPE_VERSION = "relationship-taxonomy-v1"

RELATIONSHIP_TYPES: dict[str, RelationshipTypeContract] = {
    "same_entity": RelationshipTypeContract(
        "same_entity", RelationshipFamily.IDENTITY, RelationshipDirection.UNDIRECTED, "same_entity", True
    ),
    "sequel": RelationshipTypeContract(
        "sequel", RelationshipFamily.CONTINUITY, RelationshipDirection.DIRECTED, "prequel", True
    ),
    "prequel": RelationshipTypeContract(
        "prequel", RelationshipFamily.CONTINUITY, RelationshipDirection.DIRECTED, "sequel", True
    ),
    "continuation": RelationshipTypeContract(
        "continuation",
        RelationshipFamily.CONTINUITY,
        RelationshipDirection.DIRECTED,
        None,
        True,
    ),
    "spinoff": RelationshipTypeContract(
        "spinoff", RelationshipFamily.FRANCHISE, RelationshipDirection.DIRECTED, None, True
    ),
    "side_story": RelationshipTypeContract(
        "side_story",
        RelationshipFamily.EPISODE_CONTEXT,
        RelationshipDirection.DIRECTED,
        None,
        True,
    ),
    "special": RelationshipTypeContract(
        "special", RelationshipFamily.EPISODE_CONTEXT, RelationshipDirection.DIRECTED, None, True
    ),
    "recap": RelationshipTypeContract(
        "recap", RelationshipFamily.EPISODE_CONTEXT, RelationshipDirection.DIRECTED, None, True
    ),
    "compilation": RelationshipTypeContract(
        "compilation",
        RelationshipFamily.EPISODE_CONTEXT,
        RelationshipDirection.DIRECTED,
        None,
        True,
    ),
    "movie_tie_in": RelationshipTypeContract(
        "movie_tie_in",
        RelationshipFamily.EPISODE_CONTEXT,
        RelationshipDirection.DIRECTED,
        None,
        True,
    ),
    "remake": RelationshipTypeContract(
        "remake", RelationshipFamily.VARIANT, RelationshipDirection.DIRECTED, None, True
    ),
    "reboot": RelationshipTypeContract(
        "reboot", RelationshipFamily.VARIANT, RelationshipDirection.DIRECTED, None, True
    ),
    "retelling": RelationshipTypeContract(
        "retelling", RelationshipFamily.VARIANT, RelationshipDirection.DIRECTED, None, True
    ),
    "alternate_adaptation": RelationshipTypeContract(
        "alternate_adaptation",
        RelationshipFamily.ADAPTATION,
        RelationshipDirection.UNDIRECTED,
        "alternate_adaptation",
        True,
    ),
    "adaptation_of": RelationshipTypeContract(
        "adaptation_of",
        RelationshipFamily.ADAPTATION,
        RelationshipDirection.DIRECTED,
        "adapted_by",
        True,
    ),
    "adapted_by": RelationshipTypeContract(
        "adapted_by",
        RelationshipFamily.ADAPTATION,
        RelationshipDirection.DIRECTED,
        "adaptation_of",
        True,
    ),
    "source_material": RelationshipTypeContract(
        "source_material",
        RelationshipFamily.ADAPTATION,
        RelationshipDirection.DIRECTED,
        "adapted_by",
        True,
    ),
    "same_franchise": RelationshipTypeContract(
        "same_franchise",
        RelationshipFamily.FRANCHISE,
        RelationshipDirection.UNDIRECTED,
        "same_franchise",
        True,
    ),
    "shared_universe": RelationshipTypeContract(
        "shared_universe",
        RelationshipFamily.FRANCHISE,
        RelationshipDirection.UNDIRECTED,
        "shared_universe",
        True,
    ),
    "similar_to": RelationshipTypeContract(
        "similar_to", RelationshipFamily.SIMILARITY, RelationshipDirection.UNDIRECTED, "similar_to", False
    ),
    "unrelated": RelationshipTypeContract(
        "unrelated", RelationshipFamily.UNCERTAIN, RelationshipDirection.UNDIRECTED, "unrelated", False
    ),
    "uncertain": RelationshipTypeContract(
        "uncertain", RelationshipFamily.UNCERTAIN, RelationshipDirection.UNKNOWN, None, False
    ),
    # Legacy broad labels remain accepted while richer recipes migrate producers.
    "sequel_prequel": RelationshipTypeContract(
        "sequel_prequel",
        RelationshipFamily.CONTINUITY,
        RelationshipDirection.PAIRED,
        "sequel_prequel",
        False,
    ),
    "movie_related": RelationshipTypeContract(
        "movie_related",
        RelationshipFamily.EPISODE_CONTEXT,
        RelationshipDirection.UNKNOWN,
        None,
        False,
    ),
    "special_related": RelationshipTypeContract(
        "special_related",
        RelationshipFamily.EPISODE_CONTEXT,
        RelationshipDirection.UNKNOWN,
        None,
        False,
    ),
    "remake_reboot": RelationshipTypeContract(
        "remake_reboot", RelationshipFamily.VARIANT, RelationshipDirection.UNKNOWN, None, False
    ),
    "adaptation_related": RelationshipTypeContract(
        "adaptation_related",
        RelationshipFamily.ADAPTATION,
        RelationshipDirection.UNKNOWN,
        None,
        False,
    ),
    "franchise_related": RelationshipTypeContract(
        "franchise_related",
        RelationshipFamily.FRANCHISE,
        RelationshipDirection.UNKNOWN,
        None,
        False,
    ),
    "related_anime": RelationshipTypeContract(
        "related_anime", RelationshipFamily.UNCERTAIN, RelationshipDirection.UNKNOWN, None, False
    ),
    "same_creator": RelationshipTypeContract(
        "same_creator", RelationshipFamily.SIMILARITY, RelationshipDirection.UNDIRECTED, "same_creator", False
    ),
    "same_studio": RelationshipTypeContract(
        "same_studio", RelationshipFamily.SIMILARITY, RelationshipDirection.UNDIRECTED, "same_studio", False
    ),
}


def supporting_source_count(edge: RelationshipEdgeLike) -> int:
    return len(_edge_supporting_urls(edge))


def supporting_provider_count(edge: RelationshipEdgeLike) -> int:
    providers: set[str] = set()

    for url in _edge_supporting_urls(edge):
        providers.add(_provider_for_url(url))

    return len(providers)


def relationship_confidence(edge: RelationshipEdgeLike) -> float:
    relationship_base = {
        "adaptation_related": 0.62,
        "adaptation_of": 0.74,
        "adapted_by": 0.74,
        "alternate_adaptation": 0.7,
        "compilation": 0.7,
        "continuation": 0.78,
        "franchise_related": 0.55,
        "movie_related": 0.72,
        "movie_tie_in": 0.72,
        "prequel": 0.78,
        "recap": 0.7,
        "reboot": 0.76,
        "remake": 0.76,
        "same_creator": 0.68,
        "same_franchise": 0.62,
        "same_studio": 0.66,
        "sequel": 0.78,
        "special_related": 0.7,
        "special": 0.7,
        "sequel_prequel": 0.78,
        "remake_reboot": 0.76,
        "related_anime": 0.42,
    }.get(edge.relationship, 0.4)

    source_count = supporting_source_count(edge)
    provider_count = supporting_provider_count(edge)
    source_bonus = min(max(source_count - 1, 0), 5) * 0.04
    provider_bonus = min(max(provider_count - 1, 0), 4) * 0.05
    typed_anilist_bonus = (
        0.06
        if edge.relationship != "related_anime" and _has_provider(edge.supporting_urls, "anilist")
        else 0.0
    )
    confidence = relationship_base + source_bonus + provider_bonus + typed_anilist_bonus
    return round(min(confidence, 0.98), 2)


def relationship_confidence_score(edge: RelationshipEdgeLike) -> float:
    return relationship_confidence(edge)


def relationship_contract(relationship: str) -> RelationshipTypeContract:
    return RELATIONSHIP_TYPES.get(
        relationship,
        RelationshipTypeContract(
            relationship=relationship,
            family=RelationshipFamily.UNCERTAIN,
            direction=RelationshipDirection.UNKNOWN,
            inverse_relationship=None,
            deterministic=False,
        ),
    )


def relationship_family(relationship: str) -> str:
    return relationship_contract(relationship).family.value


def relationship_direction(relationship: str) -> str:
    return relationship_contract(relationship).direction.value


def inverse_relationship(relationship: str) -> str | None:
    return relationship_contract(relationship).inverse_relationship


def relationship_evidence_id(
    *,
    source_entity_id: str,
    target_entity_id: str,
    relationship: str,
    supporting_urls: Sequence[str],
) -> str:
    payload = {
        "relationship": relationship,
        "source_entity_id": source_entity_id,
        "supporting_urls": list(dict.fromkeys(supporting_urls)),
        "target_entity_id": target_entity_id,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"relationship-evidence:{digest}"


def relationship_id(
    *,
    source_entity_id: str,
    target_entity_id: str,
    relationship: str,
) -> str:
    payload = {
        "relationship": relationship,
        "source_entity_id": source_entity_id,
        "target_entity_id": target_entity_id,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"relationship:{digest}"


def relationship_quality_flags(edge: RelationshipEdgeLike) -> list[str]:
    contract = relationship_contract(edge.relationship)
    flags = [RelationshipQualityFlag.SOURCE_BACKED.value]
    if contract.deterministic:
        flags.append(RelationshipQualityFlag.DETERMINISTIC_RECIPE.value)
    if edge.relationship in {
        "adaptation_related",
        "franchise_related",
        "movie_related",
        "related_anime",
        "remake_reboot",
        "sequel_prequel",
        "special_related",
    }:
        flags.append(RelationshipQualityFlag.LEGACY_BROAD_TYPE.value)
    if contract.family == RelationshipFamily.UNCERTAIN or edge.relationship == "related_anime":
        flags.append(RelationshipQualityFlag.JUDGMENT_CANDIDATE.value)
    return flags


def relationship_confidence_tier(edge: RelationshipEdgeLike) -> str:
    confidence = relationship_confidence(edge)
    if RelationshipQualityFlag.JUDGMENT_CANDIDATE.value in relationship_quality_flags(edge):
        return ConfidenceTier.REVIEW.value
    if confidence >= 0.8:
        return ConfidenceTier.HIGH.value
    if confidence >= 0.6:
        return ConfidenceTier.MEDIUM.value
    return ConfidenceTier.LOW.value


def relationship_confidence_score_tier(edge: RelationshipEdgeLike) -> str:
    return relationship_confidence_tier(edge)


def relationship_confidence_profile(edge: RelationshipEdgeLike) -> dict[str, object]:
    contract = relationship_contract(edge.relationship)
    provider_count = supporting_provider_count(edge)
    source_count = supporting_source_count(edge)
    return {
        "agreement_status": _agreement_status(provider_count),
        "confidence_tier": relationship_confidence_tier(edge),
        "evidence_origin": "source_backed_relationship",
        "evidence_strength": _evidence_strength(source_count, provider_count),
        "extraction_method": "deterministic" if contract.deterministic else "source_broad_label",
        "freshness_status": "snapshot_current",
        "quality_flags": relationship_quality_flags(edge),
        "recipe_version": RELATIONSHIP_RECIPE_VERSION,
        "score_scope": "recipe_local",
    }


def relationship_confidence_profile_json(edge: RelationshipEdgeLike) -> str:
    return json.dumps(
        relationship_confidence_profile(edge),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def relationship_confidence_score_profile_json(edge: RelationshipEdgeLike) -> str:
    return relationship_confidence_profile_json(edge)


def deterministic_anilist_relationship_recipe(
    *,
    relation_type: str,
    target_format: str | None,
    evidence_refs: Sequence[str] = (),
) -> RelationshipRecipeResult:
    relation = relation_type.upper()
    relationship = _deterministic_anilist_relationship(
        relation_type=relation,
        target_format=target_format,
    )
    if relationship is not None:
        return RelationshipRecipeResult(
            relationship=relationship,
            recipe_version=RELATIONSHIP_RECIPE_VERSION,
            evidence_refs=tuple(evidence_refs),
        )
    return RelationshipRecipeResult(
        relationship=None,
        recipe_version=RELATIONSHIP_RECIPE_VERSION,
        evidence_refs=tuple(evidence_refs),
        judgment_candidate_reason=f"anilist_relation_type:{relation}",
    )


def _edge_supporting_urls(edge: RelationshipEdgeLike) -> list[str]:
    if edge.supporting_urls:
        return list(dict.fromkeys(edge.supporting_urls))
    return [edge.target_url]


def _has_provider(urls: Sequence[str], provider: str) -> bool:
    return any(_provider_for_url(url) == provider for url in urls)


def _provider_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return _HOST_TO_PROVIDER.get(host, url)


def _agreement_status(provider_count: int) -> str:
    if provider_count >= 2:
        return "multi_provider"
    if provider_count == 1:
        return "single_provider"
    return "no_provider"


def _evidence_strength(source_count: int, provider_count: int) -> str:
    if source_count >= 3 and provider_count >= 2:
        return "strong"
    if source_count >= 1:
        return "moderate"
    return "weak"


def _deterministic_anilist_relationship(
    *,
    relation_type: str,
    target_format: str | None,
) -> str | None:
    if relation_type == "SEQUEL":
        return "sequel"
    if relation_type == "PREQUEL":
        return "prequel"
    if relation_type == "SPIN_OFF":
        return "spinoff"
    if relation_type == "SIDE_STORY":
        return "side_story"
    if relation_type == "SUMMARY":
        return "recap"
    if relation_type == "COMPILATION":
        return "compilation"
    if relation_type in {"PARENT", "CONTAINS"}:
        return _format_aware_precise_relationship(target_format)
    return None


def _format_aware_precise_relationship(target_format: str | None) -> str | None:
    if target_format == "MOVIE":
        return "movie_tie_in"
    if target_format in {"SPECIAL", "OVA", "ONA", "TV_SHORT"}:
        return "special"
    return None
