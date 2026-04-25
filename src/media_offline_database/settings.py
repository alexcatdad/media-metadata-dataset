from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Safe runtime settings shared by CLI commands."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mod_env: str = Field(default="local", validation_alias="MOD_ENV")
    mod_log_level: str = Field(default="INFO", validation_alias="MOD_LOG_LEVEL")
    mod_data_dir: Path = Field(default=Path(".mod/data"), validation_alias="MOD_DATA_DIR")
    mod_cache_dir: Path = Field(default=Path(".mod/cache"), validation_alias="MOD_CACHE_DIR")
    mod_output_dir: Path = Field(default=Path(".mod/out"), validation_alias="MOD_OUTPUT_DIR")
