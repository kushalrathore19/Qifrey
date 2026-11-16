"""Tests for the end-to-end evaluation runner and reporting."""

from __future__ import annotations

import json
from pathlib import Path

from eval.run_eval import (
    _build_fake_responses_from_gold,
    evaluate_gold_file,
    write_reports,
)

from qifrey.pipeline.llm_client import FakeLLMClient


class TestEvalRun:
    def test_end_to_end_evaluation_with_fake_llm(self, tmp_path: Path) -> None:
        gold_file = Path("eval/gold/example_story.json")
        if not gold_file.exists():
            # In case running from root or backend
            gold_file = Path(__file__).resolve().parent.parent / "eval/gold/example_story.json"

        with gold_file.open("r", encoding="utf-8") as f:
            gold_data = json.load(f)

        fake_responses = _build_fake_responses_from_gold(gold_data)
        client = FakeLLMClient(responses=fake_responses)

        res = evaluate_gold_file(gold_file, client)
        assert res["story_title"] == "The Warden of Silver"
        assert res["metrics"]["characters"].f1 == 1.0
        assert res["metrics"]["locations"].f1 == 1.0
        assert res["metrics"]["facts"].f1 == 1.0
        assert res["metrics"]["contradictions"].f1 == 1.0
        assert res["usage"]["total_calls"] > 0
        assert res["usage"]["estimated_cost_usd"] >= 0.0

        # Test writing report files
        out_dir = tmp_path / "reports"
        md_path, csv_path = write_reports([res], out_dir)
        assert md_path.exists()
        assert csv_path.exists()

        md_content = md_path.read_text(encoding="utf-8")
        assert "Qifrey Evaluation Report" in md_content
        assert "Estimated Cost" in md_content
        assert "Qifrey vs Naive Baseline" in md_content

        csv_content = csv_path.read_text(encoding="utf-8")
        assert "timestamp,story,entity_task,precision,recall,f1" in csv_content
