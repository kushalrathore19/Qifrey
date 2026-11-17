"""Validation engine for extracted narrative elements."""

from __future__ import annotations

import difflib
import logging
from typing import Any

from pydantic import ValidationError

from qifrey.pipeline.schemas import (
    CharacterExtraction,
    ExtractionOutput,
    FactExtraction,
    LocationExtraction,
    RelationshipExtraction,
    ValidationResult,
)

logger = logging.getLogger(__name__)


def quote_match_ratio(quote: str, text: str) -> float:
    """Calculate the best match ratio (0.0 to 1.0) of a quote against the text."""
    clean_quote = " ".join(quote.strip().lower().split())
    clean_text = " ".join(text.strip().lower().split())

    if not clean_quote:
        return 0.0

    if clean_quote in clean_text:
        return 1.0

    quote_words = clean_quote.split()
    text_words = clean_text.split()
    k = len(quote_words)
    if k == 0 or len(text_words) == 0:
        return 0.0

    # Locate candidate start positions in text matching anchor words
    first_w = quote_words[0]
    candidate_indices = [
        i for i, w in enumerate(text_words) if w == first_w or (len(w) > 3 and first_w in w)
    ]

    # If first word had no hits, try middle or last word
    if not candidate_indices and k > 1:
        mid_w = quote_words[k // 2]
        candidate_indices = [
            max(0, i - (k // 2))
            for i, w in enumerate(text_words)
            if w == mid_w or (len(w) > 3 and mid_w in w)
        ]

    # If still none, sample across the text
    if not candidate_indices:
        step = max(1, k // 2)
        candidate_indices = list(range(0, len(text_words), step))

    best_ratio = 0.0
    for idx in candidate_indices:
        for offset in (0, -1, 1, -2, 2):
            w_len = k + offset
            if w_len <= 0 or idx + w_len > len(text_words) + 1:
                continue
            candidate_str = " ".join(text_words[idx : idx + w_len])
            ratio = difflib.SequenceMatcher(None, clean_quote, candidate_str).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                if best_ratio >= 0.95:
                    return best_ratio

    return best_ratio


def validate_extraction(
    raw_data: ExtractionOutput | dict[str, Any],
    chapter_text: str,
    *,
    min_quote_ratio: float = 0.85,
    min_confidence: float = 0.5,
    confidence_threshold: float | None = None,
    ignored_names: set[str] | None = None,
) -> ValidationResult:
    """Validate extracted items against chapter text, confidence threshold, and duplicate checks.

    Rejection criteria:
    (a) Fails schema
    (b) Evidence quote not found in chapter text (ratio < 0.85)
    (c) Confidence < min_confidence
    (d) Exact duplicate
    (e) Matches IgnoredName
    """
    if confidence_threshold is not None:
        min_confidence = confidence_threshold

    rejections: list[dict[str, str]] = []
    ignored = {n.strip().lower() for n in ignored_names} if ignored_names else set()

    # (a) Schema validation
    if isinstance(raw_data, ExtractionOutput):
        parsed = raw_data
    else:
        try:
            parsed = ExtractionOutput.model_validate(raw_data)
        except ValidationError as err:
            rejections.append(
                {
                    "item_type": "extraction_output",
                    "item": str(raw_data)[:200],
                    "reason": f"Schema validation error: {err}",
                }
            )
            return ValidationResult(rejections=rejections)

    # Validate characters
    accepted_chars: list[CharacterExtraction] = []
    seen_char_names: set[str] = set()
    for char in parsed.characters:
        name_key = char.name.strip().lower()
        if not name_key:
            rejections.append(
                {
                    "item_type": "character",
                    "item": str(char),
                    "reason": "Empty character name",
                }
            )
            continue

        if name_key in ignored:
            rejections.append(
                {
                    "item_type": "character",
                    "item": char.name,
                    "reason": f"Character '{char.name}' is on the ignored names list",
                }
            )
            continue

        if name_key in seen_char_names:
            rejections.append(
                {
                    "item_type": "character",
                    "item": char.name,
                    "reason": f"Duplicate character '{char.name}' in extraction",
                }
            )
            continue

        if char.evidence_quote:
            ratio = quote_match_ratio(char.evidence_quote, chapter_text)
            if ratio < min_quote_ratio:
                rejections.append(
                    {
                        "item_type": "character",
                        "item": char.name,
                        "reason": (
                            f"Evidence quote not found in chapter "
                            f"(ratio {ratio:.2f} < {min_quote_ratio})"
                        ),
                    }
                )
                continue

        seen_char_names.add(name_key)
        accepted_chars.append(char)

    # Validate locations
    accepted_locs: list[LocationExtraction] = []
    seen_loc_names: set[str] = set()
    for loc in parsed.locations:
        loc_key = loc.name.strip().lower()
        if not loc_key:
            rejections.append(
                {
                    "item_type": "location",
                    "item": str(loc),
                    "reason": "Empty location name",
                }
            )
            continue

        if loc_key in seen_loc_names:
            rejections.append(
                {
                    "item_type": "location",
                    "item": loc.name,
                    "reason": f"Duplicate location '{loc.name}' in extraction",
                }
            )
            continue

        seen_loc_names.add(loc_key)
        accepted_locs.append(loc)

    # Validate facts
    accepted_facts: list[FactExtraction] = []
    seen_facts: set[tuple[str, str, str]] = set()
    for fact in parsed.facts:
        # Confidence check
        if fact.confidence < min_confidence:
            rejections.append(
                {
                    "item_type": "fact",
                    "item": f"{fact.character}: {fact.attribute}={fact.value}",
                    "reason": f"Confidence {fact.confidence:.2f} below threshold {min_confidence}",
                }
            )
            continue

        # Quote verification
        ratio = quote_match_ratio(fact.evidence_quote, chapter_text)
        if ratio < min_quote_ratio:
            rejections.append(
                {
                    "item_type": "fact",
                    "item": f"{fact.character}: {fact.attribute}={fact.value}",
                    "reason": (
                        f"Evidence quote not found in text (ratio {ratio:.2f} < {min_quote_ratio})"
                    ),
                }
            )
            continue

        # Duplicate check
        fact_key = (
            fact.character.strip().lower(),
            fact.attribute.strip().lower(),
            fact.value.strip().lower(),
        )
        if fact_key in seen_facts:
            rejections.append(
                {
                    "item_type": "fact",
                    "item": f"{fact.character}: {fact.attribute}={fact.value}",
                    "reason": f"Duplicate fact '{fact.character}: {fact.attribute}={fact.value}'",
                }
            )
            continue

        seen_facts.add(fact_key)
        accepted_facts.append(fact)

    # Validate relationships
    accepted_rels: list[RelationshipExtraction] = []
    seen_rels: set[tuple[str, str, str]] = set()
    for rel in parsed.relationships:
        if not rel.a.strip() or not rel.b.strip():
            rejections.append(
                {
                    "item_type": "relationship",
                    "item": f"{rel.a} <-> {rel.b}",
                    "reason": "Missing character in relationship",
                }
            )
            continue

        # Quote verification if quote provided
        if rel.evidence_quote:
            ratio = quote_match_ratio(rel.evidence_quote, chapter_text)
            if ratio < min_quote_ratio:
                rejections.append(
                    {
                        "item_type": "relationship",
                        "item": f"{rel.a} - {rel.b} ({rel.type})",
                        "reason": (
                            f"Evidence quote not found in text "
                            f"(ratio {ratio:.2f} < {min_quote_ratio})"
                        ),
                    }
                )
                continue

        # Undirected pair duplicate check
        a_key, b_key = sorted([rel.a.strip().lower(), rel.b.strip().lower()])
        rel_key = (a_key, b_key, rel.type.strip().lower())
        if rel_key in seen_rels:
            rejections.append(
                {
                    "item_type": "relationship",
                    "item": f"{rel.a} - {rel.b} ({rel.type})",
                    "reason": f"Duplicate relationship '{rel.a} - {rel.b} ({rel.type})'",
                }
            )
            continue

        seen_rels.add(rel_key)
        accepted_rels.append(rel)

    for rej in rejections:
        logger.info("Validation rejected %s: %s", rej.get("item"), rej.get("reason"))

    return ValidationResult(
        accepted_characters=accepted_chars,
        accepted_locations=accepted_locs,
        accepted_facts=accepted_facts,
        accepted_relationships=accepted_rels,
        rejections=rejections,
    )
