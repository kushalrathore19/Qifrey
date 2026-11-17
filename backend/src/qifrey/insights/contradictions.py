"""Contradiction detection and LLM adjudication for character facts."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from qifrey.db.models import AttributeRule, Fact, Issue
from qifrey.pipeline.llm_client import LLMClient, get_llm_client

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

COLOR_SYNONYMS: dict[str, str] = {
    "emerald": "green",
    "sapphire": "blue",
    "azure": "blue",
    "navy": "blue",
    "crimson": "red",
    "scarlet": "red",
    "ruby": "red",
    "golden": "yellow",
    "amber": "yellow",
    "ebony": "black",
    "raven": "black",
    "pitch black": "black",
    "snowy": "white",
    "chalky": "white",
}


def normalize_fact_value(value: str) -> str:
    """Normalize fact value for candidate pairing comparison."""
    v = value.strip().lower()
    # Strip leading articles
    for article in ("the ", "a ", "an "):
        if v.startswith(article):
            v = v[len(article) :].strip()

    # Remove extra punctuation
    v = re.sub(r"[^\w\s-]", "", v).strip()

    # Color normalization if single word matches
    words = v.split()
    normalized_words = [COLOR_SYNONYMS.get(w, w) for w in words]
    return " ".join(normalized_words)


class AdjudicationOutput(BaseModel):
    """LLM decision on whether two contrasting facts represent a true narrative contradiction."""

    model_config = ConfigDict(extra="ignore")

    verdict: Literal["contradiction", "legitimate_change", "different_referent"] = Field(
        ...,
        description=(
            "'contradiction': genuine world inconsistency (e.g. blue eyes vs green eyes). "
            "'legitimate_change': intentional change over time (e.g. haircut, aging, clothing). "
            "'different_referent': quotes describe different entities or a metaphor."
        ),
    )
    explanation: str = Field(default="", description="Reasoning for the verdict")
    severity: Literal["warning", "error", "info"] = Field(
        default="warning",
        description="Severity level of the contradiction",
    )


def adjudicate_candidate_pair(
    fact1: Fact,
    fact2: Fact,
    character_name: str,
    *,
    story_id: int,
    llm_client: LLMClient,
) -> AdjudicationOutput:
    """Send candidate contradiction pair to LLM adjudicator."""
    system = (
        "You are an expert fiction editor analyzing potential story contradictions. "
        "Determine whether two extracted facts about a character are a true narrative "
        "contradiction, a legitimate change over time (e.g., haircut, clothing change, aging, "
        "wound healing), or refer to different things/metaphors."
    )

    ch1_label = (
        f"Chapter {fact1.chapter.index}"
        if fact1.chapter
        else (f"Chapter {fact1.chapter_id}" if fact1.chapter_id else "Author Notes")
    )
    ch2_label = (
        f"Chapter {fact2.chapter.index}"
        if fact2.chapter
        else (f"Chapter {fact2.chapter_id}" if fact2.chapter_id else "Author Notes")
    )

    user = (
        f"Character: {character_name}\n"
        f"Attribute: {fact1.attribute}\n\n"
        f"Occurrence 1 ({ch1_label}):\n"
        f"  Value: '{fact1.value}'\n"
        f'  Quote: "{fact1.quote or "No quote"}"\n\n'
        f"Occurrence 2 ({ch2_label}):\n"
        f"  Value: '{fact2.value}'\n"
        f'  Quote: "{fact2.quote or "No quote"}"\n\n'
        f"Verdict choices:\n"
        f"- 'contradiction': Accidental author error or incompatible fact.\n"
        f"- 'legitimate_change': Natural progression (e.g. hair cut, outfit change, aging).\n"
        f"- 'different_referent': Describing a metaphor, another entity, or mistaken identity.\n\n"
        f"Output JSON conforming to AdjudicationOutput schema."
    )

    return llm_client.complete_json(
        system=system,
        user=user,
        schema=AdjudicationOutput,
        story_id=story_id,
        purpose="contradiction_adjudication",
    )


def detect_contradictions(
    story_id: int,
    db: Session,
    *,
    llm_client: LLMClient | None = None,
) -> list[Issue]:
    """Detect fact contradictions across the story graph and create open Issues."""
    client = llm_client or get_llm_client()

    # Fetch attribute rules for this story
    rules = db.query(AttributeRule).filter(AttributeRule.story_id == story_id).all()
    rule_map = {r.attribute.strip().lower(): r.mode for r in rules}

    # Query all facts for this story, ordered by character and attribute
    facts = (
        db.query(Fact)
        .filter(Fact.story_id == story_id)
        .order_by(Fact.character_id, Fact.attribute, Fact.chapter_id)
        .all()
    )

    # Group facts by (character_id, attribute)
    groups: dict[tuple[int, str], list[Fact]] = {}
    for f in facts:
        groups.setdefault((f.character_id, f.attribute), []).append(f)

    # Fetch existing contradiction issues to respect author decisions (dismissed / intentional)
    existing_issues = (
        db.query(Issue).filter(Issue.story_id == story_id, Issue.type == "contradiction").all()
    )

    # Map existing related_fact_ids -> status
    existing_pairs: dict[str, str] = {}
    for iss in existing_issues:
        if iss.related_fact_ids_json:
            try:
                ids = json.loads(iss.related_fact_ids_json)
                key = json.dumps(sorted(ids))
                existing_pairs[key] = iss.status
            except (json.JSONDecodeError, TypeError):
                pass

    new_issues: list[Issue] = []

    for (char_id, attribute), char_facts in groups.items():
        if len(char_facts) < 2:
            continue

        rule_mode = rule_map.get(attribute.strip().lower(), "strict")
        if rule_mode == "ignore":
            continue

        # Check for distinct normalized values
        # Form candidate pairs where normalized values differ
        seen_pairs_in_run: set[tuple[int, int]] = set()

        for i in range(len(char_facts)):
            for j in range(i + 1, len(char_facts)):
                f1 = char_facts[i]
                f2 = char_facts[j]

                # If rule_mode == "can_change", only flag if two values appear in the same chapter
                if rule_mode == "can_change" and (
                    f1.chapter_id is None
                    or f2.chapter_id is None
                    or f1.chapter_id != f2.chapter_id
                ):
                    continue

                norm1 = normalize_fact_value(f1.value)
                norm2 = normalize_fact_value(f2.value)

                if norm1 == norm2:
                    continue

                pair_key = tuple(sorted([f1.id, f2.id]))
                if pair_key in seen_pairs_in_run:
                    continue
                seen_pairs_in_run.add(pair_key)

                pair_json = json.dumps(list(pair_key))

                # Respect author decisions: do not recreate if dismissed or marked intentional
                if pair_json in existing_pairs:
                    prev_status = existing_pairs[pair_json]
                    if prev_status in ("dismissed", "intentional", "accepted", "open"):
                        logger.info(
                            "Skipping pair %s with existing status '%s'",
                            pair_json,
                            prev_status,
                        )
                        continue

                char_name = (
                    f1.character.canonical_name if f1.character else f"Character #{char_id}"
                )
                decision = adjudicate_candidate_pair(
                    f1,
                    f2,
                    char_name,
                    story_id=story_id,
                    llm_client=client,
                )

                if decision.verdict == "contradiction":
                    f1_is_manual = f1.source == "manual" or f1.locked
                    f2_is_manual = f2.source == "manual" or f2.locked
                    is_notes_conflict = (f1_is_manual and not f2_is_manual) or (
                        f2_is_manual and not f1_is_manual
                    )

                    ch1_label = (
                        f"Ch. {f1.chapter.index}"
                        if f1.chapter
                        else (f"Ch. {f1.chapter_id}" if f1.chapter_id else "Author Notes")
                    )
                    ch2_label = (
                        f"Ch. {f2.chapter.index}"
                        if f2.chapter
                        else (f"Ch. {f2.chapter_id}" if f2.chapter_id else "Author Notes")
                    )

                    if is_notes_conflict:
                        manual_f = f1 if f1_is_manual else f2
                        text_f = f2 if f1_is_manual else f1
                        text_ch = (
                            f"Ch. {text_f.chapter.index}"
                            if text_f.chapter
                            else (f"Ch. {text_f.chapter_id}" if text_f.chapter_id else "Text")
                        )
                        msg = (
                            f"Text conflicts with your notes: '{text_f.value}' ({text_ch}) vs "
                            f"'{manual_f.value}' in author notes. {decision.explanation}".strip()
                        )
                    else:
                        msg = (
                            f"Contradiction in {attribute} for {char_name}: "
                            f"'{f1.value}' ({ch1_label}) vs '{f2.value}' ({ch2_label}). "
                            f"{decision.explanation}".strip()
                        )

                    combined_quote = (
                        f'{ch1_label}: "{f1.quote or f1.value}"\n'
                        f'{ch2_label}: "{f2.quote or f2.value}"'
                    )

                    issue_chapter_id = f2.chapter_id or f1.chapter_id
                    issue = Issue(
                        story_id=story_id,
                        type="contradiction",
                        chapter_id=issue_chapter_id,
                        severity=decision.severity,
                        message=msg,
                        quote=combined_quote,
                        related_fact_ids_json=pair_json,
                        status="open",
                    )
                    db.add(issue)
                    new_issues.append(issue)
                    existing_pairs[pair_json] = "open"

    db.commit()
    return new_issues
