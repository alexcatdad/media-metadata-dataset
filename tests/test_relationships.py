from __future__ import annotations

from media_offline_database.bootstrap import BootstrapRelatedEdge
from media_offline_database.relationships import (
    RELATIONSHIP_RECIPE_VERSION,
    deterministic_anilist_relationship_recipe,
    inverse_relationship,
    relationship_confidence,
    relationship_confidence_profile,
    relationship_direction,
    relationship_family,
    relationship_quality_flags,
    supporting_provider_count,
    supporting_source_count,
)


def test_relationship_metrics_reflect_support_density_and_specificity() -> None:
    typed_edge = BootstrapRelatedEdge(
        target="anime:manami:anidb:13612",
        relationship="sequel_prequel",
        target_url="https://anidb.net/anime/13612",
        supporting_urls=[
            "https://anidb.net/anime/13612",
            "https://anilist.co/anime/100643",
            "https://myanimelist.net/anime/36862",
            "https://simkl.com/anime/740881",
        ],
    )
    generic_edge = BootstrapRelatedEdge(
        target="anime:manami:anime-planet:made-in-abyss-marulks-daily-life",
        relationship="related_anime",
        target_url="https://anime-planet.com/anime/made-in-abyss-marulks-daily-life",
        supporting_urls=[
            "https://anime-planet.com/anime/made-in-abyss-marulks-daily-life"
        ],
    )

    assert supporting_source_count(typed_edge) == 4
    assert supporting_provider_count(typed_edge) == 4
    assert relationship_confidence(typed_edge) == 0.98
    assert supporting_source_count(generic_edge) == 1
    assert supporting_provider_count(generic_edge) == 1
    assert relationship_confidence(generic_edge) == 0.42


def test_relationship_contract_preserves_precise_type_family_and_inverse() -> None:
    assert relationship_family("sequel") == "continuity"
    assert relationship_direction("sequel") == "directed"
    assert inverse_relationship("sequel") == "prequel"
    assert relationship_family("sequel_prequel") == "continuity"
    assert relationship_direction("sequel_prequel") == "paired"


def test_confidence_profile_is_dimensional_and_recipe_specific() -> None:
    edge = BootstrapRelatedEdge(
        target="anime:manami:anidb:13612",
        relationship="sequel",
        target_url="https://anidb.net/anime/13612",
        supporting_urls=[
            "https://anidb.net/anime/13612",
            "https://anilist.co/anime/100643",
        ],
    )

    assert relationship_quality_flags(edge) == [
        "source_backed",
        "deterministic_recipe",
    ]
    assert relationship_confidence_profile(edge) == {
        "agreement_status": "multi_provider",
        "confidence_tier": "high",
        "evidence_origin": "source_backed_relationship",
        "evidence_strength": "moderate",
        "extraction_method": "deterministic",
        "freshness_status": "snapshot_current",
        "quality_flags": ["source_backed", "deterministic_recipe"],
        "recipe_version": RELATIONSHIP_RECIPE_VERSION,
        "score_scope": "recipe_local",
    }


def test_anilist_recipe_queues_ambiguous_cases_for_judgment() -> None:
    sequel = deterministic_anilist_relationship_recipe(
        relation_type="SEQUEL",
        target_format="TV",
        evidence_refs=["https://anilist.co/anime/1"],
    )
    ambiguous = deterministic_anilist_relationship_recipe(
        relation_type="ALTERNATIVE",
        target_format="TV",
        evidence_refs=["https://anilist.co/anime/2"],
    )

    assert sequel.relationship == "sequel"
    assert sequel.recipe_version == RELATIONSHIP_RECIPE_VERSION
    assert ambiguous.relationship is None
    assert ambiguous.judgment_candidate_reason == "anilist_relation_type:ALTERNATIVE"
