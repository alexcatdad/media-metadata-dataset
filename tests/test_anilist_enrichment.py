from __future__ import annotations

import json
from pathlib import Path

from media_offline_database.bootstrap import BootstrapEntity, BootstrapRelatedEdge
from media_offline_database.enrich_anilist_relations import (
    AniListResolvedRelation,
    canonicalize_bootstrap_relationship_targets,
    classify_anilist_relationship,
    enrich_bootstrap_entities_with_anilist_relations,
    write_anilist_relation_enriched_seed,
)
from media_offline_database.sources import SourceRole


def test_classify_anilist_relationship_maps_core_relation_types() -> None:
    assert (
        classify_anilist_relationship(relation_type="SEQUEL", target_format="TV")
        == "sequel_prequel"
    )
    assert (
        classify_anilist_relationship(relation_type="PREQUEL", target_format="MOVIE")
        == "sequel_prequel"
    )
    assert (
        classify_anilist_relationship(relation_type="ALTERNATIVE", target_format="TV")
        == "remake_reboot"
    )
    assert (
        classify_anilist_relationship(relation_type="SUMMARY", target_format="MOVIE")
        == "movie_related"
    )
    assert (
        classify_anilist_relationship(relation_type="SIDE_STORY", target_format="OVA")
        == "special_related"
    )
    assert (
        classify_anilist_relationship(relation_type="SOURCE", target_format=None)
        == "related_anime"
    )


def test_enrich_bootstrap_entities_with_anilist_relations_retypes_matching_edges() -> None:
    entities = [
        _bootstrap_entity(
            entity_id="anime:manami:anidb:12681",
            title="Made in Abyss",
            sources=[
                "https://anidb.net/anime/12681",
                "https://anilist.co/anime/97986",
            ],
            related=[
                BootstrapRelatedEdge(
                    target="anime:manami:anilist:101343",
                    relationship="related_anime",
                    target_url="https://anilist.co/anime/101343",
                ),
                BootstrapRelatedEdge(
                    target="anime:manami:anidb:14177",
                    relationship="related_anime",
                    target_url="https://anidb.net/anime/14177",
                ),
            ],
        ),
        _bootstrap_entity(
            entity_id="anime:manami:anilist:101343",
            title="Made in Abyss: Tabidachi no Yoake",
            sources=["https://anilist.co/anime/101343"],
        ),
        _bootstrap_entity(
            entity_id="anime:manami:anidb:14177",
            title="Made in Abyss Movie 3: Fukaki Tamashii no Reimei",
            sources=[
                "https://anidb.net/anime/14177",
                "https://anilist.co/anime/109911",
            ],
        ),
    ]

    def fake_fetcher(anilist_id: int) -> list[AniListResolvedRelation]:
        if anilist_id != 97986:
            return []
        return [
            AniListResolvedRelation(
                target_anilist_id=101343,
                relation_type="SUMMARY",
                target_format="MOVIE",
            ),
            AniListResolvedRelation(
                target_anilist_id=109911,
                relation_type="SEQUEL",
                target_format="MOVIE",
            ),
        ]

    enriched = enrich_bootstrap_entities_with_anilist_relations(
        entities,
        fetch_relations=fake_fetcher,
    )

    assert [edge.relationship for edge in enriched[0].related] == [
        "movie_related",
        "sequel_prequel",
    ]
    assert enriched[0].related[0].supporting_urls == [
        "https://anilist.co/anime/101343",
        "https://anilist.co/anime/97986",
    ]
    assert enriched[0].related[1].supporting_urls == [
        "https://anidb.net/anime/14177",
        "https://anilist.co/anime/97986",
        "https://anilist.co/anime/109911",
    ]


def test_canonicalize_bootstrap_relationship_targets_collapses_alias_edges() -> None:
    entities = [
        _bootstrap_entity(
            entity_id="anime:manami:anidb:12681",
            title="Made in Abyss",
            sources=[
                "https://anidb.net/anime/12681",
                "https://anilist.co/anime/97986",
                "https://myanimelist.net/anime/34599",
            ],
        ),
        _bootstrap_entity(
            entity_id="anime:manami:anidb:13941",
            title="Gekijouban Soushuuhen Made in Abyss",
            sources=[
                "https://anidb.net/anime/13941",
                "https://simkl.com/anime/784549",
            ],
            related=[
                BootstrapRelatedEdge(
                    target="anime:manami:anidb:12681",
                    relationship="related_anime",
                    target_url="https://anidb.net/anime/12681",
                ),
                BootstrapRelatedEdge(
                    target="anime:manami:anilist:97986",
                    relationship="related_anime",
                    target_url="https://anilist.co/anime/97986",
                ),
                BootstrapRelatedEdge(
                    target="anime:manami:myanimelist:34599",
                    relationship="related_anime",
                    target_url="https://myanimelist.net/anime/34599",
                ),
            ],
        ),
    ]

    canonicalized = canonicalize_bootstrap_relationship_targets(entities)

    assert canonicalized[1].related == [
        BootstrapRelatedEdge(
            target="anime:manami:anidb:12681",
            relationship="related_anime",
            target_url="https://anidb.net/anime/12681",
            supporting_urls=[
                "https://anidb.net/anime/12681",
                "https://anilist.co/anime/97986",
                "https://myanimelist.net/anime/34599",
            ],
        )
    ]


def test_write_anilist_relation_enriched_seed_writes_jsonl(tmp_path: Path) -> None:
    input_path = tmp_path / "normalized.jsonl"
    input_path.write_text(
        "\n".join(
            [
                _bootstrap_entity(
                    entity_id="anime:manami:anidb:270",
                    title="Hellsing",
                    sources=[
                        "https://anidb.net/anime/270",
                        "https://anilist.co/anime/270",
                    ],
                    related=[
                        BootstrapRelatedEdge(
                            target="anime:manami:anidb:777",
                            relationship="related_anime",
                            target_url="https://anidb.net/anime/777",
                        )
                    ],
                ).model_dump_json(),
                _bootstrap_entity(
                    entity_id="anime:manami:anidb:777",
                    title="Hellsing Ultimate",
                    sources=[
                        "https://anidb.net/anime/777",
                        "https://anilist.co/anime/777",
                    ],
                ).model_dump_json(),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "enriched.jsonl"

    def fake_fetcher(_: int) -> list[AniListResolvedRelation]:
        return [
            AniListResolvedRelation(
                target_anilist_id=777,
                relation_type="ALTERNATIVE",
                target_format="OVA",
            )
        ]

    written_path = write_anilist_relation_enriched_seed(
        input_path=input_path,
        output_path=output_path,
        fetch_relations=fake_fetcher,
    )

    payload = [
        json.loads(line)
        for line in written_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert written_path == output_path
    assert payload[0]["related"][0]["relationship"] == "remake_reboot"
    assert payload[0]["related"][0]["supporting_urls"] == [
        "https://anidb.net/anime/777",
        "https://anilist.co/anime/270",
        "https://anilist.co/anime/777",
    ]


def _bootstrap_entity(
    *,
    entity_id: str,
    title: str,
    sources: list[str],
    related: list[BootstrapRelatedEdge] | None = None,
) -> BootstrapEntity:
    return BootstrapEntity(
        entity_id=entity_id,
        domain="anime",
        canonical_source=sources[0],
        source_role=SourceRole.BACKBONE_SOURCE,
        record_source="test",
        title=title,
        media_type="TV",
        status="FINISHED",
        release_year=2000,
        sources=sources,
        related=related or [],
    )
