"""Tests for grammar checker, fiction filtering, and graceful degradation."""

from __future__ import annotations

import shutil
from unittest.mock import MagicMock, patch

import pytest

from qifrey.grammar.checker import (
    _find_quote_spans,
    _is_span_in_dialogue,
    check_grammar,
    get_language_tool,
)


def _has_java() -> bool:
    """Return True if a functional Java runtime is found."""
    if not shutil.which("java"):
        return False
    # Check if LanguageTool can actually instantiate
    tool = get_language_tool()
    return tool is not None


def test_find_quote_spans() -> None:
    text = 'He said, "Hello there!" and then whispered, “Be quiet.”'
    spans = _find_quote_spans(text)
    assert len(spans) == 2
    # Verify dialogue span matching
    assert _is_span_in_dialogue(10, 15, spans) is True
    assert _is_span_in_dialogue(0, 5, spans) is False


def test_graceful_degradation_without_java() -> None:
    """When Java or LanguageTool fails to initialize, return [] without crashing."""
    with patch("qifrey.grammar.checker.get_language_tool", return_value=None):
        issues = check_grammar("This are bad grammar.")
        assert issues == []


def test_grammar_checker_with_mocked_languagetool() -> None:
    """Verify offset extraction, suggestions, and fiction-friendly rule filtering."""
    mock_match_1 = MagicMock()
    mock_match_1.ruleId = "UPPERCASE_SENTENCE_START"  # In default disabled list
    mock_match_1.offset = 0
    mock_match_1.errorLength = 4
    mock_match_1.message = "Sentence should start with uppercase"
    mock_match_1.replacements = ["This"]

    mock_match_2 = MagicMock()
    mock_match_2.ruleId = "EN_A_VS_AN"
    mock_match_2.offset = 5
    mock_match_2.errorLength = 1
    mock_match_2.message = "Use 'an' instead of 'a'"
    mock_match_2.replacements = ["an"]

    mock_tool = MagicMock()
    mock_tool.check.return_value = [mock_match_1, mock_match_2]

    with patch("qifrey.grammar.checker.get_language_tool", return_value=mock_tool):
        text = "this a apple."
        issues = check_grammar(text)

        # UPPERCASE_SENTENCE_START was filtered out by disabled_rules
        assert len(issues) == 1
        assert issues[0].rule_id == "EN_A_VS_AN"
        assert issues[0].span_start == 5
        assert issues[0].span_end == 6
        assert issues[0].quote == "a"
        assert "an" in issues[0].suggestions


@pytest.mark.skipif(not _has_java(), reason="Java runtime not installed on host machine")
def test_live_languagetool() -> None:
    """Only runs when a live Java runtime is available."""
    text = "She has an car."
    issues = check_grammar(text)
    assert len(issues) >= 1
    assert any("car" in i.quote or "an" in i.quote for i in issues)
