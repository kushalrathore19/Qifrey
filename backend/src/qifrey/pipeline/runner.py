"""Analysis pipeline runner for stories and chapters."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qifrey.db.models import Chapter, Story
from qifrey.db.session import get_session_factory
from qifrey.graph.alias_resolver import resolve_or_create_character
from qifrey.graph.store import (
    delete_chapter_data,
    upsert_character,
    upsert_fact,
    upsert_location,
    upsert_relationship,
)
from qifrey.pipeline.context_builder import build_memory_block, chunk_chapter_text
from qifrey.pipeline.llm_client import LLMClient, get_llm_client
from qifrey.pipeline.prompts import load_prompt
from qifrey.pipeline.schemas import ExtractionOutput
from qifrey.pipeline.validator import validate_extraction

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# In-memory progress tracking: story_id -> status dict
_ANALYSIS_PROGRESS: dict[int, dict[str, Any]] = {}


def get_story_analysis_status(story_id: int, db: Session) -> dict[str, Any]:
    """Return the current analysis progress for a story."""
    if story_id in _ANALYSIS_PROGRESS:
        return _ANALYSIS_PROGRESS[story_id]

    # Derive from DB if not actively running
    chapters = db.query(Chapter).filter(Chapter.story_id == story_id).order_by(Chapter.index).all()
    total = len(chapters)
    analyzed = sum(1 for c in chapters if c.analyzed_hash and c.analyzed_hash == c.content_hash)

    status = "completed" if total > 0 and analyzed == total else "idle"
    return {
        "story_id": story_id,
        "status": status,
        "current_chapter": analyzed,
        "total_chapters": total,
        "error": None,
    }


def analyze_chapter(
    story_id: int,
    chapter: Chapter,
    db: Session,
    *,
    llm_client: LLMClient | None = None,
) -> None:
    """Analyze a single chapter: context -> extract -> validate -> resolve -> store."""
    # Incremental check: if content hash matches analyzed hash, skip
    if chapter.analyzed_hash and chapter.analyzed_hash == chapter.content_hash:
        logger.info("Chapter %d is up to date (hash matches), skipping.", chapter.index)
        return

    logger.info("Analyzing Chapter %d: '%s'...", chapter.index, chapter.title)

    # Delete existing facts/relationships for this chapter
    delete_chapter_data(db, chapter.id)
    db.commit()

    client = llm_client or get_llm_client()
    system_prompt = load_prompt("extraction_v1")

    # Split text into chunks if longer than ~3000 words
    chunks = chunk_chapter_text(chapter.text, max_words=3000)

    for chunk_idx, chunk in enumerate(chunks, start=1):
        # Build memory from existing graph
        memory_block = build_memory_block(story_id, chapter.index, chunk, db)

        user_content = (
            f"CHAPTER {chapter.index}: {chapter.title} (Part {chunk_idx}/{len(chunks)})\n\n"
        )
        if memory_block:
            user_content += f"{memory_block}\n\n"
        user_content += f"TEXT:\n{chunk}"

        # LLM extraction
        extraction: ExtractionOutput = client.complete_json(
            system=system_prompt,
            user=user_content,
            schema=ExtractionOutput,
            story_id=story_id,
            purpose=f"extraction_ch{chapter.index}_p{chunk_idx}",
        )

        # Validate extraction against this chunk's text
        val_result = validate_extraction(extraction, chunk)

        # 1. Store characters and aliases
        for char_ext in val_result.accepted_characters:
            char_obj = resolve_or_create_character(
                char_ext.name,
                story_id,
                db,
                description=char_ext.description,
                llm_client=client,
            )
            if char_ext.aliases:
                upsert_character(
                    db,
                    story_id,
                    char_obj.canonical_name,
                    aliases=char_ext.aliases,
                )

        # 2. Store locations
        for loc_ext in val_result.accepted_locations:
            upsert_location(db, story_id, loc_ext.name, description=loc_ext.description)

        # 3. Store facts
        for fact_ext in val_result.accepted_facts:
            target_char = resolve_or_create_character(
                fact_ext.character,
                story_id,
                db,
                llm_client=client,
            )
            upsert_fact(
                db,
                story_id=story_id,
                character_id=target_char.id,
                attribute=fact_ext.attribute,
                value=fact_ext.value,
                chapter_id=chapter.id,
                quote=fact_ext.evidence_quote,
                confidence=fact_ext.confidence,
            )

        # 4. Store relationships
        for rel_ext in val_result.accepted_relationships:
            char_a = resolve_or_create_character(rel_ext.a, story_id, db, llm_client=client)
            char_b = resolve_or_create_character(rel_ext.b, story_id, db, llm_client=client)
            upsert_relationship(
                db,
                story_id=story_id,
                source_character_id=char_a.id,
                target_character_id=char_b.id,
                type_=rel_ext.type,
                chapter_id=chapter.id,
                quote=rel_ext.evidence_quote,
            )

        db.commit()

    # Mark chapter as analyzed
    chapter.analyzed_hash = chapter.content_hash
    db.commit()


def analyze_story(story_id: int, *, llm_client: LLMClient | None = None) -> None:
    """Analyze all unanalyzed or modified chapters for a story sequentially."""
    factory = get_session_factory()
    with factory() as db:
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            logger.error("Story %d not found for analysis", story_id)
            return

        chapters = (
            db.query(Chapter).filter(Chapter.story_id == story_id).order_by(Chapter.index).all()
        )
        total = len(chapters)

        _ANALYSIS_PROGRESS[story_id] = {
            "story_id": story_id,
            "status": "running",
            "current_chapter": 0,
            "total_chapters": total,
            "error": None,
        }

        try:
            for idx, ch in enumerate(chapters, start=1):
                _ANALYSIS_PROGRESS[story_id]["current_chapter"] = idx
                analyze_chapter(story_id, ch, db, llm_client=llm_client)

            _ANALYSIS_PROGRESS[story_id]["status"] = "completed"
        except Exception as err:
            logger.exception("Error during analysis of story %d: %s", story_id, err)
            _ANALYSIS_PROGRESS[story_id]["status"] = "failed"
            _ANALYSIS_PROGRESS[story_id]["error"] = str(err)
            raise
