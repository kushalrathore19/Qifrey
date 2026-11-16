"""Evaluation metrics calculation: precision, recall, and F1 for extraction and insights.

Matching is alias-aware and fuzzy for names (normalizes case/honorifics with configurable
token overlap).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Common honorifics and titles to strip during normalization
HONORIFICS: frozenset[str] = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "miss",
        "dr",
        "prof",
        "professor",
        "sir",
        "lady",
        "lord",
        "master",
        "captain",
        "count",
        "countess",
        "king",
        "queen",
        "prince",
        "princess",
        "the",
    }
)


def normalize_string(text: str) -> str:
    """Lowercase, strip non-alphanumeric punctuation (keeping whitespace), and trim."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(cleaned.split())


def normalize_name(name: str) -> str:
    """Normalize a name by lowering case, removing punctuation, and stripping honorifics."""
    tokens = normalize_string(name).split()
    filtered = [t for t in tokens if t not in HONORIFICS]
    return " ".join(filtered) if filtered else " ".join(tokens)


def token_overlap_ratio(str_a: str, str_b: str) -> float:
    """Compute Jaccard token overlap between two strings."""
    tokens_a = set(str_a.split())
    tokens_b = set(str_b.split())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def match_names(name_a: str, name_b: str, threshold: float = 0.6) -> bool:
    """Check if two names match using normalization, containment, or token overlap."""
    norm_a = normalize_name(name_a)
    norm_b = normalize_name(name_b)

    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    if norm_a in norm_b or norm_b in norm_a:
        return True

    return token_overlap_ratio(norm_a, norm_b) >= threshold


def match_character_alias_aware(
    candidate_name: str,
    gold_canonical: str,
    gold_aliases: list[str],
    threshold: float = 0.6,
) -> bool:
    """Match candidate against canonical name or any gold alias."""
    if match_names(candidate_name, gold_canonical, threshold):
        return True
    return any(match_names(candidate_name, alias, threshold) for alias in gold_aliases)


@dataclass
class MetricScore:
    """Precision, recall, and F1 score along with raw confusion matrix counts."""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
        }


def compute_metric_score(tp: int, fp: int, fn: int) -> MetricScore:
    """Calculate precision, recall, and F1 from TP, FP, FN."""
    precision = round(tp / (tp + fp), 6) if (tp + fp) > 0 else (1.0 if fn == 0 else 0.0)
    recall = round(tp / (tp + fn), 6) if (tp + fn) > 0 else (1.0 if fp == 0 else 0.0)
    if precision + recall > 0:
        f1 = round(2 * (precision * recall) / (precision + recall), 6)
    else:
        f1 = 0.0
    return MetricScore(
        precision=precision,
        recall=recall,
        f1=f1,
        tp=tp,
        fp=fp,
        fn=fn,
    )


def evaluate_characters(
    gold_characters: list[dict[str, Any]],
    extracted_characters: list[dict[str, Any]],
    threshold: float = 0.6,
) -> tuple[MetricScore, dict[int, int]]:
    """Evaluate character extraction. Returns (MetricScore, gold_to_extracted_mapping)."""
    matched_extracted: set[int] = set()
    gold_to_extracted: dict[int, int] = {}

    tp = 0
    for g_idx, gold_char in enumerate(gold_characters):
        g_name = gold_char.get("canonical_name", "")
        g_aliases = gold_char.get("aliases", [])

        match_found = False
        for e_idx, ext_char in enumerate(extracted_characters):
            if e_idx in matched_extracted:
                continue
            e_name = ext_char.get("canonical_name") or ext_char.get("name", "")
            e_aliases = ext_char.get("aliases", [])

            # Match canonical or aliases symmetrically
            if match_character_alias_aware(e_name, g_name, g_aliases, threshold):
                matched_extracted.add(e_idx)
                gold_to_extracted[g_idx] = e_idx
                tp += 1
                match_found = True
                break
            # Check if any extracted alias matches gold canonical
            for e_al in e_aliases:
                if match_character_alias_aware(e_al, g_name, g_aliases, threshold):
                    matched_extracted.add(e_idx)
                    gold_to_extracted[g_idx] = e_idx
                    tp += 1
                    match_found = True
                    break
            if match_found:
                break

    fn = len(gold_characters) - tp
    fp = len(extracted_characters) - len(matched_extracted)
    score = compute_metric_score(tp, fp, fn)
    return score, gold_to_extracted


def evaluate_aliases(
    gold_characters: list[dict[str, Any]],
    extracted_characters: list[dict[str, Any]],
    gold_to_extracted: dict[int, int],
    threshold: float = 0.6,
) -> MetricScore:
    """Evaluate alias extraction for matched characters."""
    total_tp = 0
    total_fp = 0
    total_fn = 0

    for g_idx, gold_char in enumerate(gold_characters):
        g_aliases = [normalize_name(a) for a in gold_char.get("aliases", [])]
        e_idx = gold_to_extracted.get(g_idx)
        if e_idx is not None and e_idx < len(extracted_characters):
            e_char = extracted_characters[e_idx]
            e_aliases = [
                normalize_name(a)
                for a in e_char.get("aliases", [])
                if normalize_name(a) != normalize_name(e_char.get("canonical_name", ""))
            ]
        else:
            e_aliases = []

        matched_e_aliases: set[int] = set()
        char_tp = 0
        for g_al in g_aliases:
            found = False
            for al_idx, e_al in enumerate(e_aliases):
                if al_idx in matched_e_aliases:
                    continue
                if match_names(g_al, e_al, threshold):
                    matched_e_aliases.add(al_idx)
                    char_tp += 1
                    found = True
                    break
            if not found:
                pass

        char_fn = len(g_aliases) - char_tp
        char_fp = len(e_aliases) - len(matched_e_aliases)

        total_tp += char_tp
        total_fn += char_fn
        total_fp += char_fp

    return compute_metric_score(total_tp, total_fp, total_fn)


def evaluate_locations(
    gold_locations: list[dict[str, Any] | str],
    extracted_locations: list[dict[str, Any] | str],
    threshold: float = 0.6,
) -> MetricScore:
    """Evaluate location extraction with fuzzy matching."""
    g_names = [
        loc.get("name", "") if isinstance(loc, dict) else str(loc) for loc in gold_locations
    ]
    e_names = [
        loc.get("name", "") if isinstance(loc, dict) else str(loc) for loc in extracted_locations
    ]

    matched_e: set[int] = set()
    tp = 0
    for g_name in g_names:
        for e_idx, e_name in enumerate(e_names):
            if e_idx in matched_e:
                continue
            if match_names(g_name, e_name, threshold):
                matched_e.add(e_idx)
                tp += 1
                break

    fn = len(g_names) - tp
    fp = len(e_names) - len(matched_e)
    return compute_metric_score(tp, fp, fn)


def _normalize_attribute(attr: str) -> str:
    """Normalize attribute name (strip other: prefix and snake_case)."""
    norm = attr.lower().strip()
    if norm.startswith("other:"):
        norm = norm[6:]
    return norm.replace(" ", "_").replace("-", "_")


def _match_fact_values(val_a: str, val_b: str, threshold: float = 0.5) -> bool:
    """Fuzzy match two fact values."""
    norm_a = normalize_string(val_a)
    norm_b = normalize_string(val_b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    if norm_a in norm_b or norm_b in norm_a:
        return True
    return token_overlap_ratio(norm_a, norm_b) >= threshold


def evaluate_facts(
    gold_facts: list[dict[str, Any]],
    extracted_facts: list[dict[str, Any]],
    gold_characters: list[dict[str, Any]],
    threshold: float = 0.6,
) -> MetricScore:
    """Evaluate fact extraction (character match, attribute match, value match)."""
    matched_e: set[int] = set()
    tp = 0

    for g_fact in gold_facts:
        g_char_name = g_fact.get("character", "")
        # Find aliases for this gold character
        g_aliases: list[str] = []
        for gc in gold_characters:
            if match_names(gc.get("canonical_name", ""), g_char_name, threshold):
                g_aliases = gc.get("aliases", [])
                break

        g_attr = _normalize_attribute(g_fact.get("attribute", ""))
        g_val = str(g_fact.get("value", ""))

        found = False
        for e_idx, e_fact in enumerate(extracted_facts):
            if e_idx in matched_e:
                continue

            e_char_name = e_fact.get("character") or e_fact.get("character_name", "")
            e_attr = _normalize_attribute(e_fact.get("attribute", ""))
            e_val = str(e_fact.get("value", ""))

            # Character match
            if not match_character_alias_aware(e_char_name, g_char_name, g_aliases, threshold):
                continue

            # Attribute match
            if g_attr != e_attr:
                continue

            # Value match
            if _match_fact_values(g_val, e_val, threshold=0.5):
                matched_e.add(e_idx)
                tp += 1
                found = True
                break

        if not found:
            pass

    fn = len(gold_facts) - tp
    fp = len(extracted_facts) - len(matched_e)
    return compute_metric_score(tp, fp, fn)


def evaluate_contradictions(
    gold_contradictions: list[dict[str, Any]],
    detected_issues: list[dict[str, Any]],
    threshold: float = 0.6,
) -> MetricScore:
    """Evaluate planted contradictions against detected contradiction issues."""
    matched_issues: set[int] = set()
    tp = 0

    for g_contra in gold_contradictions:
        g_char = g_contra.get("character", "")
        g_attr = _normalize_attribute(g_contra.get("attribute", ""))

        found = False
        for i_idx, issue in enumerate(detected_issues):
            if i_idx in matched_issues:
                continue
            if issue.get("type") != "contradiction":
                continue

            msg = issue.get("message", "").lower()
            quote = (issue.get("quote") or "").lower()

            # Check if character or attribute mentioned in message/quote
            norm_char = normalize_name(g_char)
            if (norm_char in msg or norm_char in quote) and (g_attr in msg or g_attr in quote):
                matched_issues.add(i_idx)
                tp += 1
                found = True
                break

            # Or if attribute is in message
            if g_attr and g_attr in msg:
                matched_issues.add(i_idx)
                tp += 1
                found = True
                break

        if not found:
            pass

    fn = len(gold_contradictions) - tp
    # Only count contradiction-type issues as potential FP
    contra_issues_count = sum(1 for i in detected_issues if i.get("type") == "contradiction")
    fp = contra_issues_count - len(matched_issues)
    if fp < 0:
        fp = 0

    return compute_metric_score(tp, fp, fn)
