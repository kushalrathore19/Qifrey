"""Prompt loading utilities."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


@lru_cache
def load_prompt(name: str = "extraction_v1") -> str:
    """Load prompt template markdown file by name."""
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt template {name}.md not found in {_PROMPTS_DIR}")
    return path.read_text(encoding="utf-8")
