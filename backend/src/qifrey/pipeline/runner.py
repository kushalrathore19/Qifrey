"""Analysis pipeline runner for stories and chapters."""

from __future__ import annotations

import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any

from qifrey.db.models import Chapter, IgnoredName, Issue, Story
from qifrey.db.session import get_session_factory
from qifrey.grammar.checker import DEFAULT_DISABLED_RULES, check_grammar
from qifrey.graph.alias_resolver import resolve_or_create_character
from qifrey.graph.store import (
    delete_chapter_data,
    upsert_character,
    upsert_fact,
    upsert_location,
    upsert_relationship,
)
from qifrey.insights.contradictions import detect_contradictions
from qifrey.insights.summarizer import generate_summaries
from qifrey.pipeline.context_builder import build_memory_block, chunk_chapter_text
from qifrey.pipeline.llm_client import LLMClient, get_llm_client
from qifrey.pipeline.prompts import load_prompt
from qifrey.pipeline.rate_limiter import register_rate_limit_listener
from qifrey.pipeline.schemas import ExtractionOutput
from qifrey.pipeline.validator import validate_extraction

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# In-memory progress tracking: story_id -> status dict
_ANALYSIS_PROGRESS: dict[int, dict[str, Any]] = {}


def set_story_rate_limit_status(story_id: int | None, waiting: bool) -> None:
    """Callback invoked by RateLimiter to update live analysis progress during 429 backoff."""
    if story_id is not None and story_id in _ANALYSIS_PROGRESS:
        if waiting:
            _ANALYSIS_PROGRESS[story_id]["status"] = "waiting on rate limit"
        elif _ANALYSIS_PROGRESS[story_id]["status"] == "waiting on rate limit":
            _ANALYSIS_PROGRESS[story_id]["status"] = "running"


# Register global rate limit listener
register_rate_limit_listener(set_story_rate_limit_status)


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
) -> bool:
    """Analyze a single chapter. Returns True if analyzed, False if skipped."""
    if chapter.exclude_from_analysis:
        logger.info("Chapter %d is marked exclude_from_analysis, skipping.", chapter.index)
        return False

    # Incremental check: if content hash matches analyzed hash, skip
    if chapter.analyzed_hash and chapter.analyzed_hash == chapter.content_hash:
        logger.info("Chapter %d is up to date (hash matches), skipping.", chapter.index)
        return False

    logger.info("Analyzing Chapter %d: '%s'...", chapter.index, chapter.title)

    # Read story settings and ignored names
    story = db.query(Story).filter(Story.id == story_id).first()
    settings: dict[str, Any] = {}
    if story and story.settings_json:
        with contextlib.suppress(Exception):
            settings = json.loads(story.settings_json)
    confidence_threshold = float(settings.get("confidence_threshold", 0.7))
    grammar_lang = str(settings.get("grammar_language", "en-US"))
    disabled_rules_list = settings.get("disabled_grammar_rules", [])
    effective_disabled_rules = DEFAULT_DISABLED_RULES.union(disabled_rules_list)

    ignored_records = db.query(IgnoredName).filter(IgnoredName.story_id == story_id).all()
    ignored_names = {r.name for r in ignored_records}

    # Delete existing facts/relationships for this chapter
    delete_chapter_data(db, chapter.id)
    # Delete old grammar issues for this chapter
    db.query(Issue).filter(Issue.chapter_id == chapter.id, Issue.type == "grammar").delete(
        synchronize_session=False
    )
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
        val_result = validate_extraction(
            extraction,
            chunk,
            confidence_threshold=confidence_threshold,
            ignored_names=ignored_names,
        )

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

    # Run grammar checks for this changed chapter
    grammar_issues = check_grammar(
        chapter.text,
        language=grammar_lang,
        disabled_rules=effective_disabled_rules,
    )
    for g in grammar_issues:
        db.add(
            Issue(
                story_id=story_id,
                chapter_id=chapter.id,
                type="grammar",
                severity="warning",
                message=g.message,
                quote=g.quote,
                span_start=g.span_start,
                span_end=g.span_end,
                suggestions_json=json.dumps(g.suggestions),
                status="open",
            )
        )

    # Mark chapter as analyzed
    chapter.analyzed_hash = chapter.content_hash
    db.commit()
    return True


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

        any_changed = False
        try:
            for idx, ch in enumerate(chapters, start=1):
                _ANALYSIS_PROGRESS[story_id]["current_chapter"] = idx
                if analyze_chapter(story_id, ch, db, llm_client=llm_client):
                    any_changed = True

            # Contradictions and summary recomputed only if changed or story has no summary
            if any_changed or not story.summary:
                detect_contradictions(story_id, db, llm_client=llm_client)
                generate_summaries(story_id, db, llm_client=llm_client)

            _ANALYSIS_PROGRESS[story_id]["status"] = "completed"
        except Exception as err:
            logger.exception("Error during analysis of story %d: %s", story_id, err)
            _ANALYSIS_PROGRESS[story_id]["status"] = "failed"
            _ANALYSIS_PROGRESS[story_id]["error"] = str(err)
            raise
