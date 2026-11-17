"""Map-reduce summarizer for chapters and entire stories."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from qifrey.db.models import Chapter, Story
from qifrey.pipeline.llm_client import LLMClient, get_llm_client

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SummaryOutput(BaseModel):
    """Schema for generated summaries."""

    model_config = ConfigDict(extra="ignore")

    summary: str = Field(
        default="", description="Concise, factual summary of the narrative events"
    )


def summarize_chapter(
    chapter: Chapter,
    story_id: int,
    *,
    llm_client: LLMClient,
) -> str:
    """Generate a concise summary for a single chapter."""
    system = (
        "You are an expert story editor. Write a concise, 2-3 sentence factual summary "
        "of the main plot events and character developments in this chapter. Do not editorialize."
    )
    user = f"Title: {chapter.title} (Index {chapter.index})\n\nText:\n{chapter.text[:8000]}"

    result = llm_client.complete_json(
        system=system,
        user=user,
        schema=SummaryOutput,
        story_id=story_id,
        purpose=f"chapter_summary_ch{chapter.index}",
    )
    return result.summary.strip()


def summarize_story(
    story_id: int,
    chapter_summaries: list[tuple[int, str, str]],
    *,
    llm_client: LLMClient,
) -> str:
    """Reduce chapter summaries into a cohesive high-level story summary."""
    system = (
        "You are an expert story editor. Combine the chapter summaries into a cohesive, "
        "one-to-two paragraph narrative overview of the story so far."
    )
    ch_text = "\n\n".join(
        f"Chapter {idx} ({title}):\n{summary}" for idx, title, summary in chapter_summaries
    )
    user = f"Chapter Summaries:\n{ch_text}"

    result = llm_client.complete_json(
        system=system,
        user=user,
        schema=SummaryOutput,
        story_id=story_id,
        purpose="story_summary_reduce",
    )
    return result.summary.strip()


def generate_summaries(
    story_id: int,
    db: Session,
    *,
    llm_client: LLMClient | None = None,
) -> None:
    """Map-reduce story summarization: summarize changed chapters, then reduce to Story.summary."""
    client = llm_client or get_llm_client()
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        return

    chapters = (
        db.query(Chapter)
        .filter(Chapter.story_id == story_id, Chapter.exclude_from_analysis.is_(False))
        .order_by(Chapter.index)
        .all()
    )
    if not chapters:
        return

    any_updated = False
    chapter_summaries: list[tuple[int, str, str]] = []

    for ch in chapters:
        # Regenerate if summary is missing or content changed
        if not ch.summary or ch.content_hash != ch.analyzed_hash:
            logger.info("Summarizing Chapter %d: %s...", ch.index, ch.title)
            ch.summary = summarize_chapter(ch, story_id, llm_client=client)
            any_updated = True
        chapter_summaries.append((ch.index, ch.title, ch.summary))

    # Reduce step: update global Story.summary if any chapter changed or story has no summary
    if any_updated or not story.summary:
        logger.info("Generating global summary for story %d...", story_id)
        story.summary = summarize_story(story_id, chapter_summaries, llm_client=client)

    db.commit()
