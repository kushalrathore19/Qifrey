"""Tests for the extraction validator."""

from __future__ import annotations

from qifrey.pipeline.schemas import (
    CharacterExtraction,
    ExtractionOutput,
    FactExtraction,
    LocationExtraction,
    RelationshipExtraction,
)
from qifrey.pipeline.validator import quote_match_ratio, validate_extraction

SAMPLE_TEXT = (
    "Sarah Mitchell was thirty-four years old and possessed startling violet eyes. "
    "She lived in a secluded stone cottage near the misty harbor of Dunhaven. "
    "Her apprentice, young Toby, was fiercely loyal to her."
)


def test_quote_match_ratio() -> None:
    # Exact substring
    assert quote_match_ratio("startling violet eyes", SAMPLE_TEXT) == 1.0

    # Near exact with punctuation/casing
    assert quote_match_ratio("startling violet eyes.", SAMPLE_TEXT) >= 0.95

    # Completely hallucinated
    assert quote_match_ratio("she drove a neon green sports car", SAMPLE_TEXT) < 0.5


def test_validator_rejects_hallucinated_quote() -> None:
    extraction = ExtractionOutput(
        facts=[
            FactExtraction(
                character="Sarah",
                attribute="eye_color",
                value="violet",
                evidence_quote="possessed startling violet eyes",
                confidence=0.95,
            ),
            FactExtraction(
                character="Sarah",
                attribute="hair_color",
                value="raven black",
                evidence_quote="her hair was dark as midnight shadow",  # Not in text!
                confidence=0.9,
            ),
        ]
    )

    result = validate_extraction(extraction, SAMPLE_TEXT)
    assert len(result.accepted_facts) == 1
    assert result.accepted_facts[0].attribute == "eye_color"
    assert len(result.rejections) == 1
    assert "not found" in result.rejections[0]["reason"].lower()


def test_validator_rejects_low_confidence() -> None:
    extraction = ExtractionOutput(
        facts=[
            FactExtraction(
                character="Sarah",
                attribute="age",
                value="34",
                evidence_quote="thirty-four years old",
                confidence=0.4,  # Below 0.5
            )
        ]
    )

    result = validate_extraction(extraction, SAMPLE_TEXT)
    assert len(result.accepted_facts) == 0
    assert len(result.rejections) == 1
    assert "confidence" in result.rejections[0]["reason"].lower()


def test_validator_rejects_duplicates() -> None:
    extraction = ExtractionOutput(
        facts=[
            FactExtraction(
                character="Sarah",
                attribute="eye_color",
                value="violet",
                evidence_quote="startling violet eyes",
                confidence=0.9,
            ),
            FactExtraction(
                character="sarah",
                attribute="eye_color",
                value="violet",
                evidence_quote="startling violet eyes",
                confidence=0.9,
            ),
        ],
        relationships=[
            RelationshipExtraction(
                a="Sarah", b="Toby", type="mentor", evidence_quote="apprentice, young Toby"
            ),
            RelationshipExtraction(
                a="Toby", b="Sarah", type="mentor", evidence_quote="apprentice, young Toby"
            ),
        ],
    )

    result = validate_extraction(extraction, SAMPLE_TEXT)
    assert len(result.accepted_facts) == 1
    assert len(result.accepted_relationships) == 1
    assert any("duplicate" in r["reason"].lower() for r in result.rejections)


def test_validator_handles_locations_and_characters() -> None:
    extraction = ExtractionOutput(
        characters=[
            CharacterExtraction(
                name="Sarah Mitchell", description="Scholar", evidence_quote="Sarah Mitchell was"
            ),
        ],
        locations=[
            LocationExtraction(name="Dunhaven", description="Misty harbor"),
        ],
    )

    result = validate_extraction(extraction, SAMPLE_TEXT)
    assert len(result.accepted_characters) == 1
    assert len(result.accepted_locations) == 1
