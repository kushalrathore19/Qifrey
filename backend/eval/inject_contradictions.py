"""Programmatically inject contradictions and legitimate changes into stories for evaluation."""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path
from typing import Any

from eval.metrics import compute_metric_score

# Swappable pairs for physical attributes
ATTRIBUTE_SWAPS: dict[str, list[tuple[str, str]]] = {
    "eye_color": [
        ("silver", "dark obsidian"),
        ("green", "bright sapphire blue"),
        ("blue", "emerald green"),
        ("brown", "pale violet"),
        ("hazel", "pitch black"),
    ],
    "hair_color": [
        ("black", "golden blonde"),
        ("blonde", "raven black"),
        ("brown", "silver white"),
        ("red", "deep brown"),
    ],
}

# Legitimate temporal changes that should NOT be flagged as contradictions
LEGITIMATE_TEMPLATES: list[tuple[str, str, str]] = [
    ("haircut", "cut his hair short with shears", "hair_style"),
    ("birthday", "celebrated another birthday and turned a year older", "age"),
    ("relocation", "packed their belongings and moved into a new residence", "home_location"),
    ("wardrobe", "changed into a formal traveling cloak", "attire"),
]


def inject_contradictions(
    story_data: dict[str, Any],
    n: int = 1,
    include_legitimate_changes: bool = True,
    seed: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Inject N contradictions and optional legitimate changes into later chapters of a story.

    Returns:
        (modified_story_data, answer_key)
    """
    if seed is not None:
        random.seed(seed)

    modified = copy.deepcopy(story_data)
    chapters = modified.get("chapters", [])
    if len(chapters) < 2:
        # Not enough chapters to plant cross-chapter contradictions
        return modified, []

    answer_key: list[dict[str, Any]] = []
    injected_count = 0

    # Find candidate facts from chapter 1 that can be mutated in chapter 2+
    ch1 = chapters[0]
    ch1_facts = ch1.get("facts", [])

    for fact in ch1_facts:
        if injected_count >= n:
            break
        attr = fact.get("attribute", "")
        val = fact.get("value", "")
        char_name = fact.get("character", "")

        swaps = ATTRIBUTE_SWAPS.get(attr, [])
        new_val = None
        for orig, replacement in swaps:
            if orig.lower() in val.lower():
                new_val = replacement
                break
            if replacement.lower() in val.lower():
                new_val = orig
                break

        if not new_val and swaps:
            new_val = swaps[0][1]

        if new_val:
            # Plant this contradiction in the last chapter
            target_chapter = chapters[-1]
            target_text = target_chapter.get("text", "")

            # Inject a conflicting sentence mentioning the character and new value
            injection_sentence = (
                f" Everyone noted that {char_name} possessed remarkable {new_val} eyes."
            )
            target_chapter["text"] = target_text + injection_sentence

            # Add to facts of the target chapter
            target_chapter.setdefault("facts", []).append(
                {
                    "character": char_name,
                    "attribute": attr,
                    "value": new_val,
                    "quote": f"remarkable {new_val} eyes",
                }
            )

            # Record in answer key
            answer_key.append(
                {
                    "type": "contradiction",
                    "character": char_name,
                    "attribute": attr,
                    "chapter_a": ch1.get("index", 1),
                    "chapter_b": target_chapter.get("index", len(chapters)),
                    "original_value": val,
                    "new_value": new_val,
                    "description": (
                        f"Planted contradiction: {attr} changed from {val} to {new_val}."
                    ),
                }
            )
            injected_count += 1

    # Optionally inject a legitimate change to test false positive resistance
    if include_legitimate_changes and len(chapters) >= 2:
        target_ch = chapters[-1]
        char_name = ch1_facts[0].get("character", "The protagonist") if ch1_facts else "Hero"
        legit_type, legit_phrase, legit_attr = random.choice(LEGITIMATE_TEMPLATES)
        sentence = f" Later that year, {char_name} {legit_phrase}."
        target_ch["text"] = target_ch.get("text", "") + sentence

        answer_key.append(
            {
                "type": "legitimate_change",
                "character": char_name,
                "attribute": legit_attr,
                "chapter_index": target_ch.get("index", len(chapters)),
                "change_type": legit_type,
                "description": (
                    f"Legitimate change: {char_name} {legit_phrase} "
                    "(should NOT be flagged as contradiction)."
                ),
            }
        )

    # Sync top-level planted contradictions
    modified["contradictions"] = [
        item for item in answer_key if item.get("type") == "contradiction"
    ]
    return modified, answer_key


def evaluate_contradiction_detection(
    detected_issues: list[dict[str, Any]],
    answer_key: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate recall/precision on planted contradictions and FP on legitimate changes."""
    planted_contradictions = [k for k in answer_key if k.get("type") == "contradiction"]
    legitimate_changes = [k for k in answer_key if k.get("type") == "legitimate_change"]

    # Filter detected issues to contradiction type only
    contradiction_issues = [iss for iss in detected_issues if iss.get("type") == "contradiction"]

    tp = 0
    matched_issues: set[int] = set()

    for p in planted_contradictions:
        p_char = p.get("character", "").lower()
        p_attr = p.get("attribute", "").lower()

        found = False
        for i_idx, iss in enumerate(contradiction_issues):
            if i_idx in matched_issues:
                continue
            msg = iss.get("message", "").lower()
            quote = (iss.get("quote") or "").lower()

            if (p_char in msg or p_char in quote) and (p_attr in msg or p_attr in quote):
                matched_issues.add(i_idx)
                tp += 1
                found = True
                break
        if not found:
            pass

    fn = len(planted_contradictions) - tp
    fp = len(contradiction_issues) - len(matched_issues)
    if fp < 0:
        fp = 0

    score = compute_metric_score(tp, fp, fn)

    # Check false positives on legitimate changes
    legit_fp = 0
    for leg in legitimate_changes:
        leg_char = leg.get("character", "").lower()
        leg_attr = leg.get("attribute", "").lower()
        for iss in contradiction_issues:
            msg = iss.get("message", "").lower()
            if leg_char in msg and leg_attr in msg:
                legit_fp += 1
                break

    return {
        "metrics": score,
        "total_planted": len(planted_contradictions),
        "detected_tp": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "legitimate_changes_count": len(legitimate_changes),
        "false_positives_on_legitimate": legit_fp,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject contradictions into a gold story.")
    parser.add_argument("--input", required=True, help="Path to input clean gold JSON story.")
    parser.add_argument("--out", required=True, help="Path to save modified story JSON.")
    parser.add_argument("--key", required=True, help="Path to save answer key JSON.")
    parser.add_argument("--n", type=int, default=1, help="Number of contradictions to inject.")
    parser.add_argument(
        "--no-legitimate",
        action="store_true",
        help="Do not inject legitimate changes control group.",
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    with in_path.open("r", encoding="utf-8") as f:
        story = json.load(f)

    mod_story, key = inject_contradictions(
        story,
        n=args.n,
        include_legitimate_changes=not args.no_legitimate,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(mod_story, f, indent=2)

    key_path = Path(args.key)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    with key_path.open("w", encoding="utf-8") as f:
        json.dump(key, f, indent=2)

    print(f"Saved modified story with {len(key)} injected events to {out_path}")
    print(f"Saved answer key to {key_path}")


if __name__ == "__main__":
    main()
