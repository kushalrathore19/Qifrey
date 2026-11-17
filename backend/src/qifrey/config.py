"""Application configuration via environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Qifrey application settings.

    Supports QIFREY_ env prefix, plus direct provider keys.
    """

    db_path: str = "qifrey.db"
    llm_provider: str = "anthropic"  # anthropic | gemini | fake
    llm_model: str = "claude-sonnet-4-20250514"
    llm_fallback_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("QIFREY_LLM_FALLBACK_MODEL", "LLM_FALLBACK_MODEL"),
    )
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "QIFREY_ANTHROPIC_API_KEY"),
    )
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "QIFREY_GEMINI_API_KEY"),
    )
    llm_max_rpm: int = Field(
        default=10,
        validation_alias=AliasChoices("QIFREY_LLM_MAX_RPM", "LLM_MAX_RPM"),
    )
    llm_daily_budget: int = Field(
        default=1000,
        validation_alias=AliasChoices("QIFREY_LLM_DAILY_BUDGET", "LLM_DAILY_BUDGET"),
    )
    max_upload_bytes: int = 5 * 1024 * 1024

    model_config = {
        "env_prefix": "QIFREY_",
        "populate_by_name": True,
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
