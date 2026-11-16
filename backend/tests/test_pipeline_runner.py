"""Tests for the pipeline runner and re-analysis."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from qifrey.db.models import Chapter, Fact, LLMCall, Story
from qifrey.pipeline.llm_client import FakeLLMClient
from qifrey.pipeline.runner import analyze_chapter, analyze_story
from qifrey.pipeline.schemas import (
    CharacterExtraction,
    ExtractionOutput,
    FactExtraction,
)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_reanalysis_removes_old_chapter_facts(client: Any) -> None:
    """Changing a chapter and re-analyzing must delete old facts and store new ones."""
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="Changing Tale")
        db.add(story)
        db.flush()

        # Initial text: eye_color = emerald
        initial_text = "The young wizard Qifrey looked out with bright emerald eyes."
        chapter = Chapter(
            story_id=story.id,
            index=1,
            title="Chapter 1",
            text=initial_text,
            content_hash=_hash(initial_text),
            analyzed_hash=None,
        )
        db.add(chapter)
        db.commit()

        # First run: returns emerald eyes
        fake_llm_1 = FakeLLMClient(
            responses=[
                ExtractionOutput(
                    characters=[CharacterExtraction(name="Qifrey", description="Young wizard")],
                    facts=[
                        FactExtraction(
                            character="Qifrey",
                            attribute="eye_color",
                            value="emerald",
                            evidence_quote="bright emerald eyes",
                            confidence=1.0,
                        )
                    ],
                )
            ]
        )

        analyze_chapter(story.id, chapter, db, llm_client=fake_llm_1)

        # Verify fact was saved and chapter analyzed
        facts_v1 = db.query(Fact).filter(Fact.story_id == story.id).all()
        assert len(facts_v1) == 1
        assert facts_v1[0].value == "emerald"
        assert chapter.analyzed_hash == chapter.content_hash

        # Second run: author modifies chapter text (eye_color = sapphire blue)
        updated_text = "The young wizard Qifrey looked out with brilliant sapphire blue eyes."
        chapter.text = updated_text
        chapter.content_hash = _hash(updated_text)
        db.commit()

        # Content hash changed, analyzed_hash is old -> triggers re-analysis
        assert chapter.content_hash != chapter.analyzed_hash

        fake_llm_2 = FakeLLMClient(
            responses=[
                ExtractionOutput(
                    characters=[CharacterExtraction(name="Qifrey", description="Young wizard")],
                    facts=[
                        FactExtraction(
                            character="Qifrey",
                            attribute="eye_color",
                            value="sapphire blue",
                            evidence_quote="brilliant sapphire blue eyes",
                            confidence=1.0,
                        )
                    ],
                )
            ]
        )

        analyze_chapter(story.id, chapter, db, llm_client=fake_llm_2)

        # Verify: old "emerald" fact was REMOVED, only new "sapphire blue" fact remains
        facts_v2 = db.query(Fact).filter(Fact.story_id == story.id).all()
        assert len(facts_v2) == 1
        assert facts_v2[0].value == "sapphire blue"
        assert chapter.analyzed_hash == chapter.content_hash


def test_unchanged_chapter_is_skipped(client: Any) -> None:
    """When content_hash == analyzed_hash, extraction is skipped entirely."""
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="Static Story")
        db.add(story)
        db.flush()

        text = "Nothing ever changes here."
        h = _hash(text)
        chapter = Chapter(
            story_id=story.id,
            index=1,
            title="Chapter 1",
            text=text,
            content_hash=h,
            analyzed_hash=h,  # Already analyzed!
        )
        db.add(chapter)
        db.commit()

        fake_llm = FakeLLMClient()
        analyze_chapter(story.id, chapter, db, llm_client=fake_llm)

        # FakeLLM was never called
        assert len(fake_llm.history) == 0


def test_llm_calls_recorded_in_database(client: Any) -> None:
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="Logged Story")
        db.add(story)
        db.flush()

        text = "Arthur held Excalibur aloft."
        chapter = Chapter(
            story_id=story.id,
            index=1,
            title="Chapter 1",
            text=text,
            content_hash=_hash(text),
        )
        db.add(chapter)
        db.commit()

        fake_llm = FakeLLMClient(
            responses=[
                ExtractionOutput(
                    characters=[CharacterExtraction(name="Arthur")],
                    facts=[
                        FactExtraction(
                            character="Arthur",
                            attribute="weapon",
                            value="Excalibur",
                            evidence_quote="Arthur held Excalibur aloft",
                        )
                    ],
                )
            ]
        )

        analyze_story(story.id, llm_client=fake_llm)

        calls = db.query(LLMCall).filter(LLMCall.story_id == story.id).all()
        assert len(calls) >= 1
        assert calls[0].model == "fake-llm"
        assert calls[0].prompt_hash != ""
