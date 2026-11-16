"""Unit tests for LLMClient and JSON extraction/repair."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from qifrey.pipeline.llm_client import (
    AnthropicClient,
    FakeLLMClient,
    _compute_prompt_hash,
    _extract_json_text,
)


class SampleModel(BaseModel):
    name: str
    count: int


def test_extract_json_text() -> None:
    raw_plain = '{"name": "test", "count": 1}'
    assert _extract_json_text(raw_plain) == raw_plain

    raw_markdown = '```json\n{"name": "test", "count": 2}\n```'
    assert _extract_json_text(raw_markdown) == '{"name": "test", "count": 2}'

    raw_fenced = '```\n{"name": "test", "count": 3}\n```'
    assert _extract_json_text(raw_fenced) == '{"name": "test", "count": 3}'


def test_compute_prompt_hash() -> None:
    h1 = _compute_prompt_hash("sys", "usr")
    h2 = _compute_prompt_hash("sys", "usr")
    h3 = _compute_prompt_hash("sys", "diff")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_fake_llm_client_history_and_canned_responses() -> None:
    client = FakeLLMClient(
        responses=[
            SampleModel(name="Alice", count=10),
            {"name": "Bob", "count": 20},
        ]
    )

    r1 = client.complete_json("sys", "user1", SampleModel)
    assert r1.name == "Alice"
    assert r1.count == 10

    r2 = client.complete_json("sys", "user2", SampleModel)
    assert r2.name == "Bob"
    assert r2.count == 20

    assert len(client.history) == 2


def test_anthropic_client_repair_flow() -> None:
    """When the first response is invalid JSON, AnthropicClient should make a repair call."""
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_instance = MagicMock()
        mock_anthropic.return_value = mock_instance

        # Response 1: invalid json
        mock_block_1 = MagicMock()
        mock_block_1.type = "text"
        mock_block_1.text = "Here is your JSON: not a json string"
        mock_resp_1 = MagicMock()
        mock_resp_1.content = [mock_block_1]
        mock_resp_1.usage.input_tokens = 100
        mock_resp_1.usage.output_tokens = 10

        # Response 2 (repair): valid json
        mock_block_2 = MagicMock()
        mock_block_2.type = "text"
        mock_block_2.text = '{"name": "Repaired", "count": 99}'
        mock_resp_2 = MagicMock()
        mock_resp_2.content = [mock_block_2]
        mock_resp_2.usage.input_tokens = 150
        mock_resp_2.usage.output_tokens = 20

        mock_instance.messages.create.side_effect = [mock_resp_1, mock_resp_2]

        client = AnthropicClient(api_key="test-key", model="claude-test")
        result = client.complete_json("System prompt", "User prompt", SampleModel)

        assert result.name == "Repaired"
        assert result.count == 99
        assert mock_instance.messages.create.call_count == 2
