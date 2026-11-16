"""Tests for map-reduce story and chapter summarization."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from qifrey.db.models import Chapter, Story
from qifrey.insights.summarizer import SummaryOutput, generate_summaries
from qifrey.pipeline.llm_client import FakeLLMClient


def test_map_reduce_summaries(client: Any) -> None:
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="The Epic Tale")
        db.add(story)
        db.flush()

        ch1 = Chapter(
            story_id=story.id,
            index=1,
            title="Beginning",
            text="The journey started in the green forest.",
            content_hash="h1",
            analyzed_hash="h1",
        )
        ch2 = Chapter(
            story_id=story.id,
            index=2,
            title="Climax",
            text="They reached the fiery mountain and defeated the dragon.",
            content_hash="h2",
            analyzed_hash="h2",
        )
        db.add_all([ch1, ch2])
        db.commit()

        # Fake LLM responses: ch1 summary, ch2 summary, reduced story summary
        fake_llm = FakeLLMClient(
            responses=[
                SummaryOutput(summary="The hero embarks on a quest into the forest."),
                SummaryOutput(summary="The hero slays the dragon at the mountain."),
                SummaryOutput(
                    summary="A hero leaves the forest and defeats the dragon at the mountain."
                ),
            ]
        )

        generate_summaries(story.id, db, llm_client=fake_llm)

        db.refresh(story)
        db.refresh(ch1)
        db.refresh(ch2)

        assert ch1.summary == "The hero embarks on a quest into the forest."
        assert ch2.summary == "The hero slays the dragon at the mountain."
        assert "defeats the dragon" in story.summary

        # Re-run when nothing changed: no new LLM calls should be made
        generate_summaries(story.id, db, llm_client=fake_llm)
        assert len(fake_llm.responses) == 0
