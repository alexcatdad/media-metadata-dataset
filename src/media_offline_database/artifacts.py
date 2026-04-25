from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from media_offline_database import __version__

ARTIFACT_MANIFEST_SCHEMA = "media-offline-dataset.artifact-manifest"
ARTIFACT_MANIFEST_SCHEMA_VERSION = 1
ARTIFACT_VERSION = 1


def artifact_manifest_metadata(*, artifact: str, build_stage: str) -> dict[str, Any]:
    return {
        "artifact": artifact,
        "artifact_version": ARTIFACT_VERSION,
        "build_stage": build_stage,
        "created_at": datetime.now(UTC).isoformat(),
        "generator_version": __version__,
        "manifest_schema": ARTIFACT_MANIFEST_SCHEMA,
        "manifest_schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
    }


def write_keyless_smoke_artifact(output_dir: Path) -> Path:
    """Write a tiny dataset artifact without network access or credentials."""

    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "keyless-smoke.parquet"
    manifest_path = output_dir / "keyless-smoke-manifest.json"

    frame = pl.DataFrame(
        {
            "entity_id": ["anime:smoke:1", "tv:smoke:1", "movie:smoke:1"],
            "domain": ["anime", "tv", "movie"],
            "title": ["Smoke Anime", "Smoke TV", "Smoke Movie"],
            "source_role": ["BACKBONE_SOURCE", "BACKBONE_SOURCE", "ID_SOURCE"],
        }
    )
    frame.write_parquet(dataset_path, compression="zstd")

    manifest: dict[str, Any] = {
        **artifact_manifest_metadata(
            artifact="keyless-smoke",
            build_stage="keyless-smoke",
        ),
        "row_count": frame.height,
        "files": [
            {
                "path": dataset_path.name,
                "format": "parquet",
                "compression": "zstd",
            }
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path
