from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from huggingface_hub import HfApi, hf_hub_download  # pyright: ignore[reportUnknownVariableType]
from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError
from pydantic import BaseModel, ConfigDict

from media_offline_database.publishability import validate_current_manifest_publishability
from media_offline_database.refresh_state import RefreshState
from media_offline_database.release_readiness import assert_release_readiness_if_applicable
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
    bundle_commit_sha: str | None = None
    commit_url: str | None = None
    release_tag: str | None = None


@dataclass(frozen=True)
class PublishBundle:
    manifest_path: Path
    local_dir: Path
    allow_patterns: list[str]


class PublishRehearsalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_id: str
    manifest_path: str
    local_dir: str
    allow_patterns: list[str]
    dataset_card_path: str | None = None


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
    assert_release_readiness_if_applicable(manifest_path)
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


def render_hf_dataset_card(
    *,
    repo_id: str,
    title: str,
    private: bool,
) -> str:
    visibility_line = "private" if private else "public"
    return "\n".join(
        [
            "---",
            "pretty_name: Media Metadata Dataset",
            "task_categories:",
            "- information-retrieval",
            "- feature-extraction",
            "---",
            "",
            f"# {title}",
            "",
            "Open, non-commercial dataset artifacts for narrative screen media discovery.",
            "",
            "This dataset is distributed as Parquet tables plus a manifest. It is not an API, "
            "hosted service, application, DuckDB database artifact, recommendation engine, graph "
            "browser, or RAG serving layer.",
            "",
            "## Artifact Contract",
            "",
            "Consumers should read the manifest first, then load the referenced Parquet files. "
            "The manifest records table paths, row counts, schema versions, source coverage, "
            "policy versions, recipe versions, enrichment status, and source snapshot IDs.",
            "",
            "Current v1 tables include shared core surfaces such as `entities`, `titles`, "
            "`external_ids`, `relationships`, `relationship_evidence`, `facets`, `provenance`, "
            "`source_records`, `source_snapshots`, and `provider_runs`, plus domain profiles for "
            "anime, TV, and movies.",
            "",
            "## Versioning And Pinning",
            "",
            "- Hugging Face Dataset Hub is the publication and continuity host.",
            "- `main` is the moving latest pointer.",
            "- Supported releases are tagged.",
            "- Exact consumers should pin a full Hugging Face commit SHA or a supported release tag.",
            "- Source snapshots and provider runs are exposed as manifest-linked Parquet tables.",
            "",
            "## Source Policy And Publishability",
            "",
            "Source roles are `BACKBONE_SOURCE`, `ID_SOURCE`, `LOCAL_EVIDENCE`, `RUNTIME_ONLY`, "
            "`PAID_EXPERIMENT_ONLY`, and `BLOCKED`.",
            "",
            "Credentials, API tokens, public endpoints, and local access authorize reading only "
            "when allowed by the provider. They do not imply redistribution rights.",
            "",
            "Public artifacts are governed by source policy, field policy, transform policy, and "
            "artifact policy. Restricted or local-only provider data must not leak into public "
            "Parquet tables, retrieval text, embeddings, judgments, or manifests.",
            "",
            "## Intended Use",
            "",
            "Downstream users may load these files into their own search, graph, recommendation, "
            "or RAG systems. This dataset exposes reusable surfaces; downstream consumers own "
            "interpretation, ranking, personalization, UI, and serving.",
            "",
            "## Limitations",
            "",
            "- V1 is not anime-only; it requires meaningful anime, TV, and movie source paths.",
            "- Some records may be partially enriched. Consumers should inspect enrichment status.",
            "- Source coverage depends on provider rights, publishability policy, and rate limits.",
            "- LLM outputs are judgments until materialization gates approve derived outputs.",
            "- Confidence is dimensional and recipe-specific, not one universal score.",
            "",
            "## License And Attribution",
            "",
            "License and attribution requirements are snapshot-specific and are recorded in the "
            "manifest and source policy surfaces. Consumers are responsible for preserving required "
            "attribution from the published snapshot.",
            "",
            "## Citation",
            "",
            "Cite the Hugging Face dataset repo, release tag or commit SHA, and manifest dataset "
            "version used.",
            "",
            f"- Repo id: `{repo_id}`",
            f"- Visibility: `{visibility_line}`",
            "",
        ]
    )


def rehearse_publish_bundle(
    *,
    manifest_path: Path,
    repo_id: str,
    output_dir: Path | None = None,
    private: bool = True,
) -> PublishRehearsalResult:
    bundle = build_publish_bundle(manifest_path)
    for pattern in bundle.allow_patterns:
        source_path = bundle.local_dir / pattern
        if not source_path.exists():
            raise FileNotFoundError(f"bundle path missing for publish rehearsal: {source_path}")

    dataset_card_path: Path | None = None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        dataset_card_path = output_dir / "README.md"
        dataset_card_path.write_text(
            render_hf_dataset_card(
                repo_id=repo_id,
                title=repo_id.split("/")[-1],
                private=private,
            ),
            encoding="utf-8",
        )

    return PublishRehearsalResult(
        repo_id=repo_id,
        manifest_path=str(bundle.manifest_path),
        local_dir=str(bundle.local_dir),
        allow_patterns=bundle.allow_patterns,
        dataset_card_path=None if dataset_card_path is None else str(dataset_card_path),
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
    body = render_hf_dataset_card(
        repo_id=repo_id,
        title=title,
        private=private,
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
    bundle = build_publish_bundle(manifest_path)
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

    bundle_commit_info = api.upload_folder(
        repo_id=repo_id,
        folder_path=bundle.local_dir,
        path_in_repo=checkpoint_path,
        commit_message=f"Upload checkpoint {checkpoint_path}",
        token=token,
        repo_type="dataset",
        allow_patterns=bundle.allow_patterns,
    )
    bundle_commit_sha = extract_hf_commit_sha(bundle_commit_info)

    state_bytes = (
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    state_commit_info = api.upload_file(
        path_or_fileobj=state_bytes,
        path_in_repo=HF_REFRESH_STATE_PATH,
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
        commit_message=f"Update refresh state for {checkpoint_path}",
    )
    commit_sha = extract_hf_commit_sha(state_commit_info) or bundle_commit_sha
    if release_tag is not None and commit_sha is not None:
        create_release_tag(
            api=api,
            token=token,
            repo_id=repo_id,
            tag=release_tag,
            commit_sha=commit_sha,
        )

    commit_url = getattr(state_commit_info, "commit_url", None) or getattr(
        bundle_commit_info,
        "commit_url",
        None,
    )
    return HfPublishResult(
        repo_id=repo_id,
        checkpoint_path=checkpoint_path,
        state_path=HF_REFRESH_STATE_PATH,
        commit_sha=commit_sha,
        bundle_commit_sha=bundle_commit_sha,
        commit_url=commit_url,
        release_tag=release_tag,
    )
