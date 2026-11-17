"""Shared rate limiter and throttle with exponential backoff and jitter."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from qifrey.config import get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Status callback: (story_id, is_waiting) -> None
_STATUS_LISTENERS: list[Callable[[int | None, bool], None]] = []


def register_rate_limit_listener(listener: Callable[[int | None, bool], None]) -> None:
    """Register a callback invoked when entering or leaving rate limit waits."""
    if listener not in _STATUS_LISTENERS:
        _STATUS_LISTENERS.append(listener)


def notify_rate_limit_status(story_id: int | None, is_waiting: bool) -> None:
    """Notify all registered listeners about rate limit status changes."""
    for listener in _STATUS_LISTENERS:
        try:
            listener(story_id, is_waiting)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error in rate limit listener: %s", exc)


def is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception represents an HTTP 429 or quota exhaustion."""
    # Check status code attributes
    for attr in ("status_code", "code", "http_status"):
        val = getattr(exc, attr, None)
        if val in (429, "429", "RESOURCE_EXHAUSTED"):
            return True

    err_str = str(exc).lower()
    return (
        "429" in err_str
        or "resource_exhausted" in err_str
        or "resource exhausted" in err_str
        or "rate limit" in err_str
        or "quota exceeded" in err_str
        or "too many requests" in err_str
    )


class RateLimiter:
    """Thread-safe rate limiter enforcing max requests per minute (RPM)."""

    def __init__(self, max_rpm: int = 10) -> None:
        self.max_rpm = max_rpm
        self._lock = threading.Lock()
        self._timestamps: list[float] = []

    def set_max_rpm(self, max_rpm: int) -> None:
        with self._lock:
            self.max_rpm = max_rpm

    def acquire(self, story_id: int | None = None) -> None:
        """Throttle requests to respect max_rpm sliding window."""
        if self.max_rpm <= 0:
            return

        with self._lock:
            while True:
                now = time.monotonic()
                # Purge timestamps older than 60 seconds
                self._timestamps = [t for t in self._timestamps if now - t < 60.0]

                if len(self._timestamps) < self.max_rpm:
                    self._timestamps.append(now)
                    break

                # Window full: compute time until oldest timestamp expires
                oldest = self._timestamps[0]
                wait_time = max(0.05, 60.0 - (now - oldest) + 0.05)
                logger.info(
                    "Rate limit throttle (max %d RPM reached): waiting %.2fs...",
                    self.max_rpm,
                    wait_time,
                )
                if wait_time > 0.5:
                    notify_rate_limit_status(story_id, True)

                # Release lock while sleeping
                self._lock.release()
                try:
                    time.sleep(wait_time)
                finally:
                    self._lock.acquire()
                    if wait_time > 0.5:
                        notify_rate_limit_status(story_id, False)

    def execute_with_retry(
        self,
        func: Callable[[], T],
        *,
        story_id: int | None = None,
        purpose: str = "",
        max_retries: int = 5,
        initial_backoff: float = 2.0,
        max_backoff: float = 60.0,
    ) -> T:
        """Execute callable with throttling and exponential backoff retry for 429 errors."""
        last_err: Exception | None = None

        for attempt in range(max_retries):
            self.acquire(story_id=story_id)
            try:
                return func()
            except Exception as exc:
                last_err = exc
                if is_rate_limit_error(exc) and attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    backoff = min(
                        initial_backoff * (2**attempt) + random.uniform(0.1, 1.0),
                        max_backoff,
                    )
                    logger.warning(
                        "Rate limit hit (429/RESOURCE_EXHAUSTED) for %s. Retrying in %.2fs "
                        "(attempt %d/%d): %s",
                        purpose or "request",
                        backoff,
                        attempt + 1,
                        max_retries,
                        exc,
                    )
                    notify_rate_limit_status(story_id, True)
                    try:
                        time.sleep(backoff)
                    finally:
                        notify_rate_limit_status(story_id, False)
                elif attempt < max_retries - 1:
                    # Other transient errors: brief backoff
                    wait_time = 2**attempt
                    logger.warning(
                        "LLM call attempt %d for %s failed: %s. Retrying in %ds...",
                        attempt + 1,
                        purpose or "request",
                        exc,
                        wait_time,
                    )
                    time.sleep(wait_time)
                else:
                    raise

        if last_err is not None:
            raise RuntimeError(
                f"LLM request failed after {max_retries} attempts: {last_err}"
            ) from last_err
        raise RuntimeError("LLM request failed with unknown error.")


_rate_limiter_instance: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return shared RateLimiter singleton."""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        settings = get_settings()
        _rate_limiter_instance = RateLimiter(max_rpm=settings.llm_max_rpm)
    return _rate_limiter_instance


def reset_rate_limiter(max_rpm: int | None = None) -> RateLimiter:
    """Reset shared RateLimiter singleton (useful for tests)."""
    global _rate_limiter_instance
    rpm = max_rpm if max_rpm is not None else get_settings().llm_max_rpm
    _rate_limiter_instance = RateLimiter(max_rpm=rpm)
    return _rate_limiter_instance
