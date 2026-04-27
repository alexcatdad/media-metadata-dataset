from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from media_offline_database import __version__
from media_offline_database.artifacts import artifact_manifest_metadata
from media_offline_database.bootstrap import BootstrapEntity, load_bootstrap_entities
from media_offline_database.contracts import (
    CORE_SCHEMA_VERSION,
    CORE_TABLE_CONTRACTS,
    PROFILE_TABLE_CONTRACTS,
)
from media_offline_database.ingest_normalization import (
    ProviderRun,
    SourceSnapshot,
    load_provider_runs,
    load_source_snapshots,
)
from media_offline_database.publishability import (
    ARTIFACT_POLICY_VERSION,
    PUBLISHABILITY_POLICY_VERSION,
    SOURCE_FIELD_POLICY_VERSION,
    SOURCE_POLICY_VERSION,
    ArtifactInput,
    PublishableUse,
    SourceFieldReference,
    publishability_manifest_payload,
    validate_artifact_inputs,
)
from media_offline_database.relationships import (
    RELATIONSHIP_RECIPE_VERSION,
    inverse_relationship,
    relationship_direction,
    relationship_family,
)

V1_ARTIFACT = "media-metadata-v1"
V1_BUILD_STAGE = "shared-core-profile"
V1_RECIPE_VERSION = "shared-core-profile-v1"
DEFAULT_V1_OUTPUT_DIR = Path(".mod/out/v1-core")


def write_v1_core_artifact(
    *,
    input_paths: Sequence[Path],
    output_dir: Path = DEFAULT_V1_OUTPUT_DIR,
    source_snapshot_ids: Mapping[str, str] | None = None,
    source_snapshot_paths: Sequence[Path] | None = None,
    provider_run_paths: Sequence[Path] | None = None,
) -> Path:
    entities = _load_all_entities(input_paths)
    source_snapshots = _load_source_snapshots_by_source(source_snapshot_paths)
    provider_runs = _load_provider_runs_by_source(provider_run_paths)
    snapshot_ids = {
        source_id: _source_snapshot_id_for_source(
            source_id,
            source_snapshots=source_snapshots,
            source_snapshot_ids=source_snapshot_ids,
        )
        for source_id in _source_ids(entities)
    }
    provider_run_ids = {
        source_id: _provider_run_id_for_source(
            source_id,
            source_snapshot_id=snapshot_ids[source_id],
            provider_runs=provider_runs,
        )
        for source_id in _source_ids(entities)
    }
    frames = _build_frames(
        entities,
        source_snapshot_ids=snapshot_ids,
        provider_run_ids=provider_run_ids,
        source_snapshots=source_snapshots,
        provider_runs=provider_runs,
    )
    source_ids = _source_ids(entities)
    validation = validate_artifact_inputs(
        _artifact_inputs(frames.keys(), source_ids=source_ids),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, object]] = []
    tables: list[dict[str, object]] = []
    table_contracts = {**CORE_TABLE_CONTRACTS, **PROFILE_TABLE_CONTRACTS}
    policy_versions = _contract_policy_versions()

    for table_name, frame in frames.items():
        table_path = output_dir / f"{table_name}.parquet"
        frame.write_parquet(table_path, compression="zstd")
        contract = table_contracts[table_name]
        files.append(
            {
                "path": table_path.name,
                "format": "parquet",
                "compression": "zstd",
                "kind": table_name,
            }
        )
        tables.append(
            {
                "table_name": table_name,
                "path": table_path.name,
                "format": "parquet",
                "row_count": frame.height,
                "schema_version": contract.schema_version,
                "compatibility_tier": contract.compatibility_tier.value,
                "policy_versions": policy_versions,
                "recipe_versions": {"normalization": V1_RECIPE_VERSION},
                "enrichment_status": _table_enrichment_status(table_name),
            }
        )

    manifest_path = output_dir / "media-metadata-v1-manifest.json"
    manifest = {
        **artifact_manifest_metadata(artifact=V1_ARTIFACT, build_stage=V1_BUILD_STAGE),
        "dataset_line": "media-metadata-v1",
        "dataset_version": __version__,
        "core_schema_version": CORE_SCHEMA_VERSION,
        "hf_repo_id": "local/media-metadata-dataset",
        "policy_versions": policy_versions,
        "recipe_versions": {"normalization": V1_RECIPE_VERSION},
        "confidence_recipe_versions": {"relationships": RELATIONSHIP_RECIPE_VERSION},
        "enrichment_status": {
            "snapshot": "source-ingested",
            "profiles": "source-derived",
            "facets": "source-derived",
            "embeddings": "missing",
            "judgments": "missing",
        },
        "source_coverage": _source_coverage(entities, snapshot_ids),
        "publishability": publishability_manifest_payload(
            [*validation.validated_uses, PublishableUse.PUBLIC_MANIFEST],
            input_count=validation.input_count,
        ),
        "row_count": len(entities),
        "entity_row_count": frames["entities"].height,
        "relationship_row_count": frames["relationships"].height,
        "domains": sorted({entity.domain for entity in entities}),
        "tables": tables,
        "files": files,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _load_all_entities(input_paths: Sequence[Path]) -> list[BootstrapEntity]:
    entities: list[BootstrapEntity] = []
    seen: set[str] = set()
    for input_path in input_paths:
        for entity in load_bootstrap_entities(input_path):
            if entity.entity_id in seen:
                continue
            seen.add(entity.entity_id)
            entities.append(entity)
    return sorted(entities, key=lambda entity: entity.entity_id)


def _load_source_snapshots_by_source(
    source_snapshot_paths: Sequence[Path] | None,
) -> dict[str, SourceSnapshot]:
    snapshots: dict[str, SourceSnapshot] = {}
    for path in source_snapshot_paths or []:
        for snapshot in load_source_snapshots(path):
            snapshots[snapshot.source_id] = snapshot
    return snapshots


def _load_provider_runs_by_source(
    provider_run_paths: Sequence[Path] | None,
) -> dict[str, ProviderRun]:
    provider_runs: dict[str, ProviderRun] = {}
    for path in provider_run_paths or []:
        for provider_run in load_provider_runs(path):
            provider_runs[provider_run.source_id] = provider_run
    return provider_runs


def _source_snapshot_id_for_source(
    source_id: str,
    *,
    source_snapshots: Mapping[str, SourceSnapshot],
    source_snapshot_ids: Mapping[str, str] | None,
) -> str:
    if source_id in source_snapshots:
        return source_snapshots[source_id].source_snapshot_id
    if source_snapshot_ids is not None:
        return source_snapshot_ids.get(source_id, f"{source_id}:unspecified")
    return f"{source_id}:unspecified"


def _provider_run_id_for_source(
    source_id: str,
    *,
    source_snapshot_id: str,
    provider_runs: Mapping[str, ProviderRun],
) -> str:
    if source_id in provider_runs:
        return provider_runs[source_id].provider_run_id
    return _provider_run_id(source_id, source_snapshot_id)


def _build_frames(
    entities: Sequence[BootstrapEntity],
    *,
    source_snapshot_ids: Mapping[str, str],
    provider_run_ids: Mapping[str, str],
    source_snapshots: Mapping[str, SourceSnapshot],
    provider_runs: Mapping[str, ProviderRun],
) -> dict[str, pl.DataFrame]:
    provenance_by_entity = {
        entity.entity_id: _provenance_id(_policy_source_id(entity.record_source), entity.entity_id)
        for entity in entities
    }
    frames = {
        "entities": _frame("entities", _entity_rows(entities, provenance_by_entity)),
        "titles": _frame("titles", _title_rows(entities, provenance_by_entity)),
        "external_ids": _frame("external_ids", _external_id_rows(entities, provenance_by_entity)),
        "relationships": _frame("relationships", _relationship_rows(entities, provenance_by_entity)),
        "relationship_evidence": _frame(
            "relationship_evidence", _relationship_evidence_rows(entities, provenance_by_entity)
        ),
        "facets": _frame("facets", _facet_rows(entities, provenance_by_entity)),
        "provenance": _frame(
            "provenance",
            _provenance_rows(
                entities,
                provenance_by_entity,
                source_snapshot_ids,
                provider_run_ids,
            ),
        ),
        "source_snapshots": _frame(
            "source_snapshots",
            _source_snapshot_rows(entities, source_snapshot_ids, source_snapshots),
        ),
        "provider_runs": _frame(
            "provider_runs",
            _provider_run_rows(entities, source_snapshot_ids, provider_runs),
        ),
        "source_records": _frame(
            "source_records",
            _source_record_rows(
                entities,
                provenance_by_entity,
                source_snapshot_ids,
                provider_run_ids,
            ),
        ),
        "anime_profile": _frame("anime_profile", _anime_profile_rows(entities, provenance_by_entity)),
        "tv_profile": _frame("tv_profile", _tv_profile_rows(entities, provenance_by_entity)),
        "movie_profile": _frame("movie_profile", _movie_profile_rows(entities, provenance_by_entity)),
    }
    return frames


def _entity_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
) -> list[dict[str, object]]:
    return [
        {
            "entity_id": entity.entity_id,
            "domain": entity.domain,
            "media_type": entity.media_type,
            "status": entity.status,
            "release_year": None if entity.release_year == 0 else entity.release_year,
            "release_date": None,
            "confidence_tier": "high",
            "evidence_count": max(1, len(entity.sources)),
            "conflict_status": "none",
            "quality_flags": ["source_backed"],
            "evidence_id": _evidence_id(entity.entity_id),
            "provenance_id": provenance_by_entity[entity.entity_id],
            "recipe_version": V1_RECIPE_VERSION,
            "manifest_table_name": "entities",
        }
        for entity in entities
    ]


def _title_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entity in entities:
        title_values = [("canonical", entity.title)]
        if entity.original_title and entity.original_title != entity.title:
            title_values.append(("original", entity.original_title))
        title_values.extend(("alias", synonym) for synonym in entity.synonyms if synonym != entity.title)
        seen: set[tuple[str, str]] = set()
        for title_type, title in title_values:
            key = (title_type, title)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "title_id": _stable_id("title", entity.entity_id, title_type, title),
                    "entity_id": entity.entity_id,
                    "title": title,
                    "title_type": title_type,
                    "language": None,
                    "script": None,
                    "source_id": _policy_source_id(entity.record_source),
                    "evidence_id": _evidence_id(entity.entity_id),
                    "provenance_id": provenance_by_entity[entity.entity_id],
                    "confidence_tier": "high" if title_type == "canonical" else "medium",
                    "quality_flags": ["source_backed"],
                    "recipe_version": V1_RECIPE_VERSION,
                }
            )
    return rows


def _external_id_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entity in entities:
        external_id = entity.entity_id.rsplit(":", maxsplit=1)[-1]
        rows.append(
            {
                "external_id_row_id": _stable_id("external-id", entity.entity_id, entity.record_source),
                "entity_id": entity.entity_id,
                "source_id": _policy_source_id(entity.record_source),
                "source_role": entity.source_role.value,
                "external_id": external_id,
                "url": entity.canonical_source,
                "provenance_id": provenance_by_entity[entity.entity_id],
                "recipe_version": V1_RECIPE_VERSION,
            }
        )
    return rows


def _relationship_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entity in entities:
        for edge in entity.related:
            relationship_id = _stable_id(
                "relationship", entity.entity_id, edge.relationship, edge.target
            )
            rows.append(
                {
                    "relationship_id": relationship_id,
                    "source_entity_id": entity.entity_id,
                    "target_entity_id": edge.target,
                    "relationship_type": edge.relationship,
                    "relationship_family": relationship_family(edge.relationship),
                    "direction": relationship_direction(edge.relationship),
                    "inverse_relationship_type": inverse_relationship(edge.relationship),
                    "confidence_tier": "medium",
                    "evidence_count": max(1, len(edge.supporting_urls)),
                    "conflict_status": "none",
                    "quality_flags": ["source_backed", "deterministic_recipe"],
                    "evidence_id": _stable_id("relationship-evidence", relationship_id),
                    "provenance_id": provenance_by_entity[entity.entity_id],
                    "recipe_version": RELATIONSHIP_RECIPE_VERSION,
                }
            )
    return rows


def _relationship_evidence_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entity in entities:
        for edge in entity.related:
            relationship_id = _stable_id(
                "relationship", entity.entity_id, edge.relationship, edge.target
            )
            evidence_id = _stable_id("relationship-evidence", relationship_id)
            rows.append(
                {
                    "relationship_evidence_id": evidence_id,
                    "relationship_id": relationship_id,
                    "evidence_id": evidence_id,
                    "source_id": _policy_source_id(entity.record_source),
                    "source_record_id": entity.entity_id,
                    "evidence_strength": "source_backed",
                    "claim": edge.relationship,
                    "provenance_id": provenance_by_entity[entity.entity_id],
                    "recipe_version": V1_RECIPE_VERSION,
                }
            )
    return rows


def _facet_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entity in entities:
        for namespace, values in {
            "genre": entity.genres,
            "studio": entity.studios,
            "creator": entity.creators,
            "tag": entity.tags,
        }.items():
            for value in values:
                rows.append(
                    {
                        "facet_id": _stable_id("facet", entity.entity_id, namespace, value),
                        "entity_id": entity.entity_id,
                        "facet_namespace": namespace,
                        "facet_key": _facet_key(value),
                        "facet_value": value,
                        "confidence_tier": "medium",
                        "evidence_id": _evidence_id(entity.entity_id),
                        "provenance_id": provenance_by_entity[entity.entity_id],
                        "recipe_version": V1_RECIPE_VERSION,
                    }
                )
    return rows


def _provenance_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
    source_snapshot_ids: Mapping[str, str],
    provider_run_ids: Mapping[str, str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entity in entities:
        rows.append(
            {
                "provenance_id": provenance_by_entity[entity.entity_id],
                "source_id": _policy_source_id(entity.record_source),
                "source_snapshot_id": source_snapshot_ids[_policy_source_id(entity.record_source)],
                "provider_run_id": provider_run_ids[_policy_source_id(entity.record_source)],
                "recipe_run_id": V1_RECIPE_VERSION,
                "policy_version": SOURCE_POLICY_VERSION,
            }
        )
    return rows


def _source_snapshot_rows(
    entities: Sequence[BootstrapEntity],
    source_snapshot_ids: Mapping[str, str],
    source_snapshots: Mapping[str, SourceSnapshot],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source_id, source_entities in _entities_by_source(entities).items():
        if source_id in source_snapshots:
            rows.append(_source_snapshot_model_row(source_snapshots[source_id]))
            continue
        snapshot_id = source_snapshot_ids[source_id]
        fetched_at = _snapshot_datetime(snapshot_id)
        rows.append(
            {
                "source_snapshot_id": snapshot_id,
                "source_id": source_id,
                "source_role": source_entities[0].source_role.value,
                "snapshot_kind": _snapshot_kind(source_id),
                "fetched_at": fetched_at,
                "source_published_at": fetched_at if source_id == "manami" else None,
                "fetch_window_started_at": None if source_id == "manami" else fetched_at,
                "fetch_window_finished_at": None if source_id == "manami" else fetched_at,
                "source_version": snapshot_id,
                "policy_version": SOURCE_POLICY_VERSION,
                "publishable_field_policy_version": SOURCE_FIELD_POLICY_VERSION,
                "artifact_policy_version": ARTIFACT_POLICY_VERSION,
                "record_count": len(source_entities),
                "content_hash": _source_content_hash(source_entities),
                "manifest_uri": None,
                "notes": "Generated by v1 artifact writer from normalized source-backed rows.",
            }
        )
    return rows


def _provider_run_rows(
    entities: Sequence[BootstrapEntity],
    source_snapshot_ids: Mapping[str, str],
    provider_runs: Mapping[str, ProviderRun],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source_id, source_entities in _entities_by_source(entities).items():
        if source_id in provider_runs:
            rows.append(_provider_run_model_row(provider_runs[source_id]))
            continue
        snapshot_id = source_snapshot_ids[source_id]
        run_at = _snapshot_datetime(snapshot_id)
        rows.append(
            {
                "provider_run_id": _provider_run_id(source_id, snapshot_id),
                "source_id": source_id,
                "source_snapshot_id": snapshot_id,
                "adapter_name": _adapter_name(source_id),
                "adapter_version": _adapter_version(source_id),
                "started_at": run_at,
                "finished_at": run_at,
                "request_count": _request_count(source_id, source_entities),
                "cache_hit_count": 0,
                "status": "completed",
                "auth_shape": "none",
                "secret_refs": [],
                "notes": "No secret values or restricted payloads are stored in provider run metadata.",
            }
        )
    return rows


def _source_record_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
    source_snapshot_ids: Mapping[str, str],
    provider_run_ids: Mapping[str, str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entity in entities:
        source_record_id = entity.entity_id
        rows.append(
            {
                "source_record_ref_id": _stable_id("source-record", entity.record_source, source_record_id),
                "entity_id": entity.entity_id,
                "source_id": _policy_source_id(entity.record_source),
                "source_record_id": source_record_id,
                "source_snapshot_id": source_snapshot_ids[_policy_source_id(entity.record_source)],
                "provider_run_id": provider_run_ids[_policy_source_id(entity.record_source)],
                "source_role": entity.source_role.value,
                "source_url": entity.canonical_source,
                "source_record_hash": _stable_hash(entity.model_dump_json()),
                "provenance_id": provenance_by_entity[entity.entity_id],
                "recipe_version": V1_RECIPE_VERSION,
            }
        )
    return rows


def _anime_profile_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
) -> list[dict[str, object]]:
    return [
        {
            "entity_id": entity.entity_id,
            "profile_schema_version": PROFILE_TABLE_CONTRACTS["anime_profile"].schema_version,
            "anime_format": entity.media_type,
            "anime_season": None,
            "anime_season_year": entity.release_year or None,
            "cour_count": None,
            "episode_count": entity.episodes,
            "source_demographic": None,
            "anime_relationship_hints": sorted({edge.relationship for edge in entity.related}),
            "provenance_id": provenance_by_entity[entity.entity_id],
            "recipe_version": V1_RECIPE_VERSION,
        }
        for entity in entities
        if entity.domain == "anime"
    ]


def _tv_profile_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
) -> list[dict[str, object]]:
    return [
        {
            "entity_id": entity.entity_id,
            "profile_schema_version": PROFILE_TABLE_CONTRACTS["tv_profile"].schema_version,
            "season_count": None,
            "episode_count": entity.episodes,
            "show_status": entity.status,
            "network_or_platform": _tag_value(entity.tags, "network:"),
            "release_shape": entity.media_type,
            "provenance_id": provenance_by_entity[entity.entity_id],
            "recipe_version": V1_RECIPE_VERSION,
        }
        for entity in entities
        if entity.domain == "tv"
    ]


def _movie_profile_rows(
    entities: Sequence[BootstrapEntity],
    provenance_by_entity: Mapping[str, str],
) -> list[dict[str, object]]:
    return [
        {
            "entity_id": entity.entity_id,
            "profile_schema_version": PROFILE_TABLE_CONTRACTS["movie_profile"].schema_version,
            "runtime_minutes": None,
            "release_year": entity.release_year or None,
            "release_date": None,
            "collection_id": None,
            "franchise_hint": _tag_value(entity.tags, "franchise:"),
            "release_shape": entity.media_type,
            "provenance_id": provenance_by_entity[entity.entity_id],
            "recipe_version": V1_RECIPE_VERSION,
        }
        for entity in entities
        if entity.domain == "movie"
    ]


def _frame(table_name: str, rows: list[dict[str, object]]) -> pl.DataFrame:
    contract = {**CORE_TABLE_CONTRACTS, **PROFILE_TABLE_CONTRACTS}[table_name]
    schema = {column.name: _polars_dtype(column.dtype) for column in contract.columns}
    if rows:
        return pl.DataFrame(rows, schema=schema)
    return pl.DataFrame(schema=schema)


def _polars_dtype(dtype: str) -> pl.DataType:
    match dtype:
        case "string":
            return pl.String()
        case "int64":
            return pl.Int64()
        case "datetime":
            return pl.Datetime(time_zone="UTC")
        case "date":
            return pl.Date()
        case "list[string]":
            return pl.List(pl.String())
        case _:
            raise ValueError(f"unsupported contract dtype: {dtype}")


def _artifact_inputs(
    table_names: Iterable[str],
    *,
    source_ids: Sequence[str],
) -> list[ArtifactInput]:
    contracts = {**CORE_TABLE_CONTRACTS, **PROFILE_TABLE_CONTRACTS}
    inputs: list[ArtifactInput] = []
    for table_name in table_names:
        for column in contracts[table_name].columns:
            inputs.append(
                ArtifactInput(
                    artifact=V1_ARTIFACT,
                    table=table_name,
                    column=column.name,
                    source_fields=[
                        SourceFieldReference(
                            source_id=source_id,
                            field_name=_source_field_for_column(table_name, column.name),
                        )
                        for source_id in source_ids
                    ],
                    use=PublishableUse.PUBLIC_PARQUET,
                )
            )
    return inputs


def _source_field_for_column(table_name: str, column: str) -> str:
    if table_name == "relationships" or table_name == "relationship_evidence":
        return "relationship_type"
    if column in {"title", "title_type"}:
        return "title"
    if column in {"source_url", "url", "source_record_hash"}:
        return "sources"
    if column in {"source_role", "source_id"}:
        return "source_role"
    if column in {"domain", "media_type", "status", "release_year", "episodes"}:
        return column
    if column in {"genre", "genres", "facet_value", "facet_key", "facet_namespace"}:
        return "genres"
    if column in {"creators", "creator"}:
        return "creators"
    return "entity_id"


def _source_coverage(
    entities: Sequence[BootstrapEntity],
    source_snapshot_ids: Mapping[str, str],
) -> list[dict[str, object]]:
    grouped: dict[str, list[BootstrapEntity]] = defaultdict(list)
    for entity in entities:
        grouped[_policy_source_id(entity.record_source)].append(entity)
    rows: list[dict[str, object]] = []
    for source_id, source_entities in sorted(grouped.items()):
        rows.append(
            {
                "source_id": source_id,
                "source_role": source_entities[0].source_role.value,
                "source_snapshot_id": source_snapshot_ids[source_id],
                "domains": sorted({entity.domain for entity in source_entities}),
                "record_count": len(source_entities),
            }
        )
    return rows


def _contract_policy_versions() -> dict[str, str]:
    return {
        "source_policy_version": SOURCE_POLICY_VERSION,
        "field_policy_version": SOURCE_FIELD_POLICY_VERSION,
        "artifact_policy_version": ARTIFACT_POLICY_VERSION,
        "publishability_validation_version": PUBLISHABILITY_POLICY_VERSION,
    }


def _table_enrichment_status(table_name: str) -> str:
    if table_name in {"source_snapshots", "provider_runs"}:
        return "source-metadata"
    if table_name in {"anime_profile", "tv_profile", "movie_profile", "facets"}:
        return "source-derived"
    return "source-ingested"


def _entities_by_source(entities: Sequence[BootstrapEntity]) -> dict[str, list[BootstrapEntity]]:
    grouped: dict[str, list[BootstrapEntity]] = defaultdict(list)
    for entity in entities:
        grouped[_policy_source_id(entity.record_source)].append(entity)
    return dict(sorted(grouped.items()))


def _source_ids(entities: Sequence[BootstrapEntity]) -> list[str]:
    return sorted({_policy_source_id(entity.record_source) for entity in entities}) or ["bootstrap_seed"]


def _policy_source_id(record_source: str) -> str:
    if record_source.startswith("manami-project/anime-offline-database"):
        return "manami"
    return record_source


def _stable_id(*parts: object) -> str:
    return ":".join(str(part) for part in parts[:-1]) + ":" + _stable_hash(str(parts[-1]))


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _stable_full_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _provenance_id(source_id: str, entity_id: str) -> str:
    return _stable_id("provenance", source_id, entity_id)


def _evidence_id(entity_id: str) -> str:
    return _stable_id("evidence", entity_id)


def _facet_key(value: str) -> str:
    return value.strip().casefold().replace(" ", "_")


def _tag_value(tags: Sequence[str], prefix: str) -> str | None:
    for tag in tags:
        if tag.startswith(prefix):
            return tag.removeprefix(prefix)
    return None


def _provider_run_id(source_id: str, source_snapshot_id: str) -> str:
    return _stable_id("provider-run", source_id, source_snapshot_id, V1_RECIPE_VERSION)


def _snapshot_datetime(source_snapshot_id: str) -> datetime:
    date_part = source_snapshot_id.rsplit(":", maxsplit=1)[-1]
    try:
        return datetime.fromisoformat(date_part).replace(tzinfo=UTC)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=UTC)


def _snapshot_kind(source_id: str) -> str:
    if source_id == "manami":
        return "release_file"
    if source_id == "wikidata":
        return "sparql_query_window"
    return "api_fetch_window"


def _adapter_name(source_id: str) -> str:
    return {
        "manami": "manami-release-normalizer",
        "tvmaze": "tvmaze-show-normalizer",
        "wikidata": "wikidata-movie-normalizer",
    }.get(source_id, f"{source_id}-normalizer")


def _adapter_version(source_id: str) -> str:
    return {
        "manami": "manami-bootstrap-v1",
        "tvmaze": "tvmaze-bootstrap-v1",
        "wikidata": "wikidata-movie-bootstrap-v1",
    }.get(source_id, V1_RECIPE_VERSION)


def _request_count(source_id: str, entities: Sequence[BootstrapEntity]) -> int:
    if source_id == "manami":
        return 0
    return len(entities)


def _source_content_hash(entities: Sequence[BootstrapEntity]) -> str:
    payload = "\n".join(
        entity.model_dump_json() for entity in sorted(entities, key=lambda item: item.entity_id)
    )
    return _stable_full_hash(payload)


def _source_snapshot_model_row(snapshot: SourceSnapshot) -> dict[str, object]:
    row = snapshot.model_dump(mode="python")
    row["source_role"] = snapshot.source_role.value
    return row


def _provider_run_model_row(provider_run: ProviderRun) -> dict[str, object]:
    row = provider_run.model_dump(mode="python")
    row["secret_refs"] = list(provider_run.secret_refs)
    return row
