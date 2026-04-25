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
    google_ai_studio_api_key: str | None = Field(
        default=None,
        validation_alias="GOOGLE_AI_STUDIO_API_KEY",
    )
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        validation_alias="GEMINI_BASE_URL",
    )
    gemini_benchmark_delay_seconds: float = Field(
        default=4.0,
        validation_alias="GEMINI_BENCHMARK_DELAY_SECONDS",
    )
    z_ai_api_key_id: str | None = Field(default=None, validation_alias="Z_AI_API_KEY_ID")
    z_ai_api_key_secret: str | None = Field(
        default=None,
        validation_alias="Z_AI_API_KEY_SECRET",
    )
    z_ai_base_url: str = Field(
        default="https://api.z.ai/api/paas/v4/",
        validation_alias="Z_AI_BASE_URL",
    )
    z_ai_default_model: str = Field(
        default="glm-4.5-flash",
        validation_alias="Z_AI_DEFAULT_MODEL",
    )
    z_ai_fallback_models: str = Field(
        default="glm-4.7-flash",
        validation_alias="Z_AI_FALLBACK_MODELS",
    )
    z_ai_max_concurrency: int = Field(default=1, validation_alias="Z_AI_MAX_CONCURRENCY")

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

    @property
    def resolved_gemini_api_key(self) -> str | None:
        """Return the configured Gemini API key without exposing it."""

        return self.google_ai_studio_api_key or self.gemini_api_key or self.google_api_key

    @property
    def z_ai_models(self) -> list[str]:
        """Return the default Z.ai model followed by configured fallbacks."""

        fallback_models = [
            model.strip()
            for model in self.z_ai_fallback_models.split(",")
            if model.strip()
        ]
        return [self.z_ai_default_model, *fallback_models]

    @property
    def has_z_ai_credentials(self) -> bool:
        """Return whether the split Z.ai API key fields are present."""

        return bool(self.z_ai_api_key_id and self.z_ai_api_key_secret)
