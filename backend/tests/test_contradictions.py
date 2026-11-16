"""Tests for contradiction detection, LLM adjudication, and author decision persistence."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from qifrey.db.models import Chapter, Character, Fact, Issue, Story
from qifrey.insights.contradictions import (
    AdjudicationOutput,
    detect_contradictions,
    normalize_fact_value,
)
from qifrey.pipeline.llm_client import FakeLLMClient


def test_normalize_fact_value() -> None:
    assert normalize_fact_value("the blue eyes") == "blue eyes"
    assert normalize_fact_value("an emerald green") == "green green"
    assert normalize_fact_value("  A Doctor!  ") == "doctor"
    assert normalize_fact_value("sapphire") == "blue"


def test_planted_eye_color_contradiction_detected(client: Any) -> None:
    """Planted eye-color inconsistency returns exactly one contradiction issue with both quotes."""
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="The Inconsistent Wizard")
        db.add(story)
        db.flush()

        ch1 = Chapter(
            story_id=story.id,
            index=1,
            title="Ch 1",
            text="Qifrey looked up with clear azure blue eyes.",
            content_hash="h1",
        )
        ch2 = Chapter(
            story_id=story.id,
            index=2,
            title="Ch 2",
            text="Qifrey glared with striking emerald green eyes.",
            content_hash="h2",
        )
        db.add_all([ch1, ch2])
        db.flush()

        char = Character(story_id=story.id, canonical_name="Qifrey")
        db.add(char)
        db.flush()

        f1 = Fact(
            story_id=story.id,
            character_id=char.id,
            attribute="eye_color",
            value="azure blue",
            chapter_id=ch1.id,
            quote="clear azure blue eyes",
            confidence=1.0,
        )
        f2 = Fact(
            story_id=story.id,
            character_id=char.id,
            attribute="eye_color",
            value="emerald green",
            chapter_id=ch2.id,
            quote="striking emerald green eyes",
            confidence=1.0,
        )
        db.add_all([f1, f2])
        db.commit()

        fake_llm = FakeLLMClient(
            responses=[
                AdjudicationOutput(
                    verdict="contradiction",
                    explanation="Eye colors changed from blue to green without reason.",
                    severity="warning",
                )
            ]
        )

        issues = detect_contradictions(story.id, db, llm_client=fake_llm)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.type == "contradiction"
        assert issue.status == "open"
        assert "azure blue" in issue.message or "blue" in issue.message
        assert "emerald green" in issue.message or "green" in issue.message
        assert "azure blue eyes" in issue.quote
        assert "emerald green eyes" in issue.quote


def test_haircut_is_not_flagged_as_contradiction(client: Any) -> None:
    """A haircut or legitimate physical change over time is adjudicated and NOT flagged."""
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="Barbershop Journey")
        db.add(story)
        db.flush()

        ch1 = Chapter(story_id=story.id, index=1, title="Ch 1", text="text1", content_hash="h1")
        ch2 = Chapter(story_id=story.id, index=2, title="Ch 2", text="text2", content_hash="h2")
        db.add_all([ch1, ch2])
        db.flush()

        char = Character(story_id=story.id, canonical_name="Arthur")
        db.add(char)
        db.flush()

        f1 = Fact(
            story_id=story.id,
            character_id=char.id,
            attribute="hair_color",
            value="long untamed hair",
            chapter_id=ch1.id,
            quote="his long untamed hair fell to his shoulders",
        )
        f2 = Fact(
            story_id=story.id,
            character_id=char.id,
            attribute="hair_color",
            value="neatly cropped short hair",
            chapter_id=ch2.id,
            quote="he went to the barber and got neatly cropped short hair",
        )
        db.add_all([f1, f2])
        db.commit()

        fake_llm = FakeLLMClient(
            responses=[
                AdjudicationOutput(
                    verdict="legitimate_change",
                    explanation="Arthur received a haircut, explaining the shorter length.",
                )
            ]
        )

        issues = detect_contradictions(story.id, db, llm_client=fake_llm)
        assert len(issues) == 0

        # Verify no issues were added to DB
        all_issues = db.query(Issue).filter(Issue.story_id == story.id).all()
        assert len(all_issues) == 0


def test_dismissed_issues_do_not_return_after_reanalysis(client: Any) -> None:
    """When an author dismisses an issue, re-analysis must respect it and not recreate it."""
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="Author Choices")
        db.add(story)
        db.flush()

        ch1 = Chapter(story_id=story.id, index=1, title="Ch 1", text="t1", content_hash="h1")
        ch2 = Chapter(story_id=story.id, index=2, title="Ch 2", text="t2", content_hash="h2")
        db.add_all([ch1, ch2])
        db.flush()

        char = Character(story_id=story.id, canonical_name="Elena")
        db.add(char)
        db.flush()

        f1 = Fact(
            story_id=story.id,
            character_id=char.id,
            attribute="occupation",
            value="librarian",
            chapter_id=ch1.id,
            quote="Elena the librarian",
        )
        f2 = Fact(
            story_id=story.id,
            character_id=char.id,
            attribute="occupation",
            value="detective",
            chapter_id=ch2.id,
            quote="Elena the detective",
        )
        db.add_all([f1, f2])
        db.commit()

        fake_llm_1 = FakeLLMClient(
            responses=[
                AdjudicationOutput(
                    verdict="contradiction",
                    explanation="Conflicting professions.",
                )
            ]
        )

        # Run 1: creates open issue
        issues_1 = detect_contradictions(story.id, db, llm_client=fake_llm_1)
        assert len(issues_1) == 1
        issue_id = issues_1[0].id

        # Author marks the issue as "dismissed"
        issue = db.query(Issue).filter(Issue.id == issue_id).first()
        assert issue is not None
        issue.status = "dismissed"
        db.commit()

        # Run 2: re-run detection
        fake_llm_2 = FakeLLMClient(
            responses=[
                AdjudicationOutput(
                    verdict="contradiction",
                    explanation="Conflicting professions.",
                )
            ]
        )

        issues_2 = detect_contradictions(story.id, db, llm_client=fake_llm_2)
        assert len(issues_2) == 0

        # Check existing issue is STILL dismissed and was not duplicated
        all_issues = db.query(Issue).filter(Issue.story_id == story.id).all()
        assert len(all_issues) == 1
        assert all_issues[0].status == "dismissed"
