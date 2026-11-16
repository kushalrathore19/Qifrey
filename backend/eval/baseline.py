"""Naive baseline extraction using spaCy NER (optional) or capitalized-word heuristic."""

from __future__ import annotations

import collections
import re
from typing import Any

from eval.metrics import MetricScore, evaluate_characters, evaluate_locations

# Common non-name capitalized sentence starters
STOP_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "but",
        "or",
        "if",
        "then",
        "so",
        "as",
        "at",
        "by",
        "for",
        "in",
        "of",
        "on",
        "to",
        "with",
        "he",
        "she",
        "it",
        "they",
        "we",
        "i",
        "you",
        "his",
        "her",
        "their",
        "my",
        "your",
        "its",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "when",
        "where",
        "why",
        "how",
        "what",
        "who",
        "after",
        "before",
        "while",
        "during",
        "soon",
        "later",
        "suddenly",
        "meanwhile",
        "once",
        "long",
        "one",
        "first",
        "last",
        "next",
        "chapter",
        "part",
        "act",
    }
)

LOCATION_CLUES: frozenset[str] = frozenset(
    {
        "hall",
        "atelier",
        "castle",
        "tower",
        "city",
        "town",
        "village",
        "room",
        "chamber",
        "palace",
        "forest",
        "river",
        "mountain",
        "street",
        "house",
        "temple",
        "garden",
    }
)

TITLE_CLUES: frozenset[str] = frozenset(
    {
        "master",
        "lord",
        "lady",
        "sir",
        "dr",
        "prof",
        "professor",
        "warden",
        "captain",
        "king",
        "queen",
    }
)

_spacy_nlp: Any = None
_spacy_checked: bool = False


def _get_spacy_model() -> Any:
    """Attempt to load spacy en_core_web_sm if installed."""
    global _spacy_nlp, _spacy_checked
    if _spacy_checked:
        return _spacy_nlp
    _spacy_checked = True
    try:
        import spacy  # noqa: PLC0415

        try:
            _spacy_nlp = spacy.load("en_core_web_sm")
        except Exception:
            _spacy_nlp = None
    except ImportError:
        _spacy_nlp = None
    return _spacy_nlp


def extract_baseline(text: str) -> dict[str, list[dict[str, Any]]]:
    """Extract characters and locations using spaCy or capitalized regex frequency."""
    nlp = _get_spacy_model()
    if nlp is not None:
        return _extract_spacy(text, nlp)
    return _extract_heuristic(text)


def _extract_spacy(text: str, nlp: Any) -> dict[str, list[dict[str, Any]]]:
    """Extract entities via spaCy NER."""
    doc = nlp(text)
    characters: list[dict[str, Any]] = []
    locations: list[dict[str, Any]] = []

    seen_chars: set[str] = set()
    seen_locs: set[str] = set()

    for ent in doc.ents:
        clean_text = ent.text.strip()
        if not clean_text:
            continue
        if ent.label_ == "PERSON":
            norm = clean_text.lower()
            if norm not in seen_chars:
                seen_chars.add(norm)
                characters.append({"canonical_name": clean_text, "aliases": []})
        elif ent.label_ in ("GPE", "LOC", "FAC"):
            norm = clean_text.lower()
            if norm not in seen_locs:
                seen_locs.add(norm)
                locations.append({"name": clean_text})

    return {"characters": characters, "locations": locations}


def _extract_heuristic(text: str) -> dict[str, list[dict[str, Any]]]:
    """Heuristic capitalized entity extraction when spaCy is unavailable."""
    # Pattern for capitalized word sequences
    pattern = r"\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b"
    candidates = re.findall(pattern, text)

    char_counts: collections.Counter[str] = collections.Counter()
    loc_counts: collections.Counter[str] = collections.Counter()

    for cand in candidates:
        tokens = [t.lower() for t in cand.split()]
        if all(t in STOP_WORDS for t in tokens):
            continue

        # Check if candidate mentions location clues
        if any(clue in tokens for clue in LOCATION_CLUES):
            loc_counts[cand] += 1
        # Check if candidate begins with title or appears like a person name
        elif any(t in TITLE_CLUES for t in tokens) or len(tokens) <= 3:
            char_counts[cand] += 1
        else:
            char_counts[cand] += 1

    # Format result
    characters: list[dict[str, Any]] = []
    locations: list[dict[str, Any]] = []

    for name, _ in char_counts.most_common(20):
        # Filter single lowercase stop words that were capitalized at sentence start
        if name.lower() in STOP_WORDS:
            continue
        characters.append({"canonical_name": name, "aliases": []})

    for loc, _ in loc_counts.most_common(10):
        locations.append({"name": loc})

    return {"characters": characters, "locations": locations}


def run_baseline_on_gold(gold_data: dict[str, Any]) -> dict[str, MetricScore]:
    """Run the baseline on a gold story and compute its metrics."""
    # Concatenate all chapter text
    full_text = "\n\n".join(ch.get("text", "") for ch in gold_data.get("chapters", []))
    baseline_extractions = extract_baseline(full_text)

    # Collect all gold characters and locations
    gold_chars: list[dict[str, Any]] = []
    gold_locs: list[dict[str, Any]] = []
    seen_char_names: set[str] = set()
    seen_loc_names: set[str] = set()

    for ch in gold_data.get("chapters", []):
        for c in ch.get("characters", []):
            c_name = c.get("canonical_name", "").lower()
            if c_name not in seen_char_names:
                seen_char_names.add(c_name)
                gold_chars.append(c)
        for loc in ch.get("locations", []):
            loc_name = (loc.get("name") if isinstance(loc, dict) else str(loc)).lower()
            if loc_name not in seen_loc_names:
                seen_loc_names.add(loc_name)
                gold_locs.append(loc if isinstance(loc, dict) else {"name": loc})

    char_score, _ = evaluate_characters(gold_chars, baseline_extractions["characters"])
    loc_score = evaluate_locations(gold_locs, baseline_extractions["locations"])

    return {
        "characters": char_score,
        "locations": loc_score,
    }
