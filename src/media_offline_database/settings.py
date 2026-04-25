from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Safe runtime settings shared by CLI commands."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    mod_env: str = Field(default="local", validation_alias="MOD_ENV")
    mod_log_level: str = Field(default="INFO", validation_alias="MOD_LOG_LEVEL")
    mod_data_dir: Path = Field(default=Path(".mod/data"), validation_alias="MOD_DATA_DIR")
    mod_cache_dir: Path = Field(default=Path(".mod/cache"), validation_alias="MOD_CACHE_DIR")
    mod_output_dir: Path = Field(default=Path(".mod/out"), validation_alias="MOD_OUTPUT_DIR")
    cloudflare_account_id: str | None = Field(
        default=None,
        validation_alias="CLOUDFLARE_ACCOUNT_ID",
    )
    cloudflare_api_token: str | None = Field(
        default=None,
        validation_alias="CLOUDFLARE_API_TOKEN",
    )
    openai_compat_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_COMPAT_API_KEY",
    )
    openai_compat_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias="OPENAI_COMPAT_BASE_URL",
    )
    openai_compat_default_model: str = Field(
        default="inclusionai/ling-2.6-flash:free",
        validation_alias="OPENAI_COMPAT_DEFAULT_MODEL",
    )
    openai_compat_fallback_models: str = Field(
        default=(
            "inclusionai/ling-2.6-1t:free,"
            "liquid/lfm-2.5-1.2b-instruct:free,"
            "openai/gpt-oss-20b:free,"
            "baidu/qianfan-ocr-fast:free"
        ),
        validation_alias="OPENAI_COMPAT_FALLBACK_MODELS",
    )

    def require_ai_credentials(self) -> None:
        """Validate required AI credentials without exposing their values."""

        missing = [
            name
            for name, value in {
                "CLOUDFLARE_ACCOUNT_ID": self.cloudflare_account_id,
                "CLOUDFLARE_API_TOKEN": self.cloudflare_api_token,
                "OPENAI_COMPAT_API_KEY": self.openai_compat_api_key,
            }.items()
            if not value
        ]

        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(f"missing required AI credential settings: {missing_list}")

    @property
    def openai_compat_models(self) -> list[str]:
        """Return the default model followed by configured fallbacks."""

        fallback_models = [
            model.strip()
            for model in self.openai_compat_fallback_models.split(",")
            if model.strip()
        ]
        return [self.openai_compat_default_model, *fallback_models]
