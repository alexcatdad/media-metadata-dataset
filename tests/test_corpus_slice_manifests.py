from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest

from media_offline_database.bootstrap import BootstrapEntity, load_bootstrap_entities
from media_offline_database.corpus_concept_search import search_corpus_by_concept

CORPUS_DIR = Path("corpus")
MANIFEST_PATHS = sorted(CORPUS_DIR.glob("*.slice-manifest.json"))
EXPECTED_MANIFEST_FILES = [
    "bootstrap-concept-romance-college-v1.slice-manifest.json",
    "bootstrap-death-note-v1.slice-manifest.json",
    "bootstrap-designated-survivor-v1.slice-manifest.json",
    "bootstrap-ghost-in-the-shell-v1.slice-manifest.json",
    "bootstrap-screen-v1.slice-manifest.json",
]


def _load_manifest(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _duplicate_title_counts(entities: list[BootstrapEntity]) -> list[dict[str, object]]:
    counts = Counter(entity.title for entity in entities)
    return [
        {"title": title, "count": count}
        for title, count in sorted(counts.items())
        if count > 1
    ]


def _relationship_counts(entities: list[BootstrapEntity]) -> dict[str, int]:
    counts = Counter(
        edge.relationship
        for entity in entities
        for edge in entity.related
    )
    return dict(sorted(counts.items()))


def _entities_for_manifest(
    manifest_path: Path,
) -> tuple[dict[str, Any], Path, list[BootstrapEntity]]:
    manifest = _load_manifest(manifest_path)
    dataset = cast(dict[str, Any], manifest["dataset"])
    dataset_path = CORPUS_DIR / str(dataset["path"])
    entities = load_bootstrap_entities(dataset_path)
    return manifest, dataset_path, entities


def test_slice_manifests_cover_current_checked_in_slices() -> None:
    assert [path.name for path in MANIFEST_PATHS] == EXPECTED_MANIFEST_FILES


@pytest.mark.parametrize("manifest_path", MANIFEST_PATHS, ids=lambda path: path.stem)
def test_slice_manifest_matches_checked_in_dataset(manifest_path: Path) -> None:
    manifest, dataset_path, entities = _entities_for_manifest(manifest_path)
    dataset = cast(dict[str, Any], manifest["dataset"])

    assert manifest["manifest_version"] == 1
    assert manifest["slice_id"] == dataset_path.stem
    assert manifest["entity_model"] == "bootstrap-entity-v1"
    assert manifest["proves"]
    assert dataset["path"] == dataset_path.name
    assert dataset["sha256"] == _sha256(dataset_path)
    assert dataset["entity_count"] == len(entities)
    assert dataset["relationship_count"] == sum(len(entity.related) for entity in entities)
    assert dataset["domains"] == sorted({entity.domain for entity in entities})
    assert dataset["entity_ids_in_order"] == [entity.entity_id for entity in entities]
    assert dataset["relationship_counts"] == _relationship_counts(entities)
    assert dataset["duplicate_title_counts"] == _duplicate_title_counts(entities)


@pytest.mark.parametrize("manifest_path", MANIFEST_PATHS, ids=lambda path: path.stem)
def test_slice_manifest_anchor_checks_match_entities(manifest_path: Path) -> None:
    manifest, _, entities = _entities_for_manifest(manifest_path)
    entity_index = {entity.entity_id: entity for entity in entities}
    anchors = cast(list[dict[str, Any]], manifest["anchors"])

    for anchor in anchors:
        entity = entity_index[cast(str, anchor["entity_id"])]
        checks = cast(dict[str, Any], anchor["checks"])

        scalar_fields = [
            "title",
            "original_title",
            "domain",
            "media_type",
            "source_role",
            "episodes",
        ]
        for field_name in scalar_fields:
            if field_name not in checks:
                continue

            actual_value = getattr(entity, field_name)
            if field_name == "source_role":
                actual_value = entity.source_role.value
            assert actual_value == checks[field_name]

        if "relationship_types" in checks:
            assert sorted({edge.relationship for edge in entity.related}) == sorted(
                cast(list[str], checks["relationship_types"])
            )

        if "related_targets" in checks:
            assert [edge.target for edge in entity.related] == cast(
                list[str], checks["related_targets"]
            )

        if "tags_include" in checks:
            assert set(cast(list[str], checks["tags_include"])) <= set(entity.tags)

        if "genres_include" in checks:
            assert set(cast(list[str], checks["genres_include"])) <= set(entity.genres)


def test_concept_slice_query_contract_matches_checked_in_manifest() -> None:
    manifest_path = CORPUS_DIR / "bootstrap-concept-romance-college-v1.slice-manifest.json"
    manifest, _, entities = _entities_for_manifest(manifest_path)
    query_contract = cast(dict[str, Any], manifest["query_contract"])

    preview = search_corpus_by_concept(
        entities,
        query=str(query_contract["query"]),
        limit=int(query_contract["limit"]),
    )

    expected_filters = cast(dict[str, Any], query_contract["expected_filters"])
    top_match = cast(dict[str, Any], query_contract["top_match"])

    assert [match.entity_id for match in preview.matches] == cast(
        list[str], query_contract["expected_entity_ids"]
    )
    assert [match.title for match in preview.matches] == cast(
        list[str], query_contract["expected_titles"]
    )
    assert preview.filters.genres == cast(list[str], expected_filters["genres"])
    assert preview.filters.tags == cast(list[str], expected_filters["tags"])
    assert preview.matches[0].entity_id == cast(str, top_match["entity_id"])
    assert preview.matches[0].matched_genres == cast(list[str], top_match["matched_genres"])
    assert preview.matches[0].matched_tags == cast(list[str], top_match["matched_tags"])
