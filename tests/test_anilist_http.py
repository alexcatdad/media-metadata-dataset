from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
from pytest import MonkeyPatch

from media_offline_database import anilist_http


def _response(status_code: int, *, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers=headers,
        json={"data": {"Media": None}},
        request=httpx.Request("POST", anilist_http.ANILIST_GRAPHQL_URL),
    )


def test_post_anilist_graphql_retries_transient_429(monkeypatch: MonkeyPatch) -> None:
    responses: Iterator[httpx.Response] = iter(
        [
            _response(429, headers={"Retry-After": "0"}),
            _response(200),
        ]
    )
    sleeps: list[float] = []

    def fake_post(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return next(responses)

    monkeypatch.setattr(anilist_http.httpx, "post", fake_post)
    monkeypatch.setattr(anilist_http, "sleep", sleeps.append)

    response = anilist_http.post_anilist_graphql(
        query="query",
        variables={"id": 1},
        max_attempts=2,
    )

    assert response.status_code == 200
    assert sleeps == [0.0]


def test_post_anilist_graphql_raises_after_bounded_retries(
    monkeypatch: MonkeyPatch,
) -> None:
    responses: Iterator[httpx.Response] = iter(
        [
            _response(503, headers={"Retry-After": "0"}),
            _response(503),
        ]
    )

    def fake_post(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return next(responses)

    def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(anilist_http.httpx, "post", fake_post)
    monkeypatch.setattr(anilist_http, "sleep", fake_sleep)

    try:
        anilist_http.post_anilist_graphql(
            query="query",
            variables={"id": 1},
            max_attempts=2,
        )
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 503
    else:
        raise AssertionError("Expected HTTPStatusError")
