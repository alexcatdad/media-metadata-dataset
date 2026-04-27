from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from pytest import MonkeyPatch

from media_offline_database import provider_http


def _response(status_code: int, *, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers=headers,
        json={"data": {"Media": None}},
        request=httpx.Request("GET", "https://example.test/resource"),
    )


def test_provider_http_client_spaces_request_starts(monkeypatch: MonkeyPatch) -> None:
    now = 0.0
    sleeps: list[float] = []

    def fake_clock() -> float:
        return now

    def fake_sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    def fake_request(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return _response(200)

    monkeypatch.setattr(provider_http.httpx, "request", fake_request)
    client = provider_http.ProviderHttpClient(
        provider_id="example",
        rate_limit=provider_http.ProviderRateLimit(
            provider_id="example",
            requests=30,
            period_seconds=60.0,
        ),
        clock=fake_clock,
        sleeper=fake_sleep,
    )

    client.get("https://example.test/resource")
    client.get("https://example.test/resource")
    client.get("https://example.test/resource")

    assert sleeps == [2.0, 2.0]


def test_provider_http_client_retries_transient_429(monkeypatch: MonkeyPatch) -> None:
    responses: Iterator[httpx.Response] = iter(
        [
            _response(429, headers={"Retry-After": "0"}),
            _response(200),
        ]
    )
    sleeps: list[float] = []

    def fake_request(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return next(responses)

    monkeypatch.setattr(provider_http.httpx, "request", fake_request)
    client = provider_http.ProviderHttpClient(
        provider_id="example",
        rate_limit=provider_http.ProviderRateLimit(
            provider_id="example",
            requests=1,
            period_seconds=0.0,
        ),
        retry_policy=provider_http.ProviderRetryPolicy(max_attempts=2),
        sleeper=sleeps.append,
    )

    response = client.get("https://example.test/resource")

    assert response.status_code == 200
    assert sleeps == [0.0]


def test_provider_http_client_raises_after_bounded_retries(
    monkeypatch: MonkeyPatch,
) -> None:
    responses: Iterator[httpx.Response] = iter(
        [
            _response(503, headers={"Retry-After": "0"}),
            _response(503),
        ]
    )

    def fake_request(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return next(responses)

    def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(provider_http.httpx, "request", fake_request)
    client = provider_http.ProviderHttpClient(
        provider_id="example",
        rate_limit=provider_http.ProviderRateLimit(
            provider_id="example",
            requests=1,
            period_seconds=0.0,
        ),
        retry_policy=provider_http.ProviderRetryPolicy(max_attempts=2),
        sleeper=fake_sleep,
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client.get("https://example.test/resource")

    exc = exc_info.value
    assert exc.response.status_code == 503


def test_provider_http_client_uses_reset_header(monkeypatch: MonkeyPatch) -> None:
    responses: Iterator[httpx.Response] = iter(
        [
            _response(429, headers={"X-RateLimit-Reset": "10"}),
            _response(503),
        ]
    )
    sleeps: list[float] = []

    def fake_request(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return next(responses)

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(provider_http.httpx, "request", fake_request)
    monkeypatch.setattr(provider_http, "datetime", _FakeDateTime)
    client = provider_http.ProviderHttpClient(
        provider_id="example",
        rate_limit=provider_http.ProviderRateLimit(
            provider_id="example",
            requests=1,
            period_seconds=0.0,
        ),
        retry_policy=provider_http.ProviderRetryPolicy(
            max_attempts=2,
            reset_epoch_header="X-RateLimit-Reset",
        ),
        sleeper=fake_sleep,
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client.get("https://example.test/resource")

    assert sleeps == [2.5]
    exc = exc_info.value
    assert exc.response.status_code == 503


def test_provider_http_client_persists_daily_budget_guard(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    requests: list[str] = []

    def fake_request(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        requests.append(f"{method} {url}")
        return _response(200)

    monkeypatch.setattr(provider_http.httpx, "request", fake_request)
    client = provider_http.ProviderHttpClient(
        provider_id="example",
        rate_limit=provider_http.ProviderRateLimit(
            provider_id="example",
            requests=1,
            period_seconds=0.0,
        ),
        budget_policy=provider_http.ProviderBudgetPolicy(
            max_requests_per_day=1,
            ledger_dir=tmp_path,
        ),
    )

    client.get("https://example.test/resource")

    with pytest.raises(provider_http.ProviderBudgetExhaustedError):
        client.get("https://example.test/resource")

    assert requests == ["GET https://example.test/resource"]
    assert (tmp_path / "example.json").exists()


def test_provider_http_client_resets_daily_budget_for_new_day(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "example.json"
    ledger_path.write_text(
        '{\n'
        '  "date": "2026-04-26",\n'
        '  "max_requests_per_day": 1,\n'
        '  "provider_id": "example",\n'
        '  "request_count": 1\n'
        '}\n',
        encoding="utf-8",
    )
    requests: list[str] = []

    def fake_request(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        requests.append(f"{method} {url}")
        return _response(200)

    monkeypatch.setattr(provider_http.httpx, "request", fake_request)
    monkeypatch.setattr(provider_http, "datetime", _BudgetDateTime)
    client = provider_http.ProviderHttpClient(
        provider_id="example",
        rate_limit=provider_http.ProviderRateLimit(
            provider_id="example",
            requests=1,
            period_seconds=0.0,
        ),
        budget_policy=provider_http.ProviderBudgetPolicy(
            max_requests_per_day=1,
            ledger_dir=tmp_path,
        ),
    )

    client.get("https://example.test/resource")

    assert requests == ["GET https://example.test/resource"]


def test_provider_run_guard_blocks_active_duplicate(tmp_path: Path) -> None:
    first = provider_http.ProviderRunGuard(
        scope="refresh:anime.manami.default",
        guard_dir=tmp_path,
        owner="worker-1",
    )
    first.acquire()

    second = provider_http.ProviderRunGuard(
        scope="refresh:anime.manami.default",
        guard_dir=tmp_path,
        owner="worker-2",
    )
    with pytest.raises(provider_http.ProviderRunGuardActiveError):
        second.acquire()

    first.release()
    second.acquire()
    second.release()


def test_provider_run_guard_replaces_expired_guard(
    tmp_path: Path,
) -> None:
    guard_path = tmp_path / "refresh-anime-manami-default.json"
    guard_path.write_text(
        '{\n'
        '  "expires_at": "2026-04-26T00:00:00+00:00",\n'
        '  "owner": "old-worker",\n'
        '  "schema": "media-offline-dataset.run-guard",\n'
        '  "schema_version": 1,\n'
        '  "scope": "refresh:anime.manami.default",\n'
        '  "started_at": "2026-04-25T18:00:00+00:00"\n'
        '}\n',
        encoding="utf-8",
    )

    guard = provider_http.ProviderRunGuard(
        scope="refresh:anime.manami.default",
        guard_dir=tmp_path,
        owner="new-worker",
    )
    guard.acquire()

    assert "new-worker" in guard_path.read_text(encoding="utf-8")

    guard.release()


class _FakeDateTime:
    value: float = 7.5

    @classmethod
    def now(cls, tz: object | None = None) -> _FakeDateTime:
        _ = tz
        return cls()

    @classmethod
    def fromtimestamp(cls, value: float, tz: object | None = None) -> _FakeDateTime:
        _ = tz
        instance = cls()
        instance.value = value
        return instance

    def __sub__(self, other: _FakeDateTime) -> _FakeTimeDelta:
        return _FakeTimeDelta(self.value - other.value)


class _FakeTimeDelta:
    def __init__(self, value: float) -> None:
        self.value = value

    def total_seconds(self) -> float:
        return self.value


class _BudgetDateTime:
    @classmethod
    def now(cls, tz: object | None = None) -> _BudgetDateTime:
        _ = tz
        return cls()

    def date(self) -> date:
        return date(2026, 4, 27)
