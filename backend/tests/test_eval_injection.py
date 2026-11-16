"""Tests for programmatic contradiction injection and legitimate change controls."""

from __future__ import annotations

from eval.inject_contradictions import (
    evaluate_contradiction_detection,
    inject_contradictions,
)


class TestContradictionInjection:
    def test_inject_contradiction(self) -> None:
        story = {
            "title": "Clean Story",
            "chapters": [
                {
                    "index": 1,
                    "text": "Qifrey has bright green eyes.",
                    "facts": [
                        {
                            "character": "Qifrey",
                            "attribute": "eye_color",
                            "value": "green",
                        }
                    ],
                },
                {
                    "index": 2,
                    "text": "The next morning, Qifrey walked outside.",
                    "facts": [],
                },
            ],
        }

        mod_story, answer_key = inject_contradictions(
            story,
            n=1,
            include_legitimate_changes=True,
            seed=42,
        )

        assert len(answer_key) >= 1
        # Contradiction planted in chapter 2 text
        contradictions = [k for k in answer_key if k["type"] == "contradiction"]
        assert len(contradictions) == 1
        assert "eyes" in mod_story["chapters"][1]["text"].lower()

        # Legitimate change planted
        legit = [k for k in answer_key if k["type"] == "legitimate_change"]
        assert len(legit) == 1

    def test_evaluate_contradiction_detection_clean(self) -> None:
        answer_key = [
            {
                "type": "contradiction",
                "character": "Qifrey",
                "attribute": "eye_color",
                "original_value": "green",
                "new_value": "blue",
            },
            {
                "type": "legitimate_change",
                "character": "Qifrey",
                "attribute": "home_location",
            },
        ]

        # Detector caught the eye_color contradiction and did NOT flag the legitimate change
        detected_issues = [
            {
                "type": "contradiction",
                "message": "Contradiction: Qifrey eye_color changed from green to blue.",
                "quote": "blue eyes",
            }
        ]

        eval_res = evaluate_contradiction_detection(detected_issues, answer_key)
        assert eval_res["detected_tp"] == 1
        assert eval_res["false_positives"] == 0
        assert eval_res["false_negatives"] == 0
        assert eval_res["false_positives_on_legitimate"] == 0
        assert eval_res["metrics"].f1 == 1.0
