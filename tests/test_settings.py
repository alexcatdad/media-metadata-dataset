from __future__ import annotations

import pytest

from media_offline_database.settings import Settings


def test_ai_credentials_smoke_accepts_required_values() -> None:
    settings = Settings(
        cloudflare_account_id="account",
        cloudflare_api_token="token",
        openai_compat_api_key="key",
    )

    settings.require_ai_credentials()


def test_ai_credentials_smoke_reports_missing_values() -> None:
    settings = Settings(
        cloudflare_account_id="account",
        cloudflare_api_token="",
        openai_compat_api_key=None,
    )

    with pytest.raises(ValueError, match="CLOUDFLARE_API_TOKEN"):
        settings.require_ai_credentials()
