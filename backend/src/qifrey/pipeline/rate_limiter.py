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


class DailyBudgetExceededError(Exception):
    """Raised when the daily LLM call budget has been exhausted."""

    status_code = 429


def check_daily_budget_available() -> bool:
    """Return True if daily LLM call count is under QIFREY_LLM_DAILY_BUDGET."""
    settings = get_settings()
    if settings.llm_daily_budget <= 0:
        return True
    try:
        from datetime import UTC, datetime, timedelta

        from qifrey.db.models import LLMCall
        from qifrey.db.session import get_session_factory

        factory = get_session_factory()
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        with factory() as db:
            count = db.query(LLMCall).filter(LLMCall.created_at >= cutoff).count()
            return count < settings.llm_daily_budget
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not check daily LLM budget: %s", exc)
        return True


# Status callback: (story_id, status_or_waiting) -> None
_STATUS_LISTENERS: list[Callable[[int | None, str | bool | None], None]] = []


def register_rate_limit_listener(
    listener: Callable[[int | None, str | bool | None], None],
) -> None:
    """Register a callback invoked when entering or leaving rate limit or provider waits."""
    if listener not in _STATUS_LISTENERS:
        _STATUS_LISTENERS.append(listener)


def notify_rate_limit_status(story_id: int | None, status_or_waiting: str | bool | None) -> None:
    """Notify all registered listeners about rate limit and provider status changes."""
    for listener in _STATUS_LISTENERS:
        try:
            listener(story_id, status_or_waiting)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error in rate limit listener: %s", exc)


def is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception represents an HTTP 429 or quota exhaustion."""
    target = getattr(exc, "__cause__", None) or exc
    for e in (exc, target):
        for attr in ("status_code", "code", "http_status"):
            val = getattr(e, attr, None)
            if val in (429, "429", "RESOURCE_EXHAUSTED"):
                return True

        err_str = str(e).lower()
        if (
            "429" in err_str
            or "resource_exhausted" in err_str
            or "resource exhausted" in err_str
            or "rate limit" in err_str
            or "quota exceeded" in err_str
            or "too many requests" in err_str
            or "daily budget" in err_str
        ):
            return True
    return False


def is_503_error(exc: Exception) -> bool:
    """Check if an exception represents an HTTP 503 or UNAVAILABLE error."""
    target = getattr(exc, "__cause__", None) or exc
    for e in (exc, target):
        for attr in ("status_code", "code", "http_status"):
            val = getattr(e, attr, None)
            if val in (503, "503", "UNAVAILABLE"):
                return True

        err_str = str(e).lower()
        if "503" in err_str or "unavailable" in err_str or "service unavailable" in err_str:
            return True
    return False


def is_provider_error(exc: Exception) -> bool:
    """Check if an exception represents an HTTP 503 (UNAVAILABLE) or 500 (INTERNAL) error."""
    if is_503_error(exc):
        return True
    target = getattr(exc, "__cause__", None) or exc
    for e in (exc, target):
        for attr in ("status_code", "code", "http_status"):
            val = getattr(e, attr, None)
            if val in (500, "500", "INTERNAL"):
                return True

        err_str = str(e).lower()
        if "500" in err_str or "internal server error" in err_str or "internal error" in err_str:
            return True
    return False


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
        """Throttle requests to respect max_rpm sliding window and daily budget."""
        if not check_daily_budget_available():
            settings = get_settings()
            logger.warning("Daily LLM call budget (%d) reached.", settings.llm_daily_budget)
            notify_rate_limit_status(story_id, "Paused: rate limit")
            raise DailyBudgetExceededError(
                f"Daily LLM budget reached ({settings.llm_daily_budget} calls/24h). Paused."
            )

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
        max_retries: int = 6,
        initial_backoff: float = 2.0,
        max_backoff: float = 60.0,
    ) -> T:
        """Execute callable with throttling and exponential backoff retry.

        Retries on 429, 503, and 500 transient errors.
        """
        last_err: Exception | None = None

        for attempt in range(max_retries):
            self.acquire(story_id=story_id)
            try:
                return func()
            except Exception as exc:
                last_err = exc
                is_rl = is_rate_limit_error(exc)
                is_prov = is_provider_error(exc)
                if (is_rl or is_prov) and attempt < max_retries - 1:
                    status_signal: str | bool = True if is_rl else "waiting on provider"
                    status_log = "waiting on rate limit" if is_rl else "waiting on provider"
                    # Exponential backoff with jitter
                    backoff = min(
                        initial_backoff * (2**attempt) + random.uniform(0.1, 1.0),
                        max_backoff,
                    )
                    logger.warning(
                        "Transient error (%s) on attempt %d/%d for %s. Retrying in %.2fs: %s",
                        status_log,
                        attempt + 1,
                        max_retries,
                        purpose or "request",
                        backoff,
                        exc,
                    )
                    notify_rate_limit_status(story_id, status_signal)
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
            raise last_err
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
