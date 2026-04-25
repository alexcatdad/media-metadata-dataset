from __future__ import annotations

from media_offline_database.bootstrap import BootstrapRelatedEdge
from media_offline_database.relationships import (
    relationship_confidence,
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
