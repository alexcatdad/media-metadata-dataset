from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from media_offline_database.cli import app
from media_offline_database.refresh_state import RefreshState
from media_offline_database.snapshot_finalize import (
    materialize_current_snapshot,
    publish_current_snapshot,
)

runner = CliRunner()
COMMIT_SHA = "fedcba0987654321fedcba0987654321fedcba09"


class FakeCommitInfo:
    def __init__(self, commit_url: str | None = None, oid: str | None = None) -> None:
        self.commit_url = commit_url
        self.oid = oid


class FakeHfApi:
    def __init__(self) -> None:
        self.created_repos: list[dict[str, object]] = []
        self.uploaded_folders: list[dict[str, object]] = []
        self.uploaded_files: list[dict[str, object]] = []
        self.created_tags: list[dict[str, object]] = []

    def create_repo(
        self,
        repo_id: str,
        *,
        token: str | bool | None = None,
        private: bool | None = None,
        repo_type: str | None = None,
        exist_ok: bool = False,
    ) -> object:
        self.created_repos.append(
            {
                "repo_id": repo_id,
                "token": token,
                "private": private,
                "repo_type": repo_type,
                "exist_ok": exist_ok,
            }
        )
        return object()

    def whoami(
        self,
        token: bool | str | None = None,
        *,
        cache: bool = False,
    ) -> dict[str, object]:
        _ = token, cache
        return {"name": "alecatdad"}

    def upload_folder(self, **kwargs: object) -> FakeCommitInfo:
        self.uploaded_folders.append(dict(kwargs))
        return FakeCommitInfo(f"https://huggingface.co/commit/{COMMIT_SHA}", COMMIT_SHA)

    def upload_file(self, **kwargs: object) -> FakeCommitInfo:
        self.uploaded_files.append(dict(kwargs))
        return FakeCommitInfo()

    def create_tag(self, **kwargs: object) -> object:
        self.created_tags.append(dict(kwargs))
        return object()


def _write_manifest_bundle(tmp_path: Path) -> Path:
    artifact_dir = tmp_path / "compiled"
    artifact_dir.mkdir(parents=True)
    entities_path = artifact_dir / "sample-entities.parquet"
    relationships_path = artifact_dir / "sample-relationships.parquet"
    entities_path.write_bytes(b"entities")
    relationships_path.write_bytes(b"relationships")
    manifest_path = artifact_dir / "sample-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "artifact": "bootstrap-corpus",
                "files": [
                    {"path": entities_path.name, "kind": "entities"},
                    {"path": relationships_path.name, "kind": "relationships"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_materialize_current_snapshot_copies_bundle_to_snapshot_and_current(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest_bundle(tmp_path)

    result = materialize_current_snapshot(
        manifest_path=manifest_path,
        output_dir=tmp_path / "finalized",
        job_name="anime.manami.default",
        snapshot_id="2026-14",
    )

    snapshot_dir = tmp_path / "finalized" / "snapshots" / "anime.manami.default" / "2026-14"
    current_dir = tmp_path / "finalized" / "current" / "anime.manami.default"

    assert result.snapshot_path == "snapshots/anime.manami.default/2026-14"
    assert result.current_path == "current/anime.manami.default"
    assert (snapshot_dir / "sample-manifest.json").exists()
    assert (snapshot_dir / "sample-entities.parquet").read_bytes() == b"entities"
    assert (current_dir / "sample-manifest.json").exists()
    assert (current_dir / "sample-relationships.parquet").read_bytes() == b"relationships"


def test_publish_current_snapshot_uploads_snapshot_current_and_updates_state(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest_bundle(tmp_path)
    fake_api = FakeHfApi()
    state = RefreshState()

    result = publish_current_snapshot(
        api=fake_api,
        token="hf_test",
        repo_id="alecatdad/media-metadata-dataset-test",
        manifest_path=manifest_path,
        state=state,
        job_name="anime.manami.default",
        snapshot_id="2026-14",
        private=True,
    )

    assert len(fake_api.uploaded_folders) == 2
    assert fake_api.uploaded_folders[0]["path_in_repo"] == "snapshots/anime.manami.default/2026-14"
    assert fake_api.uploaded_folders[1]["path_in_repo"] == "current/anime.manami.default"
    assert [entry["path_in_repo"] for entry in fake_api.uploaded_files] == [
        "README.md",
        "snapshots/anime.manami.default/2026-14/sample-manifest.json",
        "current/anime.manami.default/sample-manifest.json",
        "state/refresh-state.json",
    ]
    assert result.snapshot_manifest_path == (
        "snapshots/anime.manami.default/2026-14/sample-manifest.json"
    )
    assert result.current_manifest_path == (
        "current/anime.manami.default/sample-manifest.json"
    )
    assert result.commit_sha == COMMIT_SHA

    state_bytes = fake_api.uploaded_files[3]["path_or_fileobj"]
    assert isinstance(state_bytes, bytes)
    state_payload = json.loads(state_bytes.decode("utf-8"))
    job = state_payload["jobs"]["anime.manami.default"]
    assert job["status"] == "completed"
    assert job["published_snapshot_path"] == "snapshots/anime.manami.default/2026-14"
    assert job["current_snapshot_path"] == "current/anime.manami.default"


def test_publish_current_snapshot_can_create_release_tag(tmp_path: Path) -> None:
    manifest_path = _write_manifest_bundle(tmp_path)
    fake_api = FakeHfApi()

    result = publish_current_snapshot(
        api=fake_api,
        token="hf_test",
        repo_id="alecatdad/media-metadata-dataset-test",
        manifest_path=manifest_path,
        state=RefreshState(),
        job_name="anime.manami.default",
        snapshot_id="2026-14",
        private=True,
        release_tag="v0.1.0",
    )

    assert result.release_tag == "v0.1.0"
    assert fake_api.created_tags == [
        {
            "repo_id": "alecatdad/media-metadata-dataset-test",
            "tag": "v0.1.0",
            "revision": COMMIT_SHA,
            "tag_message": "Release snapshot v0.1.0",
            "token": "hf_test",
            "repo_type": "dataset",
        }
    ]


def test_materialize_current_snapshot_surface_cli(tmp_path: Path) -> None:
    manifest_path = _write_manifest_bundle(tmp_path)
    output_dir = tmp_path / "cli-finalized"

    result = runner.invoke(
        app,
        [
            "materialize-current-snapshot-surface",
            str(manifest_path),
            "--snapshot-id",
            "2026-14",
            "--job-name",
            "anime.manami.default",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (output_dir / "current" / "anime.manami.default" / "sample-manifest.json").exists()
