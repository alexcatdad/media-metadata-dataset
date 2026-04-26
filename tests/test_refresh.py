from __future__ import annotations

import json
from pathlib import Path

from media_offline_database.enrich_anilist_metadata import AniListResolvedMetadata
from media_offline_database.refresh import run_manami_refresh_checkpoint
from media_offline_database.refresh_state import RefreshState
from media_offline_database.settings import Settings


class FakeCommitInfo:
    def __init__(self, commit_url: str | None = None) -> None:
        self.commit_url = commit_url


class FakeHfApi:
    def __init__(self) -> None:
        self.uploaded_folders: list[dict[str, object]] = []
        self.uploaded_files: list[dict[str, object]] = []

    def create_repo(self, *args: object, **kwargs: object) -> object:
        _ = args, kwargs
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
        return FakeCommitInfo("https://huggingface.co/commit/123")

    def upload_file(self, **kwargs: object) -> FakeCommitInfo:
        self.uploaded_files.append(dict(kwargs))
        return FakeCommitInfo()


def test_run_manami_refresh_checkpoint_persists_resume_progress(tmp_path: Path) -> None:
    release_path = tmp_path / "manami-release.json"
    release_path.write_text(
        json.dumps(
            {
                "repository": "https://github.com/manami-project/anime-offline-database",
                "lastUpdate": "2026-04-25",
                "data": [
                    {
                        "sources": [
                            "https://anidb.net/anime/12681",
                            "https://anilist.co/anime/97986",
                        ],
                        "title": "Made in Abyss",
                        "type": "TV",
                        "episodes": 13,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SUMMER", "year": 2017},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                    {
                        "sources": [
                            "https://anidb.net/anime/23",
                            "https://anilist.co/anime/1",
                        ],
                        "title": "Cowboy Bebop",
                        "type": "TV",
                        "episodes": 26,
                        "status": "FINISHED",
                        "animeSeason": {"season": "SPRING", "year": 1998},
                        "synonyms": [],
                        "relatedAnime": [],
                        "tags": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    fake_api = FakeHfApi()
    settings = Settings.model_validate(
        {
            "HF_TOKEN": "hf_test",
            "HF_NAMESPACE": "alecatdad",
            "HF_DATASET_REPO": "media-metadata-dataset-test",
        }
    )

    result = run_manami_refresh_checkpoint(
        release_path=release_path,
        output_dir=tmp_path / "out",
        repo_id="alecatdad/media-metadata-dataset-test",
        batch_size=1,
        private_repo=True,
        settings=settings,
        api=fake_api,
        remote_state=RefreshState(),
        fetch_relations=lambda _anilist_id: [],
        fetch_metadata=lambda _anilist_id: AniListResolvedMetadata(
            genres=["Adventure"],
            studios=["Kinema Citrus"],
            creators=["Akihito Tsukushi"],
        ),
    )

    assert result.repo_id == "alecatdad/media-metadata-dataset-test"
    assert result.start_offset == 0
    assert result.end_offset == 1
    assert result.next_offset == 1
    assert result.total_candidates == 2
    assert result.status == "in_progress"
    assert result.checkpoint_path.endswith("00000000-00000001")
    assert result.local_state_path.exists()

    local_state = RefreshState.model_validate_json(
        result.local_state_path.read_text(encoding="utf-8")
    )
    job = local_state.jobs["anime.manami.default"]
    assert job.next_offset == 1
    assert job.completed_count == 1
