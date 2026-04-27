from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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


@dataclass
class ProviderHttpClient:
    provider_id: str
    rate_limit: ProviderRateLimit
    retry_policy: ProviderRetryPolicy = field(default_factory=ProviderRetryPolicy)
    default_headers: Mapping[str, str] = field(default_factory=lambda: {})
    clock: Clock = monotonic
    sleeper: Sleeper = sleep
    _next_request_at: float = field(default=0.0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

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


ANILIST_HTTP_CLIENT = ProviderHttpClient(
    provider_id="anilist",
    rate_limit=ProviderRateLimit(provider_id="anilist", requests=30, period_seconds=60.0),
    retry_policy=ProviderRetryPolicy(reset_epoch_header="X-RateLimit-Reset"),
    default_headers={"User-Agent": "media-metadata-dataset local compiler"},
)
TVMAZE_HTTP_CLIENT = ProviderHttpClient(
    provider_id="tvmaze",
    rate_limit=ProviderRateLimit(provider_id="tvmaze", requests=10, period_seconds=10.0),
)
WIKIDATA_HTTP_CLIENT = ProviderHttpClient(
    provider_id="wikidata",
    rate_limit=ProviderRateLimit(provider_id="wikidata", requests=1, period_seconds=1.0),
)
