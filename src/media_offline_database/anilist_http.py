from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import sleep
from typing import Any

import httpx

ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
ANILIST_TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
DEFAULT_ANILIST_MAX_ATTEMPTS = 5
DEFAULT_ANILIST_MAX_RETRY_DELAY_SECONDS = 60.0


def post_anilist_graphql(
    *,
    query: str,
    variables: Mapping[str, Any],
    timeout_seconds: float = 20.0,
    max_attempts: int = DEFAULT_ANILIST_MAX_ATTEMPTS,
    max_retry_delay_seconds: float = DEFAULT_ANILIST_MAX_RETRY_DELAY_SECONDS,
) -> httpx.Response:
    last_response: httpx.Response | None = None

    for attempt_index in range(max_attempts):
        response = httpx.post(
            ANILIST_GRAPHQL_URL,
            json={
                "query": query,
                "variables": dict(variables),
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=timeout_seconds,
        )
        if response.status_code not in ANILIST_TRANSIENT_STATUSES:
            response.raise_for_status()
            return response

        last_response = response
        if attempt_index == max_attempts - 1:
            break

        sleep(
            _retry_delay_seconds(
                response,
                attempt_index=attempt_index,
                max_retry_delay_seconds=max_retry_delay_seconds,
            )
        )

    assert last_response is not None
    last_response.raise_for_status()
    return last_response


def _retry_delay_seconds(
    response: httpx.Response,
    *,
    attempt_index: int,
    max_retry_delay_seconds: float,
) -> float:
    header_delay = _retry_after_seconds(response.headers.get("Retry-After"))
    if header_delay is None:
        header_delay = _rate_limit_reset_delay_seconds(response.headers.get("X-RateLimit-Reset"))

    if header_delay is not None:
        return max(0.0, min(header_delay, max_retry_delay_seconds))

    return min(float(2**attempt_index), max_retry_delay_seconds)


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
