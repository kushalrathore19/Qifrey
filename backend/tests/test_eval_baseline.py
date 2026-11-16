"""Tests for baseline entity extraction."""

from __future__ import annotations

from eval.baseline import extract_baseline, run_baseline_on_gold


class TestBaselineExtraction:
    def test_extract_baseline_heuristic(self) -> None:
        text = (
            "Master Qifrey walked into the Atelier. Later, Lord Beldaruit visited the Great Hall."
        )
        result = extract_baseline(text)
        assert "characters" in result
        assert "locations" in result

        char_names = [c["canonical_name"] for c in result["characters"]]
        assert any("Qifrey" in name for name in char_names)

        loc_names = [loc["name"] for loc in result["locations"]]
        assert any("Atelier" in name or "Hall" in name for name in loc_names)

    def test_run_baseline_on_gold(self) -> None:
        gold_data = {
            "title": "Sample Gold",
            "chapters": [
                {
                    "index": 1,
                    "text": "Master Qifrey studied at the Atelier.",
                    "characters": [{"canonical_name": "Qifrey", "aliases": ["Master Qifrey"]}],
                    "locations": [{"name": "Atelier"}],
                }
            ],
        }
        scores = run_baseline_on_gold(gold_data)
        assert "characters" in scores
        assert "locations" in scores
        assert scores["characters"].tp >= 1
        assert scores["locations"].tp >= 1
