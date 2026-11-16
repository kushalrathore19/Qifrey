"""Tests for evaluation metrics: fuzzy matching, alias-awareness, precision, recall, and F1."""

from __future__ import annotations

import pytest
from eval.metrics import (
    compute_metric_score,
    evaluate_aliases,
    evaluate_characters,
    evaluate_contradictions,
    evaluate_facts,
    evaluate_locations,
    match_character_alias_aware,
    match_names,
    normalize_name,
    token_overlap_ratio,
)


class TestNameNormalizationAndMatching:
    def test_normalize_name_strips_honorifics(self) -> None:
        assert normalize_name("Master Qifrey") == "qifrey"
        assert normalize_name("Lord Voldemort") == "voldemort"
        assert normalize_name("Dr. Watson") == "watson"
        assert normalize_name("The Warden of Silver") == "warden of silver"

    def test_token_overlap_ratio(self) -> None:
        assert token_overlap_ratio("warden silver", "warden silver") == 1.0
        assert token_overlap_ratio("warden silver", "warden") == 0.5
        assert token_overlap_ratio("apple", "banana") == 0.0

    def test_match_names(self) -> None:
        assert match_names("Master Qifrey", "Qifrey") is True
        assert match_names("Qifrey", "Qifrey") is True
        assert match_names("The Warden of Silver", "Warden of Silver") is True
        assert match_names("Sherlock Holmes", "Holmes") is True
        assert match_names("Alice", "Bob") is False

    def test_match_character_alias_aware(self) -> None:
        gold_canonical = "Qifrey"
        gold_aliases = ["The Warden of Silver", "Master Qifrey"]

        assert match_character_alias_aware("Qifrey", gold_canonical, gold_aliases) is True
        assert match_character_alias_aware("The Warden", gold_canonical, gold_aliases) is True
        assert match_character_alias_aware("Master Qifrey", gold_canonical, gold_aliases) is True
        assert match_character_alias_aware("Coco", gold_canonical, gold_aliases) is False


class TestMetricComputations:
    def test_compute_metric_score(self) -> None:
        score = compute_metric_score(tp=4, fp=1, fn=1)
        assert score.precision == 4 / 5  # 0.8
        assert score.recall == 4 / 5  # 0.8
        assert score.f1 == pytest.approx(0.8)
        assert score.tp == 4
        assert score.fp == 1
        assert score.fn == 1

    def test_zero_division_safety(self) -> None:
        score = compute_metric_score(tp=0, fp=0, fn=0)
        assert score.f1 == 1.0 or score.f1 == 0.0


class TestEntityEvaluations:
    def test_evaluate_characters(self) -> None:
        gold = [
            {"canonical_name": "Qifrey", "aliases": ["Warden"]},
            {"canonical_name": "Coco", "aliases": []},
        ]
        extracted = [
            {"canonical_name": "Master Qifrey", "aliases": []},
            {"canonical_name": "Agott", "aliases": []},
        ]
        score, mapping = evaluate_characters(gold, extracted)
        # Qifrey matched -> TP=1, Coco missed -> FN=1, Agott extra -> FP=1
        assert score.tp == 1
        assert score.fn == 1
        assert score.fp == 1
        assert score.precision == 0.5
        assert score.recall == 0.5
        assert 0 in mapping

    def test_evaluate_aliases(self) -> None:
        gold = [{"canonical_name": "Qifrey", "aliases": ["Warden", "Teacher"]}]
        extracted = [{"canonical_name": "Qifrey", "aliases": ["Warden", "Magician"]}]
        gold_to_ext = {0: 0}
        score = evaluate_aliases(gold, extracted, gold_to_ext)
        # Warden matches -> TP=1, Teacher missing -> FN=1, Magician extra -> FP=1
        assert score.tp == 1
        assert score.fn == 1
        assert score.fp == 1

    def test_evaluate_locations(self) -> None:
        gold = [{"name": "The Atelier"}, {"name": "Great Hall"}]
        extracted = [{"name": "Atelier"}, {"name": "Forest of Doubt"}]
        score = evaluate_locations(gold, extracted)
        # Atelier matches -> TP=1, Great Hall missing -> FN=1, Forest extra -> FP=1
        assert score.tp == 1
        assert score.fn == 1
        assert score.fp == 1

    def test_evaluate_facts(self) -> None:
        gold_chars = [{"canonical_name": "Qifrey", "aliases": ["Master Qifrey"]}]
        gold_facts = [
            {"character": "Qifrey", "attribute": "eye_color", "value": "silver"},
            {"character": "Qifrey", "attribute": "occupation", "value": "teacher"},
        ]
        extracted_facts = [
            {"character": "Master Qifrey", "attribute": "other:eye_color", "value": "silver eyes"},
            {"character": "Master Qifrey", "attribute": "wand_color", "value": "silver"},
        ]
        score = evaluate_facts(gold_facts, extracted_facts, gold_chars)
        # eye_color matches with normalized other: prefix and silver value -> TP=1
        assert score.tp == 1
        assert score.fn == 1
        assert score.fp == 1

    def test_evaluate_contradictions(self) -> None:
        gold_contradictions = [
            {
                "character": "Qifrey",
                "attribute": "eye_color",
                "value_a": "silver",
                "value_b": "dark",
            }
        ]
        detected = [
            {
                "type": "contradiction",
                "message": "Contradiction found for Qifrey: eye_color was silver but later dark.",
                "quote": "dark eyes",
            }
        ]
        score = evaluate_contradictions(gold_contradictions, detected)
        assert score.tp == 1
        assert score.fp == 0
        assert score.fn == 0
        assert score.f1 == 1.0
