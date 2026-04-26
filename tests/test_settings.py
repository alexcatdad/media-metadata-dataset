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


def test_z_ai_defaults_live_in_settings() -> None:
    settings = Settings()

    assert settings.z_ai_base_url == "https://api.z.ai/api/paas/v4/"
    assert settings.z_ai_models == ["glm-4.5-flash", "glm-4.7-flash"]
    assert settings.z_ai_max_concurrency == 1


def test_z_ai_credentials_are_optional_but_detectable() -> None:
    blank_settings = Settings(z_ai_api_key_id=None, z_ai_api_key_secret=None)

    assert not blank_settings.has_z_ai_credentials

    settings = Settings(
        z_ai_api_key_id="id",
        z_ai_api_key_secret="secret",
    )

    assert settings.has_z_ai_credentials


def test_gemini_api_key_resolution_prefers_google_ai_studio_name() -> None:
    settings = Settings(
        google_ai_studio_api_key="studio-key",
        gemini_api_key="gemini-key",
        google_api_key="google-key",
    )

    assert settings.resolved_gemini_api_key == "studio-key"


def test_gemini_defaults_live_in_settings() -> None:
    settings = Settings()

    assert settings.gemini_base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert settings.gemini_benchmark_delay_seconds == 4.0
