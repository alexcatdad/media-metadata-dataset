from __future__ import annotations

import json
from pathlib import Path

import duckdb

from media_offline_database.artifacts import write_keyless_smoke_artifact


def test_keyless_smoke_artifact_round_trips_through_duckdb(tmp_path: Path) -> None:
    manifest_path = write_keyless_smoke_artifact(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parquet_path = tmp_path / manifest["files"][0]["path"]

    row_count = duckdb.sql(
        "select count(*) from read_parquet(?)",
        params=[str(parquet_path)],
    ).fetchone()

    assert manifest["row_count"] == 3
    assert row_count == (3,)
    assert parquet_path.exists()
    assert parquet_path.stat().st_size > 0
