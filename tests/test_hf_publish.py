from __future__ import annotations

import json
from pathlib import Path

import pytest

from media_offline_database.hf_publish import (
    HF_REFRESH_STATE_PATH,
    build_publish_bundle,
    publish_checkpoint_bundle,
    resolve_hf_repo_id,
)
from media_offline_database.publishability import PublishableUse, publishability_manifest_payload
from media_offline_database.refresh_state import RefreshState
from media_offline_database.release_readiness import ReleaseReadinessError
from media_offline_database.settings import Settings

BUNDLE_COMMIT_SHA = "1234567890abcdef1234567890abcdef12345678"
FINAL_COMMIT_SHA = "abcdef1234567890abcdef1234567890abcdef12"


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

    def upload_folder(
        self,
        *,
        repo_id: str,
        folder_path: str | Path,
        path_in_repo: str | None = None,
        commit_message: str | None = None,
        token: str | bool | None = None,
        repo_type: str | None = None,
        allow_patterns: list[str] | str | None = None,
        ignore_patterns: list[str] | str | None = None,
    ) -> FakeCommitInfo:
        self.uploaded_folders.append(
            {
                "repo_id": repo_id,
                "folder_path": Path(folder_path),
                "path_in_repo": path_in_repo,
                "commit_message": commit_message,
                "token": token,
                "repo_type": repo_type,
                "allow_patterns": allow_patterns,
                "ignore_patterns": ignore_patterns,
            }
        )
        return FakeCommitInfo(
            f"https://huggingface.co/commit/{BUNDLE_COMMIT_SHA}",
            BUNDLE_COMMIT_SHA,
        )

    def upload_file(
        self,
        *,
        path_or_fileobj: str | Path | bytes,
        path_in_repo: str,
        repo_id: str,
        token: str | bool | None = None,
        repo_type: str | None = None,
        commit_message: str | None = None,
    ) -> FakeCommitInfo:
        self.uploaded_files.append(
            {
                "path_or_fileobj": path_or_fileobj,
                "path_in_repo": path_in_repo,
                "repo_id": repo_id,
                "token": token,
                "repo_type": repo_type,
                "commit_message": commit_message,
            }
        )
        return FakeCommitInfo(
            f"https://huggingface.co/commit/{FINAL_COMMIT_SHA}",
            FINAL_COMMIT_SHA,
        )

    def create_tag(
        self,
        *,
        repo_id: str,
        tag: str,
        revision: str | None = None,
        tag_message: str | None = None,
        token: str | bool | None = None,
        repo_type: str | None = None,
    ) -> object:
        self.created_tags.append(
            {
                "repo_id": repo_id,
                "tag": tag,
                "revision": revision,
                "tag_message": tag_message,
                "token": token,
                "repo_type": repo_type,
            }
        )
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
                "publishability": publishability_manifest_payload(
                    [PublishableUse.PUBLIC_PARQUET, PublishableUse.PUBLIC_MANIFEST],
                    input_count=2,
                ),
                "files": [
                    {"path": entities_path.name, "kind": "entities"},
                    {"path": relationships_path.name, "kind": "relationships"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_build_publish_bundle_collects_manifest_files(tmp_path: Path) -> None:
    manifest_path = _write_manifest_bundle(tmp_path)

    bundle = build_publish_bundle(manifest_path)

    assert bundle.manifest_path == manifest_path
    assert bundle.local_dir == manifest_path.parent
    assert bundle.allow_patterns == [
        "sample-manifest.json",
        "sample-entities.parquet",
        "sample-relationships.parquet",
    ]


def test_build_publish_bundle_rejects_unready_v1_manifest(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "compiled"
    artifact_dir.mkdir(parents=True)
    manifest_path = artifact_dir / "media-metadata-v1-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "artifact": "media-metadata-v1",
                "dataset_line": "media-metadata-v1",
                "dataset_version": "0.1.0",
                "core_schema_version": "core.v1",
                "domains": ["anime"],
                "source_coverage": [],
                "publishability": publishability_manifest_payload(
                    [PublishableUse.PUBLIC_PARQUET, PublishableUse.PUBLIC_MANIFEST],
                    input_count=0,
                ),
                "files": [],
                "tables": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReleaseReadinessError, match="required_domains_missing"):
        build_publish_bundle(manifest_path)


def test_resolve_hf_repo_id_prefers_explicit_then_settings_then_whoami() -> None:
    fake_api = FakeHfApi()
    settings = Settings.model_validate(
        {
            "HF_TOKEN": "hf_test",
            "HF_NAMESPACE": "alecatdad",
            "HF_DATASET_REPO": "media-metadata-dataset-test",
        }
    )

    assert resolve_hf_repo_id(
        settings=settings,
        api=fake_api,
        token="hf_test",
        repo_id="custom/repo",
    ) == "custom/repo"
    assert resolve_hf_repo_id(
        settings=settings,
        api=fake_api,
        token="hf_test",
    ) == "alecatdad/media-metadata-dataset-test"

    fallback_settings = Settings.model_validate({"HF_TOKEN": "hf_test"})
    assert resolve_hf_repo_id(
        settings=fallback_settings,
        api=fake_api,
        token="hf_test",
    ) == "alecatdad/media-metadata-dataset"

    empty_var_settings = Settings.model_validate(
        {
            "HF_TOKEN": "hf_test",
            "HF_NAMESPACE": "",
            "HF_DATASET_REPO": "",
        }
    )
    assert resolve_hf_repo_id(
        settings=empty_var_settings,
        api=fake_api,
        token="hf_test",
    ) == "alecatdad/media-metadata-dataset"


def test_publish_checkpoint_bundle_uploads_artifact_and_state(tmp_path: Path) -> None:
    fake_api = FakeHfApi()
    manifest_path = _write_manifest_bundle(tmp_path)
    state = RefreshState()

    result = publish_checkpoint_bundle(
        api=fake_api,
        token="hf_test",
        repo_id="alecatdad/media-metadata-dataset-test",
        manifest_path=manifest_path,
        checkpoint_path="checkpoints/anime.manami.default/2026-14/00000000-00000100",
        state=state,
        private=True,
    )

    assert fake_api.created_repos == [
        {
            "repo_id": "alecatdad/media-metadata-dataset-test",
            "token": "hf_test",
            "private": True,
            "repo_type": "dataset",
            "exist_ok": True,
        }
    ]
    assert len(fake_api.uploaded_folders) == 1
    assert fake_api.uploaded_folders[0]["path_in_repo"] == (
        "checkpoints/anime.manami.default/2026-14/00000000-00000100"
    )
    assert fake_api.uploaded_folders[0]["allow_patterns"] == [
        "sample-manifest.json",
        "sample-entities.parquet",
        "sample-relationships.parquet",
    ]
    assert [entry["path_in_repo"] for entry in fake_api.uploaded_files] == [
        "README.md",
        HF_REFRESH_STATE_PATH,
    ]
    assert result.repo_id == "alecatdad/media-metadata-dataset-test"
    assert result.state_path == HF_REFRESH_STATE_PATH
    assert result.bundle_commit_sha == BUNDLE_COMMIT_SHA
    assert result.commit_sha == FINAL_COMMIT_SHA
    assert result.commit_url == f"https://huggingface.co/commit/{FINAL_COMMIT_SHA}"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "huggingface" not in manifest


def test_publish_checkpoint_bundle_can_create_release_tag(tmp_path: Path) -> None:
    fake_api = FakeHfApi()
    manifest_path = _write_manifest_bundle(tmp_path)

    result = publish_checkpoint_bundle(
        api=fake_api,
        token="hf_test",
        repo_id="alecatdad/media-metadata-dataset-test",
        manifest_path=manifest_path,
        checkpoint_path="checkpoints/manual",
        state=RefreshState(),
        private=True,
        release_tag="v0.1.0",
    )

    assert result.release_tag == "v0.1.0"
    assert fake_api.created_tags == [
        {
            "repo_id": "alecatdad/media-metadata-dataset-test",
            "tag": "v0.1.0",
            "revision": FINAL_COMMIT_SHA,
            "tag_message": "Release snapshot v0.1.0",
            "token": "hf_test",
            "repo_type": "dataset",
        }
    ]
