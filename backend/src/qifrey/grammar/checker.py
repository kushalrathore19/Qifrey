"""Grammar checker wrapper using LanguageTool with fiction-friendly filtering."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Fiction-friendly disabled rules (colloquial styling, fragments, typography quirks)
DEFAULT_DISABLED_RULES: frozenset[str] = frozenset(
    {
        "WHITESPACE_RULE",
        "EN_QUOTES",
        "EN_UNPAIRED_QUOTES",
        "SENTENCE_FRAGMENT",
        "FRAGMENT_TWO_WORDS",
        "COMMA_PARENTHESIS_WHITESPACE",
        "UPPERCASE_SENTENCE_START",
        "TOO_LONG_SENTENCE",
        "PASSIVE_VOICE",
        "INFORMAL_CONTRACTION",
    }
)

# Rules to skip when the error occurs inside quotation marks (spoken dialogue)
SKIP_IN_DIALOGUE_RULES: frozenset[str] = frozenset(
    {
        "SENTENCE_FRAGMENT",
        "INFORMAL_WORD",
        "SLANG",
        "DOUBLE_NEGATIVE",
        "COLLOQUIALISM",
        "BAD_STYLE",
        "CAN_NOT",
        "A_LOT_OF",
    }
)

_tool_instance: Any = None
_tool_failed: bool = False
_tool_failure_reason: str | None = None


@dataclass
class GrammarIssue:
    """A grammar or spelling issue detected in text."""

    message: str
    rule_id: str
    span_start: int
    span_end: int
    quote: str
    suggestions: list[str] = field(default_factory=list)


def _find_quote_spans(text: str) -> list[tuple[int, int]]:
    """Return character index ranges (start, end) that are enclosed in quotation marks."""
    spans: list[tuple[int, int]] = []
    # Match double quotes, curly double quotes, and single quotes
    patterns = [
        r'"([^"\\]*(\\.[^"\\]*)*)"',
        r"“([^”\\]*(\\.[^”\\]*)*)”",
        r"‘([^’\\]*(\\.[^’\\]*)*)’",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            spans.append((match.start(), match.end()))
    return spans


def _is_span_in_dialogue(start: int, end: int, quote_spans: list[tuple[int, int]]) -> bool:
    """Check if the given span falls within any quotation span."""
    return any(start >= q_start and end <= q_end for q_start, q_end in quote_spans)


def get_language_tool(language: str = "en-US") -> Any | None:
    """Return cached LanguageTool instance or None if Java/LanguageTool is unavailable."""
    global _tool_instance, _tool_failed, _tool_failure_reason
    if _tool_failed:
        return None
    if _tool_instance is not None:
        return _tool_instance

    try:
        import language_tool_python

        _tool_instance = language_tool_python.LanguageTool(language)
        return _tool_instance
    except Exception as exc:  # noqa: BLE001
        _tool_failed = True
        _tool_failure_reason = "grammar checker unavailable (Java not found)"
        logger.warning(
            "LanguageTool / Java runtime is unavailable (%s). Grammar checks will be skipped.",
            exc,
        )
        return None


def get_grammar_checker_status() -> dict[str, Any]:
    """Return status of the grammar checker (available or reason for unavailability)."""
    tool = get_language_tool()
    if tool is not None:
        return {"available": True, "message": None}
    return {
        "available": False,
        "message": _tool_failure_reason or "grammar checker unavailable (Java not found)",
    }


def check_grammar(
    text: str,
    *,
    language: str = "en-US",
    disabled_rules: set[str] | frozenset[str] | None = None,
    skip_dialogue_rules: set[str] | frozenset[str] | None = None,
) -> list[GrammarIssue]:
    """Analyze chapter text for grammar and spelling errors.

    Degrades gracefully if Java or LanguageTool is not installed.
    """
    if not text.strip():
        return []

    tool = get_language_tool(language)
    if tool is None:
        return []

    disabled = disabled_rules or DEFAULT_DISABLED_RULES
    dialogue_skip = skip_dialogue_rules or SKIP_IN_DIALOGUE_RULES
    quote_spans = _find_quote_spans(text)

    try:
        matches = tool.check(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error running LanguageTool check: %s", exc)
        return []

    issues: list[GrammarIssue] = []
    for m in matches:
        rule_id = getattr(m, "ruleId", "") or ""
        if rule_id in disabled:
            continue

        start = getattr(m, "offset", 0)
        length = getattr(m, "errorLength", 0)
        end = start + length

        # If inside dialogue and rule is skipped for dialogue, omit
        if rule_id in dialogue_skip and _is_span_in_dialogue(start, end, quote_spans):
            continue

        snippet = text[start:end] if 0 <= start < len(text) else ""
        suggestions = getattr(m, "replacements", []) or []

        issues.append(
            GrammarIssue(
                message=getattr(m, "message", ""),
                rule_id=rule_id,
                span_start=start,
                span_end=end,
                quote=snippet,
                suggestions=suggestions[:5],
            )
        )

    return issues
