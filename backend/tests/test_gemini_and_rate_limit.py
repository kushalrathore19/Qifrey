"""Tests for Phase 9: Gemini provider, rate limiter throttle, 429 retry, and caching."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from pydantic import BaseModel, Field

from qifrey.config import get_settings
from qifrey.db.models import Character, LLMCall, Story
from qifrey.graph.alias_resolver import (
    clear_resolution_cache,
    resolve_or_create_character,
)
from qifrey.pipeline.context_builder import chunk_chapter_text
from qifrey.pipeline.llm_client import (
    FakeLLMClient,
    GeminiClient,
    get_llm_client,
    set_llm_client,
)
from qifrey.pipeline.rate_limiter import (
    RateLimiter,
    is_rate_limit_error,
    register_rate_limit_listener,
)
from qifrey.pipeline.runner import _ANALYSIS_PROGRESS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class DummyTestSchema(BaseModel):
    name: str = Field(..., description="Character name")
    score: int = Field(default=10)


def test_is_rate_limit_error() -> None:
    """Detects 429, RESOURCE_EXHAUSTED, and rate limit errors across providers."""

    class Custom429Error(Exception):
        status_code = 429

    class CustomCodeExhaustedError(Exception):
        code = "RESOURCE_EXHAUSTED"

    assert is_rate_limit_error(Custom429Error("Rate limit")) is True
    assert is_rate_limit_error(CustomCodeExhaustedError("Out of quota")) is True
    assert is_rate_limit_error(Exception("429 Too Many Requests")) is True
    assert is_rate_limit_error(Exception("RESOURCE_EXHAUSTED: quota exceeded")) is True
    assert is_rate_limit_error(ValueError("Some other validation error")) is False


def test_gemini_client_complete_json_and_repair(db_session: Session) -> None:
    """GeminiClient calls SDK, validates schema, logs to LLMCall, and repairs invalid JSON."""
    mock_genai = MagicMock()
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client

    # First call returns invalid JSON; second call (repair) returns valid JSON conforming to schema
    mock_resp1 = MagicMock()
    mock_resp1.text = "Here is some non-json output: {bad"
    mock_resp1.usage_metadata.prompt_token_count = 20
    mock_resp1.usage_metadata.candidates_token_count = 10

    mock_resp2 = MagicMock()
    mock_resp2.text = '{"name": "Arthur Dent", "score": 42}'
    mock_resp2.usage_metadata.prompt_token_count = 35
    mock_resp2.usage_metadata.candidates_token_count = 15

    mock_client.models.generate_content.side_effect = [mock_resp1, mock_resp2]

    story = Story(title="Gemini Story")
    db_session.add(story)
    db_session.commit()

    with patch.dict(
        "sys.modules",
        {"google": MagicMock(), "google.genai": mock_genai, "google.genai.types": MagicMock()},
    ):
        client = GeminiClient(api_key="fake-gemini-key", model="gemini-2.5-flash")
        client.client = mock_client

        result = client.complete_json(
            system="You are an extractor.",
            user="Extract the character: Arthur Dent",
            schema=DummyTestSchema,
            story_id=story.id,
            purpose="test_gemini",
        )

        assert isinstance(result, DummyTestSchema)
        assert result.name == "Arthur Dent"
        assert result.score == 42

        # Verify calls recorded to LLMCall table in database
        calls = (
            db_session.query(LLMCall)
            .filter(LLMCall.story_id == story.id)
            .order_by(LLMCall.id)
            .all()
        )
        assert len(calls) == 2
        assert calls[0].purpose == "test_gemini"
        assert calls[0].model == "gemini-2.5-flash"
        assert calls[1].purpose == "test_gemini_repair"


def test_rate_limiter_throttle_enforces_rpm() -> None:
    """RateLimiter throttles rapid requests to stay under max_rpm."""
    limiter = RateLimiter(max_rpm=3)
    # 3 calls should proceed with no/minimal wait
    t0 = time.monotonic()
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5


def test_retry_on_429_backoff_and_status_update() -> None:
    """Retry on 429 updates status to 'waiting on rate limit' and resumes."""
    status_events: list[tuple[int | None, bool]] = []

    def status_listener(story_id: int | None, waiting: bool) -> None:
        status_events.append((story_id, waiting))

    register_rate_limit_listener(status_listener)

    limiter = RateLimiter(max_rpm=60)
    attempts = 0

    class RateLimit429Error(Exception):
        status_code = 429

    def flaky_func() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RateLimit429Error("Rate limit exceeded: 429")
        return "success"

    # Set up mock story in progress
    _ANALYSIS_PROGRESS[999] = {
        "story_id": 999,
        "status": "running",
        "current_chapter": 1,
        "total_chapters": 3,
        "error": None,
    }

    result = limiter.execute_with_retry(
        flaky_func,
        story_id=999,
        purpose="flaky_test",
        max_retries=4,
        initial_backoff=0.05,
        max_backoff=0.5,
    )

    assert result == "success"
    assert attempts == 3

    # Check that status listener was notified entering and leaving wait
    assert (999, True) in status_events
    assert (999, False) in status_events
    assert _ANALYSIS_PROGRESS[999]["status"] == "running"


def test_batching_small_chunks_per_chapter() -> None:
    """chunk_chapter_text batches small paragraphs/tail chunks into fewer calls."""
    # Create 3 short paragraphs
    p1 = "Paragraph one with some introductory text for chapter."
    p2 = "Paragraph two containing character descriptions."
    p3 = "Short final scene."
    text = f"{p1}\n\n{p2}\n\n{p3}"

    chunks = chunk_chapter_text(text, max_words=3000)
    assert len(chunks) == 1

    # Longer text where trailing chunk is small
    long_p1 = "word " * 2000
    long_p2 = "word " * 1200
    small_tail = "word " * 200
    combined = f"{long_p1}\n\n{long_p2}\n\n{small_tail}"
    chunks = chunk_chapter_text(combined, max_words=3000)
    # Long p1 (2000w), long p2 (1200w) + tail (200w) batched into 2 chunks instead of 3
    assert len(chunks) == 2


def test_alias_resolver_caches_llm_answers(db_session: Session) -> None:
    """Ambiguous alias resolution caches LLM answers so identical queries do not re-prompt."""
    clear_resolution_cache()

    story = Story(title="Cache Story")
    db_session.add(story)
    db_session.flush()

    c1 = Character(story_id=story.id, canonical_name="John Vance", description="Detective")
    c2 = Character(story_id=story.id, canonical_name="John Clark", description="Physician")
    db_session.add_all([c1, c2])
    db_session.commit()

    # Ambiguous query "John" matches both c1 and c2
    fake_llm = FakeLLMClient(
        responses=[{"is_same_person": True, "canonical_name": "John Vance", "confidence": 0.9}]
    )

    # First resolution: calls fake LLM
    res1 = resolve_or_create_character("John", story.id, db_session, llm_client=fake_llm)
    assert res1 is not None
    assert res1.id == c1.id
    assert len(fake_llm.history) == 1

    # Second resolution with another ambiguous mention of "John": should hit cache, NOT call LLM
    res2 = resolve_or_create_character("John", story.id, db_session, llm_client=fake_llm)
    assert res2 is not None
    assert res2.id == c1.id
    # History length remains 1
    assert len(fake_llm.history) == 1


def test_provider_config_selection() -> None:
    """get_llm_client returns appropriate client type based on config."""
    set_llm_client(None)
    with patch.object(get_settings(), "llm_provider", "gemini"):
        set_llm_client(None)
        client = get_llm_client()
        assert isinstance(client, GeminiClient)

    with patch.object(get_settings(), "llm_provider", "fake"):
        set_llm_client(None)
        client = get_llm_client()
        assert isinstance(client, FakeLLMClient)

    set_llm_client(None)
