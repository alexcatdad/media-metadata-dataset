from __future__ import annotations

from collections.abc import Sequence
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
        "franchise_related": 0.55,
        "movie_related": 0.72,
        "same_creator": 0.68,
        "same_studio": 0.66,
        "special_related": 0.7,
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


def _edge_supporting_urls(edge: RelationshipEdgeLike) -> list[str]:
    if edge.supporting_urls:
        return list(dict.fromkeys(edge.supporting_urls))
    return [edge.target_url]


def _has_provider(urls: Sequence[str], provider: str) -> bool:
    return any(_provider_for_url(url) == provider for url in urls)


def _provider_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return _HOST_TO_PROVIDER.get(host, url)
