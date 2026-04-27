from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from media_offline_database.provider_http import (
    ANILIST_HTTP_CLIENT,
    ProviderHttpClient,
    ProviderRetryPolicy,
)

ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
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
    client = ANILIST_HTTP_CLIENT
    if _uses_custom_retry_policy(
        max_attempts=max_attempts,
        max_retry_delay_seconds=max_retry_delay_seconds,
    ):
        client = ProviderHttpClient(
            provider_id=ANILIST_HTTP_CLIENT.provider_id,
            rate_limit=ANILIST_HTTP_CLIENT.rate_limit,
            retry_policy=ProviderRetryPolicy(
                max_attempts=max_attempts,
                max_retry_delay_seconds=max_retry_delay_seconds,
                transient_statuses=ANILIST_HTTP_CLIENT.retry_policy.transient_statuses,
                reset_epoch_header=ANILIST_HTTP_CLIENT.retry_policy.reset_epoch_header,
            ),
            default_headers=ANILIST_HTTP_CLIENT.default_headers,
        )

    return client.post(
        ANILIST_GRAPHQL_URL,
        json_body={
            "query": query,
            "variables": dict(variables),
        },
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=timeout_seconds,
    )


def _uses_custom_retry_policy(
    *,
    max_attempts: int,
    max_retry_delay_seconds: float,
) -> bool:
    return (
        max_attempts != ANILIST_HTTP_CLIENT.retry_policy.max_attempts
        or max_retry_delay_seconds
        != ANILIST_HTTP_CLIENT.retry_policy.max_retry_delay_seconds
    )
