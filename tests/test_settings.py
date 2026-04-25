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


def test_openai_compat_defaults_live_in_settings() -> None:
    settings = Settings()

    assert settings.openai_compat_base_url == "https://openrouter.ai/api/v1"
    assert settings.openai_compat_models == [
        "inclusionai/ling-2.6-flash:free",
        "inclusionai/ling-2.6-1t:free",
        "liquid/lfm-2.5-1.2b-instruct:free",
        "openai/gpt-oss-20b:free",
        "baidu/qianfan-ocr-fast:free",
    ]
