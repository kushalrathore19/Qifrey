"""Application configuration via environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Qifrey application settings.

    Most fields use the QIFREY_ env prefix.
    ``anthropic_api_key`` reads ANTHROPIC_API_KEY directly (no prefix).
    """

    db_path: str = "qifrey.db"
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    max_upload_bytes: int = 5 * 1024 * 1024

    model_config = {
        "env_prefix": "QIFREY_",
        "populate_by_name": True,
    }


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
