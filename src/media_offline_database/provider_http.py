from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import Lock
from time import monotonic, sleep
from typing import Any

import httpx

DEFAULT_TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})

type Clock = Callable[[], float]
type PrimitiveParam = str | int | float | bool | None
type QueryParams = (
    Mapping[str, PrimitiveParam | Sequence[PrimitiveParam]]
    | list[tuple[str, PrimitiveParam]]
)
type Sleeper = Callable[[float], None]


class ProviderBudgetExhaustedError(RuntimeError):
    pass


class ProviderRunGuardActiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderRateLimit:
    provider_id: str
    requests: int
    period_seconds: float

    @property
    def min_interval_seconds(self) -> float:
        return self.period_seconds / self.requests


@dataclass(frozen=True)
class ProviderRetryPolicy:
    max_attempts: int = 5
    max_retry_delay_seconds: float = 60.0
    transient_statuses: frozenset[int] = DEFAULT_TRANSIENT_STATUSES
    reset_epoch_header: str | None = None


@dataclass(frozen=True)
class ProviderBudgetPolicy:
    max_requests_per_day: int
    ledger_dir: Path = Path(".mod/cache/provider-http/budgets")


@dataclass(frozen=True)
class ProviderRunGuard:
    scope: str
    guard_dir: Path = Path(".mod/cache/provider-http/locks")
    stale_after_seconds: int = 6 * 60 * 60
    owner: str = field(default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}")

    def __enter__(self) -> ProviderRunGuard:
        self.acquire()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.release()

    def acquire(self) -> None:
        path = self.path
        now = datetime.now(UTC)
        if path.exists():
            existing = _load_run_guard(path)
            if existing is not None and existing.expires_at > now:
                raise ProviderRunGuardActiveError(
                    f"provider run guard already active for {self.scope}: {existing.owner}"
                )
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "media-offline-dataset.run-guard",
            "schema_version": 1,
            "scope": self.scope,
            "owner": self.owner,
            "started_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self.stale_after_seconds)).isoformat(),
        }
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def release(self) -> None:
        path = self.path
        if not path.exists():
            return
        existing = _load_run_guard(path)
        if existing is None or existing.owner == self.owner:
            path.unlink(missing_ok=True)

    @property
    def path(self) -> Path:
        return self.guard_dir / f"{_safe_scope_name(self.scope)}.json"


@dataclass
class ProviderHttpClient:
    provider_id: str
    rate_limit: ProviderRateLimit
    retry_policy: ProviderRetryPolicy = field(default_factory=ProviderRetryPolicy)
    budget_policy: ProviderBudgetPolicy | None = None
    default_headers: Mapping[str, str] = field(default_factory=lambda: {})
    clock: Clock = monotonic
    sleeper: Sleeper = sleep
    _next_request_at: float = field(default=0.0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)
    _budget_lock: Lock = field(default_factory=Lock, init=False)

    def get(
        self,
        url: str,
        *,
        params: QueryParams | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        return self.request("GET", url, params=params, headers=headers, timeout=timeout)

    def post(
        self,
        url: str,
        *,
        json_body: Any | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        return self.request(
            "POST",
            url,
            json_body=json_body,
            headers=headers,
            timeout=timeout,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        params: QueryParams | None = None,
        json_body: Any | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        last_response: httpx.Response | None = None
        last_error: httpx.TransportError | None = None

        for attempt_index in range(self.retry_policy.max_attempts):
            self._wait_for_request_slot()
            self._reserve_daily_budget()
            try:
                response = httpx.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=self._headers(headers),
                    timeout=timeout,
                )
            except httpx.TransportError as exc:
                last_error = exc
                if attempt_index == self.retry_policy.max_attempts - 1:
                    raise
                self.sleeper(self._retry_delay_seconds(None, attempt_index=attempt_index))
                continue

            if response.status_code not in self.retry_policy.transient_statuses:
                response.raise_for_status()
                return response

            last_response = response
            if attempt_index == self.retry_policy.max_attempts - 1:
                break

            self.sleeper(self._retry_delay_seconds(response, attempt_index=attempt_index))

        if last_response is not None:
            last_response.raise_for_status()
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"{self.provider_id} request failed without a response or transport error")

    def _wait_for_request_slot(self) -> None:
        with self._lock:
            now = self.clock()
            scheduled_at = max(now, self._next_request_at)
            self._next_request_at = scheduled_at + self.rate_limit.min_interval_seconds

        wait_seconds = scheduled_at - now
        if wait_seconds > 0:
            self.sleeper(wait_seconds)

    def _headers(self, headers: Mapping[str, str] | None) -> dict[str, str]:
        merged = dict(self.default_headers)
        if headers is not None:
            merged.update(headers)
        return merged

    def _reserve_daily_budget(self) -> None:
        if self.budget_policy is None:
            return

        today = datetime.now(UTC).date()
        ledger_path = _budget_ledger_path(
            self.budget_policy.ledger_dir,
            provider_id=self.provider_id,
        )
        with self._budget_lock:
            ledger = _load_budget_ledger(ledger_path, today=today)
            request_count = ledger.request_count
            if request_count >= self.budget_policy.max_requests_per_day:
                raise ProviderBudgetExhaustedError(
                    f"{self.provider_id} daily request budget exhausted: "
                    f"{request_count}/{self.budget_policy.max_requests_per_day}"
                )
            _write_budget_ledger(
                ledger_path,
                _ProviderBudgetLedger(
                    provider_id=self.provider_id,
                    date=today,
                    request_count=request_count + 1,
                    max_requests_per_day=self.budget_policy.max_requests_per_day,
                ),
            )

    def _retry_delay_seconds(
        self,
        response: httpx.Response | None,
        *,
        attempt_index: int,
    ) -> float:
        header_delay = None
        if response is not None:
            header_delay = _retry_after_seconds(response.headers.get("Retry-After"))
            if header_delay is None and self.retry_policy.reset_epoch_header is not None:
                header_delay = _rate_limit_reset_delay_seconds(
                    response.headers.get(self.retry_policy.reset_epoch_header)
                )

        if header_delay is not None:
            return max(0.0, min(header_delay, self.retry_policy.max_retry_delay_seconds))

        return min(float(2**attempt_index), self.retry_policy.max_retry_delay_seconds)


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    try:
        return float(stripped)
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(stripped)
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return (parsed - datetime.now(tz=UTC)).total_seconds()


def _rate_limit_reset_delay_seconds(value: str | None) -> float | None:
    if value is None:
        return None

    try:
        reset_at = datetime.fromtimestamp(float(value.strip()), tz=UTC)
    except (OSError, ValueError):
        return None

    return (reset_at - datetime.now(tz=UTC)).total_seconds()


@dataclass(frozen=True)
class _ProviderBudgetLedger:
    provider_id: str
    date: date
    request_count: int
    max_requests_per_day: int


@dataclass(frozen=True)
class _ProviderRunGuardRecord:
    owner: str
    expires_at: datetime


def _budget_ledger_path(ledger_dir: Path, *, provider_id: str) -> Path:
    configured_dir = os.environ.get("MOD_PROVIDER_HTTP_BUDGET_DIR")
    effective_dir = Path(configured_dir) if configured_dir else ledger_dir
    return effective_dir / f"{provider_id}.json"


def _load_budget_ledger(path: Path, *, today: date) -> _ProviderBudgetLedger:
    if not path.exists():
        return _ProviderBudgetLedger(
            provider_id=path.stem,
            date=today,
            request_count=0,
            max_requests_per_day=0,
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    ledger_date = date.fromisoformat(str(payload["date"]))
    if ledger_date != today:
        return _ProviderBudgetLedger(
            provider_id=path.stem,
            date=today,
            request_count=0,
            max_requests_per_day=int(payload.get("max_requests_per_day", 0)),
        )
    return _ProviderBudgetLedger(
        provider_id=str(payload.get("provider_id", path.stem)),
        date=ledger_date,
        request_count=int(payload["request_count"]),
        max_requests_per_day=int(payload.get("max_requests_per_day", 0)),
    )


def _write_budget_ledger(path: Path, ledger: _ProviderBudgetLedger) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider_id": ledger.provider_id,
        "date": ledger.date.isoformat(),
        "request_count": ledger.request_count,
        "max_requests_per_day": ledger.max_requests_per_day,
    }
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _load_run_guard(path: Path) -> _ProviderRunGuardRecord | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _ProviderRunGuardRecord(
            owner=str(payload["owner"]),
            expires_at=datetime.fromisoformat(str(payload["expires_at"])),
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _safe_scope_name(scope: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in scope).strip("-")


ANILIST_HTTP_CLIENT = ProviderHttpClient(
    provider_id="anilist",
    rate_limit=ProviderRateLimit(provider_id="anilist", requests=30, period_seconds=60.0),
    retry_policy=ProviderRetryPolicy(reset_epoch_header="X-RateLimit-Reset"),
    budget_policy=ProviderBudgetPolicy(max_requests_per_day=1_000),
    default_headers={"User-Agent": "media-metadata-dataset local compiler"},
)
TVMAZE_HTTP_CLIENT = ProviderHttpClient(
    provider_id="tvmaze",
    rate_limit=ProviderRateLimit(provider_id="tvmaze", requests=10, period_seconds=10.0),
    budget_policy=ProviderBudgetPolicy(max_requests_per_day=1_000),
)
WIKIDATA_HTTP_CLIENT = ProviderHttpClient(
    provider_id="wikidata",
    rate_limit=ProviderRateLimit(provider_id="wikidata", requests=1, period_seconds=1.0),
    budget_policy=ProviderBudgetPolicy(max_requests_per_day=250),
)
