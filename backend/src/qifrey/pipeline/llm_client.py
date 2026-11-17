"""LLM client interface, Anthropic implementation, and test double."""

from __future__ import annotations

import abc
import hashlib
import json
import logging
import re
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from qifrey.config import get_settings
from qifrey.db.models import LLMCall
from qifrey.db.session import get_session_factory
from qifrey.pipeline.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _compute_prompt_hash(system: str, user: str) -> str:
    combined = f"SYSTEM:{system}\nUSER:{user}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _extract_json_text(raw: str) -> str:
    """Extract JSON string from raw model text, stripping markdown code blocks if present."""
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _record_llm_call(
    *,
    story_id: int | None,
    purpose: str,
    model: str,
    prompt_hash: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
) -> None:
    """Log an LLM call record into the database."""
    try:
        factory = get_session_factory()
        with factory() as db:
            call = LLMCall(
                story_id=story_id,
                purpose=purpose,
                model=model,
                prompt_hash=prompt_hash,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
            )
            db.add(call)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to record LLMCall to database: %s", exc)


class LLMClient(abc.ABC):
    """Abstract interface for LLM completions."""

    @abc.abstractmethod
    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        story_id: int | None = None,
        purpose: str = "extraction",
    ) -> T:
        """Prompt the LLM and return a validated Pydantic model instance."""


class AnthropicClient(LLMClient):
    """Anthropic Claude implementation with retry, JSON validation, and repair."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
    ) -> None:
        import anthropic

        settings = get_settings()
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.llm_model
        self.max_retries = max_retries
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def _call_raw(
        self,
        system: str,
        user: str,
        *,
        story_id: int | None = None,
        purpose: str = "",
    ) -> tuple[str, int, int, int]:
        """Perform raw API call with shared rate limiter and retries."""

        def _do_call() -> tuple[str, int, int, int]:
            start = time.perf_counter()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=0.0,
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            text = ""
            for block in response.content:
                if getattr(block, "type", "") == "text":
                    text += block.text

            in_tokens = response.usage.input_tokens
            out_tokens = response.usage.output_tokens
            return text, in_tokens, out_tokens, latency_ms

        rate_limiter = get_rate_limiter()
        return rate_limiter.execute_with_retry(
            _do_call,
            story_id=story_id,
            purpose=purpose,
            max_retries=self.max_retries,
        )

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        story_id: int | None = None,
        purpose: str = "extraction",
    ) -> T:
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        system_with_schema = (
            f"{system}\n\n"
            f"You MUST output valid JSON only, conforming exactly to this JSON Schema:\n"
            f"{schema_json}\n"
            f"Do not include any commentary or text outside the JSON object."
        )

        prompt_hash = _compute_prompt_hash(system_with_schema, user)
        raw_text, in_tokens, out_tokens, latency_ms = self._call_raw(
            system_with_schema,
            user,
            story_id=story_id,
            purpose=purpose,
        )

        _record_llm_call(
            story_id=story_id,
            purpose=purpose,
            model=self.model,
            prompt_hash=prompt_hash,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            latency_ms=latency_ms,
        )

        json_candidate = _extract_json_text(raw_text)
        try:
            parsed = json.loads(json_candidate)
            return schema.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as parse_error:
            logger.warning(
                "JSON validation failed (%s). Attempting one repair request...",
                parse_error,
            )
            # One repair attempt
            repair_user = (
                f"Your previous response could not be parsed as valid JSON matching the schema.\n"
                f"Error: {parse_error}\n\n"
                f"Previous output:\n{raw_text}\n\n"
                f"Please fix and output ONLY the corrected JSON object conforming to the schema."
            )
            repair_hash = _compute_prompt_hash(system_with_schema, repair_user)
            repaired_text, r_in, r_out, r_latency = self._call_raw(
                system_with_schema,
                repair_user,
                story_id=story_id,
                purpose=f"{purpose}_repair",
            )
            _record_llm_call(
                story_id=story_id,
                purpose=f"{purpose}_repair",
                model=self.model,
                prompt_hash=repair_hash,
                input_tokens=r_in,
                output_tokens=r_out,
                latency_ms=r_latency,
            )
            repaired_json = _extract_json_text(repaired_text)
            parsed_repair = json.loads(repaired_json)
            return schema.model_validate(parsed_repair)


class GeminiClient(LLMClient):
    """Google Gemini implementation using official google-genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int = 5,
    ) -> None:
        from google import genai

        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key or "placeholder-api-key"
        # Default model for Gemini
        default_model = (
            settings.llm_model
            if settings.llm_model and not settings.llm_model.startswith("claude-")
            else "gemini-2.5-flash"
        )
        self.model = model or default_model
        self.max_retries = max_retries
        self.client = genai.Client(api_key=self.api_key)

    def _call_raw(
        self,
        system: str,
        user: str,
        *,
        story_id: int | None = None,
        purpose: str = "",
    ) -> tuple[str, int, int, int]:
        """Perform raw Gemini API call wrapped in rate limiter and retry."""
        from google.genai import types

        def _do_call() -> tuple[str, int, int, int]:
            start = time.perf_counter()
            config = types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                temperature=0.0,
            )
            response = self.client.models.generate_content(
                model=self.model,
                contents=user,
                config=config,
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            text = response.text or ""
            in_tokens = 0
            out_tokens = 0
            if response.usage_metadata:
                in_tokens = response.usage_metadata.prompt_token_count or 0
                out_tokens = response.usage_metadata.candidates_token_count or 0
            return text, in_tokens, out_tokens, latency_ms

        rate_limiter = get_rate_limiter()
        return rate_limiter.execute_with_retry(
            _do_call,
            story_id=story_id,
            purpose=purpose,
            max_retries=self.max_retries,
        )

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        story_id: int | None = None,
        purpose: str = "extraction",
    ) -> T:
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        system_with_schema = (
            f"{system}\n\n"
            f"You MUST output valid JSON only, conforming exactly to this JSON Schema:\n"
            f"{schema_json}\n"
            f"Do not include any commentary or text outside the JSON object."
        )

        prompt_hash = _compute_prompt_hash(system_with_schema, user)
        raw_text, in_tokens, out_tokens, latency_ms = self._call_raw(
            system_with_schema,
            user,
            story_id=story_id,
            purpose=purpose,
        )

        _record_llm_call(
            story_id=story_id,
            purpose=purpose,
            model=self.model,
            prompt_hash=prompt_hash,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            latency_ms=latency_ms,
        )

        json_candidate = _extract_json_text(raw_text)
        try:
            parsed = json.loads(json_candidate)
            return schema.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as parse_error:
            logger.warning(
                "JSON validation failed (%s). Attempting one repair request with Gemini...",
                parse_error,
            )
            repair_user = (
                f"Your previous response could not be parsed as valid JSON matching the schema.\n"
                f"Error: {parse_error}\n\n"
                f"Previous output:\n{raw_text}\n\n"
                f"Please fix and output ONLY the corrected JSON object conforming to the schema."
            )
            repair_hash = _compute_prompt_hash(system_with_schema, repair_user)
            repaired_text, r_in, r_out, r_latency = self._call_raw(
                system_with_schema,
                repair_user,
                story_id=story_id,
                purpose=f"{purpose}_repair",
            )
            _record_llm_call(
                story_id=story_id,
                purpose=f"{purpose}_repair",
                model=self.model,
                prompt_hash=repair_hash,
                input_tokens=r_in,
                output_tokens=r_out,
                latency_ms=r_latency,
            )
            repaired_json = _extract_json_text(repaired_text)
            parsed_repair = json.loads(repaired_json)
            return schema.model_validate(parsed_repair)


class FakeLLMClient(LLMClient):
    """Test double returning canned responses or schema defaults."""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self.responses: list[Any] = responses or []
        self.history: list[dict[str, Any]] = []

    def set_next_response(self, response: Any) -> None:
        self.responses.append(response)

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        story_id: int | None = None,
        purpose: str = "extraction",
    ) -> T:
        prompt_hash = _compute_prompt_hash(system, user)
        self.history.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "story_id": story_id,
                "purpose": purpose,
                "prompt_hash": prompt_hash,
            }
        )

        _record_llm_call(
            story_id=story_id,
            purpose=purpose,
            model="fake-llm",
            prompt_hash=prompt_hash,
            input_tokens=len(user.split()),
            output_tokens=50,
            latency_ms=5,
        )

        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, schema):
                return item
            if isinstance(item, dict):
                return schema.model_validate(item)
            if isinstance(item, str):
                parsed = json.loads(_extract_json_text(item))
                return schema.model_validate(parsed)
            if isinstance(item, Exception):
                raise item

        # Default fallback: construct empty or dummy instance
        try:
            return schema()
        except ValidationError:
            dummy_data: dict[str, Any] = {}
            for field_name, field_info in schema.model_fields.items():
                if field_info.is_required():
                    ann = field_info.annotation
                    if ann is str:
                        dummy_data[field_name] = "dummy"
                    elif ann is int:
                        dummy_data[field_name] = 0
                    elif ann is float:
                        dummy_data[field_name] = 0.0
                    elif ann is bool:
                        dummy_data[field_name] = False
                    elif getattr(ann, "__origin__", None) is list:
                        dummy_data[field_name] = []
                    else:
                        dummy_data[field_name] = "dummy"
            return schema.model_validate(dummy_data)


_active_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return configured LLM client singleton."""
    global _active_llm_client
    if _active_llm_client is not None:
        return _active_llm_client

    settings = get_settings()
    provider = settings.llm_provider.strip().lower()
    if provider == "gemini":
        default_model = (
            settings.llm_model
            if settings.llm_model and not settings.llm_model.startswith("claude-")
            else "gemini-2.5-flash"
        )
        _active_llm_client = GeminiClient(
            api_key=settings.gemini_api_key,
            model=default_model,
        )
    elif provider == "anthropic":
        _active_llm_client = AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
        )
    else:
        _active_llm_client = FakeLLMClient()
    return _active_llm_client


def set_llm_client(client: LLMClient | None) -> None:
    """Override active client (useful for tests)."""
    global _active_llm_client
    _active_llm_client = client
