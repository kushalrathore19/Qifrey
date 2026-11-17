"""Tests for Phase 10: editor side panel, live analysis, and single-chapter analysis."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from sqlalchemy.orm import Session

from qifrey.db.models import Chapter, Story
from qifrey.grammar.checker import get_grammar_checker_status
from qifrey.pipeline.llm_client import FakeLLMClient
from qifrey.pipeline.rate_limiter import (
    DailyBudgetExceededError,
    RateLimiter,
)
from qifrey.pipeline.runner import analyze_single_chapter


def test_grammar_status_reports_availability(client: Any) -> None:
    """GET /api/grammar/status returns structured status with available boolean and message."""
    res = client.get("/api/grammar/status")
    assert res.status_code == 200
    data = res.json()
    assert "available" in data
    assert isinstance(data["available"], bool)
    status_direct = get_grammar_checker_status()
    assert data["available"] == status_direct["available"]
    if not data["available"]:
        assert "unavailable" in data["message"].lower() or "java" in data["message"].lower()


def test_analyze_single_chapter_skips_when_hash_matches(db_session: Session) -> None:
    """Live analysis makes zero LLM calls if content_hash matches analyzed_hash."""
    story = Story(title="Live Story")
    db_session.add(story)
    db_session.flush()

    ch = Chapter(
        story_id=story.id,
        index=1,
        title="Chapter 1",
        text="Some unchanged text for testing zero LLM calls.",
        content_hash="hash_abc123",
        analyzed_hash="hash_abc123",
    )
    db_session.add(ch)
    db_session.commit()

    fake_llm = FakeLLMClient()
    result = analyze_single_chapter(ch.id, db_session, llm_client=fake_llm)

    assert result["status"] == "skipped"
    assert result["reason"] == "unchanged"
    # Zero LLM calls made!
    assert len(fake_llm.history) == 0


def test_analyze_single_chapter_analyzes_and_runs_contradictions(
    db_session: Session,
) -> None:
    """analyze_single_chapter extracts narrative elements and re-runs contradiction detection."""
    story = Story(title="Single Chapter Test")
    db_session.add(story)
    db_session.flush()

    text = "Arthur Pendragon drew Excalibur. He was forty years old."
    ch = Chapter(
        story_id=story.id,
        index=1,
        title="Chapter 1",
        text=text,
        content_hash="new_hash",
        analyzed_hash=None,
    )
    db_session.add(ch)
    db_session.commit()

    fake_llm = FakeLLMClient(
        responses=[
            {
                "characters": [
                    {
                        "name": "Arthur Pendragon",
                        "aliases": [],
                        "description": "King",
                        "evidence_quote": "Arthur Pendragon drew Excalibur",
                    }
                ],
                "locations": [],
                "facts": [
                    {
                        "character": "Arthur Pendragon",
                        "attribute": "age",
                        "value": "forty",
                        "evidence_quote": "He was forty years old",
                        "confidence": 1.0,
                    }
                ],
                "relationships": [],
            }
        ]
    )

    result = analyze_single_chapter(ch.id, db_session, llm_client=fake_llm)
    assert result["status"] == "completed"
    assert ch.analyzed_hash == ch.content_hash
    assert len(fake_llm.history) >= 1


def test_daily_budget_exhaustion_raises_rate_limit() -> None:
    """RateLimiter raises DailyBudgetExceededError when daily budget is reached."""
    with patch("qifrey.pipeline.rate_limiter.check_daily_budget_available", return_value=False):
        limiter = RateLimiter(max_rpm=60)
        try:
            limiter.acquire()
            raise AssertionError("Should have raised DailyBudgetExceededError")
        except DailyBudgetExceededError as exc:
            assert exc.status_code == 429
            assert "Daily LLM budget reached" in str(exc)
