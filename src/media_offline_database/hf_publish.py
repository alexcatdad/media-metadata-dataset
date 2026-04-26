from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from huggingface_hub import HfApi, hf_hub_download  # pyright: ignore[reportUnknownVariableType]
from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError
from pydantic import BaseModel, ConfigDict

from media_offline_database.publishability import validate_current_manifest_publishability
from media_offline_database.refresh_state import RefreshState
from media_offline_database.settings import Settings

HF_REFRESH_STATE_PATH = "state/refresh-state.json"
HF_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class HfCommitInfoLike(Protocol):
    @property
    def commit_url(self) -> str | None: ...

    @property
    def oid(self) -> str | None: ...


class HfApiLike(Protocol):
    def create_repo(
        self,
        repo_id: str,
        *,
        token: str | bool | None = None,
        private: bool | None = None,
        repo_type: str | None = None,
        exist_ok: bool = False,
    ) -> object: ...

    def whoami(
        self,
        token: bool | str | None = None,
        *,
        cache: bool = False,
    ) -> dict[str, object]: ...

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
    ) -> HfCommitInfoLike | object: ...

    def upload_file(
        self,
        *,
        path_or_fileobj: str | Path | bytes,
        path_in_repo: str,
        repo_id: str,
        token: str | bool | None = None,
        repo_type: str | None = None,
        commit_message: str | None = None,
    ) -> HfCommitInfoLike | object: ...

    def create_tag(
        self,
        *,
        repo_id: str,
        tag: str,
        revision: str | None = None,
        tag_message: str | None = None,
        token: str | bool | None = None,
        repo_type: str | None = None,
    ) -> object: ...


def _hf_whoami(api: HfApiLike, *, token: str | None) -> dict[str, object]:
    return api.whoami(token=token, cache=False)


class HfPublishResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_id: str
    checkpoint_path: str
    state_path: str
    commit_sha: str | None = None
    commit_url: str | None = None
    release_tag: str | None = None


@dataclass(frozen=True)
class PublishBundle:
    manifest_path: Path
    local_dir: Path
    allow_patterns: list[str]


def resolve_hf_repo_id(
    *,
    settings: Settings,
    api: HfApiLike | None = None,
    token: str | None = None,
    repo_id: str | None = None,
) -> str:
    if repo_id is not None:
        return repo_id

    repo_name = settings.hf_dataset_repo or "media-metadata-dataset"
    namespace = settings.hf_namespace or None
    if namespace is None:
        if api is None:
            resolved_api: HfApiLike = cast(HfApiLike, HfApi())
        else:
            resolved_api = api
        whoami = _hf_whoami(resolved_api, token=token)
        namespace = str(whoami["name"])

    return f"{namespace}/{repo_name}"


def build_publish_bundle(manifest_path: Path) -> PublishBundle:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_current_manifest_publishability(manifest)
    local_dir = manifest_path.parent
    allow_patterns = [manifest_path.name]
    for file_entry in manifest["files"]:
        allow_patterns.append(str(file_entry["path"]))

    deduped_patterns = list(dict.fromkeys(allow_patterns))
    return PublishBundle(
        manifest_path=manifest_path,
        local_dir=local_dir,
        allow_patterns=deduped_patterns,
    )


def extract_hf_commit_sha(commit_info: object) -> str | None:
    oid = getattr(commit_info, "oid", None)
    if isinstance(oid, str) and HF_COMMIT_SHA_RE.fullmatch(oid):
        return oid

    commit_url = getattr(commit_info, "commit_url", None)
    if not isinstance(commit_url, str):
        return None

    candidate = commit_url.rstrip("/").rsplit("/", maxsplit=1)[-1]
    if HF_COMMIT_SHA_RE.fullmatch(candidate):
        return candidate
    return None


def write_manifest_hf_revision(
    manifest_path: Path,
    *,
    repo_id: str,
    commit_sha: str,
    revision_tag: str | None = None,
) -> None:
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["huggingface"] = {
        "repo_id": repo_id,
        "commit_sha": commit_sha,
        "revision": commit_sha,
        "revision_tag": revision_tag,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_manifest_hf_revision(manifest_path: Path) -> None:
    manifest = cast(
        dict[str, object],
        json.loads(manifest_path.read_text(encoding="utf-8")),
    )
    hf_revision = manifest.get("huggingface")
    if not isinstance(hf_revision, dict):
        raise ValueError("manifest missing huggingface revision metadata")

    hf_revision_data = cast(dict[str, object], hf_revision)
    repo_id = hf_revision_data.get("repo_id")
    commit_sha = hf_revision_data.get("commit_sha")
    revision = hf_revision_data.get("revision")
    if not isinstance(repo_id, str) or not repo_id:
        raise ValueError("manifest missing huggingface.repo_id")
    if not isinstance(commit_sha, str) or not HF_COMMIT_SHA_RE.fullmatch(commit_sha):
        raise ValueError("manifest missing full huggingface.commit_sha")
    if revision != commit_sha:
        raise ValueError("manifest huggingface.revision must equal commit_sha for exact pinning")


def create_release_tag(
    *,
    api: HfApiLike,
    token: str,
    repo_id: str,
    tag: str,
    commit_sha: str,
) -> None:
    api.create_tag(
        repo_id=repo_id,
        tag=tag,
        revision=commit_sha,
        tag_message=f"Release snapshot {tag}",
        token=token,
        repo_type="dataset",
    )


def load_hf_refresh_state(
    *,
    repo_id: str,
    token: str,
    state_path_in_repo: str = HF_REFRESH_STATE_PATH,
) -> RefreshState:
    try:
        state_path = hf_hub_download(  # pyright: ignore[reportUnknownVariableType]
            repo_id=repo_id,
            filename=state_path_in_repo,
            repo_type="dataset",
            token=token,
        )
    except (EntryNotFoundError, RepositoryNotFoundError):
        return RefreshState()

    return RefreshState.model_validate_json(Path(state_path).read_text(encoding="utf-8"))


def write_hf_dataset_card(
    *,
    repo_id: str,
    api: HfApiLike,
    token: str,
    title: str,
    private: bool,
) -> None:
    visibility_line = "private" if private else "public"
    body = "\n".join(
        [
            "---",
            "license: mit",
            "pretty_name: Media Metadata Dataset Checkpoints",
            "task_categories:",
            "- text-classification",
            "---",
            "",
            f"# {title}",
            "",
            "Checkpointed test dataset for Media Metadata Dataset refresh-state and publish smoke flows.",
            "",
            f"- Repo id: `{repo_id}`",
            f"- Visibility: `{visibility_line}`",
            "- Contents: manifests, parquet checkpoints, and refresh-state metadata.",
            "",
        ]
    ).encode("utf-8")
    api.upload_file(
        path_or_fileobj=body,
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
        commit_message="Update dataset card",
    )


def publish_checkpoint_bundle(
    *,
    api: HfApiLike,
    token: str,
    repo_id: str,
    manifest_path: Path,
    checkpoint_path: str,
    state: RefreshState,
    private: bool = True,
    write_dataset_card: bool = True,
    release_tag: str | None = None,
) -> HfPublishResult:
    api.create_repo(
        repo_id,
        token=token,
        private=private,
        repo_type="dataset",
        exist_ok=True,
    )

    if write_dataset_card:
        write_hf_dataset_card(
            repo_id=repo_id,
            api=api,
            token=token,
            title=repo_id.split("/")[-1],
            private=private,
        )

    bundle = build_publish_bundle(manifest_path)
    commit_info = api.upload_folder(
        repo_id=repo_id,
        folder_path=bundle.local_dir,
        path_in_repo=checkpoint_path,
        commit_message=f"Upload checkpoint {checkpoint_path}",
        token=token,
        repo_type="dataset",
        allow_patterns=bundle.allow_patterns,
    )
    commit_sha = extract_hf_commit_sha(commit_info)
    if commit_sha is not None:
        write_manifest_hf_revision(
            manifest_path,
            repo_id=repo_id,
            commit_sha=commit_sha,
            revision_tag=release_tag,
        )
        api.upload_file(
            path_or_fileobj=manifest_path,
            path_in_repo=f"{checkpoint_path}/{manifest_path.name}",
            repo_id=repo_id,
            repo_type="dataset",
            token=token,
            commit_message=f"Record HF revision for {checkpoint_path}",
        )
        validate_manifest_hf_revision(manifest_path)
        if release_tag is not None:
            create_release_tag(
                api=api,
                token=token,
                repo_id=repo_id,
                tag=release_tag,
                commit_sha=commit_sha,
            )

    state_bytes = (
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    api.upload_file(
        path_or_fileobj=state_bytes,
        path_in_repo=HF_REFRESH_STATE_PATH,
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
        commit_message=f"Update refresh state for {checkpoint_path}",
    )

    commit_url = getattr(commit_info, "commit_url", None)
    return HfPublishResult(
        repo_id=repo_id,
        checkpoint_path=checkpoint_path,
        state_path=HF_REFRESH_STATE_PATH,
        commit_sha=commit_sha,
        commit_url=commit_url,
        release_tag=release_tag,
    )
