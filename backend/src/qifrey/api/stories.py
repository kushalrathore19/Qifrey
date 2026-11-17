"""Story and chapter API endpoints."""

from __future__ import annotations

import contextlib
import hashlib
import json
from typing import Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

from qifrey.api.schemas import (
    AliasCreate,
    AliasOut,
    AnalysisStatusOut,
    AttributeRuleSchema,
    ChapterBrief,
    ChapterCreate,
    ChapterOut,
    ChapterUpdate,
    CharacterBriefOut,
    CharacterCreate,
    CharacterDetailOut,
    CharacterMergeRequest,
    CharacterUpdate,
    FactCreateItem,
    FactDetailOut,
    FactUpdate,
    GrammarCheckRequest,
    GrammarIssueOut,
    GrammarStatusOut,
    IssueOut,
    IssueStatusUpdate,
    MessageOut,
    StoryCreate,
    StoryDetail,
    StoryOut,
    StorySettings,
    StorySettingsUpdate,
)
from qifrey.config import get_settings
from qifrey.db.models import (
    Alias,
    AttributeRule,
    Chapter,
    Character,
    Fact,
    IgnoredName,
    Issue,
    Story,
)
from qifrey.db.session import get_db
from qifrey.grammar.checker import check_grammar
from qifrey.graph.store import (
    delete_chapter_data,
    get_character_with_facts,
    ignore_character,
    list_characters,
    merge_characters,
)
from qifrey.ingestion.txt_parser import decode_upload, parse_chapters
from qifrey.pipeline.runner import (
    analyze_single_chapter,
    analyze_story,
    get_story_analysis_status,
)

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/grammar/status", response_model=GrammarStatusOut)
def grammar_status() -> GrammarStatusOut:
    """Return whether grammar checker (LanguageTool/Java) is available."""
    from qifrey.grammar.checker import get_grammar_checker_status

    return GrammarStatusOut(**get_grammar_checker_status())


@router.post("/stories/upload", response_model=StoryDetail, status_code=201)
def upload_story(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> Story:
    settings = get_settings()

    # Validate file extension
    if file.filename and not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported.")

    # Read and validate size
    raw_bytes = file.file.read()
    if len(raw_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="File exceeds 5 MB limit.")

    # Decode
    text = decode_upload(raw_bytes)

    # Parse chapters
    chapters = parse_chapters(text)

    # Derive title
    story_title = title or (file.filename.rsplit(".", 1)[0] if file.filename else "Untitled")

    # Create story
    story = Story(title=story_title)
    db.add(story)
    db.flush()

    # Create chapters
    for ch in chapters:
        db.add(
            Chapter(
                story_id=story.id,
                index=ch.index,
                title=ch.title,
                text=ch.text,
                content_hash=ch.content_hash,
            )
        )

    db.commit()
    db.refresh(story)
    return story


@router.post("/stories", response_model=StoryDetail, status_code=201)
def create_blank_story(
    body: StoryCreate,
    db: Session = Depends(get_db),
) -> Story:
    story = Story(title=body.title)
    db.add(story)
    db.commit()
    db.refresh(story)
    return story


@router.get("/stories", response_model=list[StoryOut])
def list_stories(db: Session = Depends(get_db)) -> list[StoryOut]:
    stories = db.query(Story).order_by(Story.updated_at.desc()).all()
    result: list[StoryOut] = []
    for s in stories:
        chapter_count = db.query(Chapter).filter(Chapter.story_id == s.id).count()
        result.append(
            StoryOut(
                id=s.id,
                title=s.title,
                summary=s.summary,
                created_at=s.created_at,
                updated_at=s.updated_at,
                chapter_count=chapter_count,
            )
        )
    return result


@router.get("/stories/{story_id}", response_model=StoryDetail)
def get_story(story_id: int, db: Session = Depends(get_db)) -> Story:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")
    return story


@router.delete("/stories/{story_id}", response_model=MessageOut)
def delete_story(story_id: int, db: Session = Depends(get_db)) -> MessageOut:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")
    db.delete(story)
    db.commit()
    return MessageOut(detail="Story deleted.")


@router.get("/stories/{story_id}/chapters", response_model=list[ChapterBrief])
def list_chapters(story_id: int, db: Session = Depends(get_db)) -> list[Chapter]:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")
    return db.query(Chapter).filter(Chapter.story_id == story_id).order_by(Chapter.index).all()


@router.get("/chapters/{chapter_id}", response_model=ChapterOut)
def get_chapter(chapter_id: int, db: Session = Depends(get_db)) -> Chapter:
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    return chapter


@router.post("/stories/{story_id}/chapters", response_model=ChapterOut, status_code=201)
def create_chapter(
    story_id: int,
    body: ChapterCreate,
    db: Session = Depends(get_db),
) -> Chapter:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")

    if body.index is not None:
        chapter_index = body.index
    else:
        max_idx = db.query(func.max(Chapter.index)).filter(Chapter.story_id == story_id).scalar()
        chapter_index = 1 if max_idx is None else int(max_idx) + 1

    text = body.text or ""
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    chapter = Chapter(
        story_id=story_id,
        index=chapter_index,
        title=body.title or f"Chapter {chapter_index}",
        text=text,
        content_hash=content_hash,
        exclude_from_analysis=body.exclude_from_analysis,
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


@router.put("/chapters/{chapter_id}", response_model=ChapterOut)
def update_chapter(
    chapter_id: int,
    body: ChapterUpdate,
    db: Session = Depends(get_db),
) -> Chapter:
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found.")

    if body.title is not None:
        chapter.title = body.title
    if body.index is not None:
        chapter.index = body.index
    if body.exclude_from_analysis is not None:
        chapter.exclude_from_analysis = body.exclude_from_analysis
    if body.text is not None:
        chapter.text = body.text
        chapter.content_hash = hashlib.sha256(body.text.encode("utf-8")).hexdigest()

    db.commit()
    db.refresh(chapter)
    return chapter


@router.delete("/chapters/{chapter_id}", response_model=MessageOut)
def delete_chapter(
    chapter_id: int,
    db: Session = Depends(get_db),
) -> MessageOut:
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found.")

    # Remove graph data provenance
    delete_chapter_data(db, chapter.id)

    # Remove issues referencing this chapter
    db.query(Issue).filter(Issue.chapter_id == chapter.id).delete(synchronize_session=False)

    db.delete(chapter)
    db.commit()
    return MessageOut(detail=f"Chapter {chapter_id} deleted.")


@router.post("/chapters/{chapter_id}/grammar", response_model=list[GrammarIssueOut])
def check_chapter_grammar_endpoint(
    chapter_id: int,
    body: GrammarCheckRequest | None = None,
    db: Session = Depends(get_db),
) -> list[GrammarIssueOut]:
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found.")

    text_to_check = body.text if (body and body.text is not None) else chapter.text
    issues = check_grammar(text_to_check)
    return [
        GrammarIssueOut(
            message=issue.message,
            rule_id=issue.rule_id,
            span_start=issue.span_start,
            span_end=issue.span_end,
            quote=issue.quote,
            suggestions=issue.suggestions,
        )
        for issue in issues
    ]


def _run_single_chapter_analysis_task(chapter_id: int) -> None:
    from qifrey.db.session import get_session_factory

    factory = get_session_factory()
    with factory() as db:
        analyze_single_chapter(chapter_id, db)


@router.post("/chapters/{chapter_id}/analyze", response_model=MessageOut)
def trigger_analyze_chapter(
    chapter_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MessageOut:
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    background_tasks.add_task(_run_single_chapter_analysis_task, chapter_id)
    return MessageOut(detail=f"Analysis scheduled for chapter {chapter_id}.")


@router.post("/stories/{story_id}/analyze", response_model=MessageOut)
def trigger_analyze_story(
    story_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MessageOut:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")
    background_tasks.add_task(analyze_story, story_id)
    return MessageOut(detail=f"Analysis scheduled for story {story_id}.")


@router.get("/stories/{story_id}/analysis-status", response_model=AnalysisStatusOut)
def get_analysis_status(
    story_id: int,
    db: Session = Depends(get_db),
) -> AnalysisStatusOut:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")
    status_dict = get_story_analysis_status(story_id, db)
    return AnalysisStatusOut(**status_dict)


@router.get("/stories/{story_id}/characters", response_model=list[CharacterBriefOut])
def get_story_characters(
    story_id: int,
    db: Session = Depends(get_db),
) -> list[CharacterBriefOut]:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")
    characters = list_characters(db, story_id)
    results: list[CharacterBriefOut] = []
    for c in characters:
        fact_count = db.query(Fact).filter(Fact.character_id == c.id).count()
        tags = json.loads(c.tags_json) if c.tags_json else []
        results.append(
            CharacterBriefOut(
                id=c.id,
                story_id=c.story_id,
                canonical_name=c.canonical_name,
                description=c.description,
                aliases=[a.name for a in c.aliases],
                fact_count=fact_count,
                source=c.source,
                locked=c.locked,
                status=c.status,
                notes=c.notes,
                color=c.color,
                tags=tags,
            )
        )
    return results


@router.get("/characters/{character_id}", response_model=CharacterDetailOut)
def get_character_detail(
    character_id: int,
    db: Session = Depends(get_db),
) -> CharacterDetailOut:
    data = get_character_with_facts(db, character_id)
    if not data:
        raise HTTPException(status_code=404, detail="Character not found.")
    return CharacterDetailOut(**data)


@router.get("/stories/{story_id}/issues", response_model=list[IssueOut])
def list_story_issues(
    story_id: int,
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Issue]:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")

    query = db.query(Issue).filter(Issue.story_id == story_id)
    if type:
        query = query.filter(Issue.type == type)
    if status:
        query = query.filter(Issue.status == status)

    return query.order_by(Issue.created_at.desc()).all()


@router.patch("/issues/{issue_id}", response_model=IssueOut)
def update_issue_status(
    issue_id: int,
    body: IssueStatusUpdate,
    db: Session = Depends(get_db),
) -> Issue:
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found.")

    issue.status = body.status
    db.commit()
    db.refresh(issue)
    return issue


# =========================================================================
# Phase 8: Author-Controlled Story Bible Endpoints
# =========================================================================


@router.post("/stories/{story_id}/characters", response_model=CharacterDetailOut, status_code=201)
def create_manual_character(
    story_id: int,
    body: CharacterCreate,
    db: Session = Depends(get_db),
) -> CharacterDetailOut:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")

    char = Character(
        story_id=story_id,
        canonical_name=body.canonical_name.strip(),
        description=body.description,
        source=body.source or "manual",
        locked=body.locked,
        status=body.status,
        notes=body.notes,
        color=body.color,
        tags_json=json.dumps(body.tags) if body.tags else None,
    )
    db.add(char)
    db.flush()

    for alias_name in body.aliases:
        a_name = alias_name.strip()
        if a_name and a_name.lower() != char.canonical_name.lower():
            db.add(Alias(character_id=char.id, name=a_name, source="manual"))

    for fact_in in body.initial_facts:
        db.add(
            Fact(
                story_id=story_id,
                character_id=char.id,
                attribute=fact_in.attribute.strip().lower(),
                value=fact_in.value.strip(),
                quote=fact_in.quote,
                chapter_id=fact_in.chapter_id,
                confidence=fact_in.confidence,
                source="manual",
                locked=fact_in.locked,
            )
        )

    db.commit()
    data = get_character_with_facts(db, char.id)
    if not data:
        raise HTTPException(status_code=500, detail="Failed to retrieve created character.")
    return CharacterDetailOut(**data)


@router.patch("/characters/{character_id}", response_model=CharacterDetailOut)
def update_character_endpoint(
    character_id: int,
    body: CharacterUpdate,
    db: Session = Depends(get_db),
) -> CharacterDetailOut:
    char = db.query(Character).filter(Character.id == character_id).first()
    if not char:
        raise HTTPException(status_code=404, detail="Character not found.")

    if body.canonical_name is not None:
        char.canonical_name = body.canonical_name.strip()
    if body.description is not None:
        char.description = body.description
    if body.status is not None:
        char.status = body.status
    if body.notes is not None:
        char.notes = body.notes
    if body.color is not None:
        char.color = body.color
    if body.tags is not None:
        char.tags_json = json.dumps(body.tags)
    if body.locked is not None:
        char.locked = body.locked

    db.commit()
    data = get_character_with_facts(db, char.id)
    if not data:
        raise HTTPException(status_code=500, detail="Failed to retrieve updated character.")
    return CharacterDetailOut(**data)


@router.delete("/characters/{character_id}", response_model=MessageOut)
def delete_character_endpoint(
    character_id: int,
    db: Session = Depends(get_db),
) -> MessageOut:
    char = db.query(Character).filter(Character.id == character_id).first()
    if not char:
        raise HTTPException(status_code=404, detail="Character not found.")

    from qifrey.db.models import Relationship

    db.query(Alias).filter(Alias.character_id == character_id).delete(synchronize_session=False)
    db.query(Fact).filter(Fact.character_id == character_id).delete(synchronize_session=False)
    db.query(Relationship).filter(
        (Relationship.source_character_id == character_id)
        | (Relationship.target_character_id == character_id)
    ).delete(synchronize_session=False)
    db.delete(char)
    db.commit()
    return MessageOut(detail=f"Character {character_id} deleted.")


@router.post("/characters/{character_id}/aliases", response_model=AliasOut, status_code=201)
def add_alias(
    character_id: int,
    body: AliasCreate,
    db: Session = Depends(get_db),
) -> AliasOut:
    char = db.query(Character).filter(Character.id == character_id).first()
    if not char:
        raise HTTPException(status_code=404, detail="Character not found.")

    alias_name = body.name.strip()
    if not alias_name:
        raise HTTPException(status_code=400, detail="Alias name cannot be empty.")

    alias = (
        db.query(Alias)
        .filter(Alias.character_id == character_id, func.lower(Alias.name) == alias_name.lower())
        .first()
    )
    if not alias:
        alias = Alias(character_id=character_id, name=alias_name, source="manual")
        db.add(alias)
        db.commit()
        db.refresh(alias)
    return AliasOut(
        id=alias.id,
        character_id=alias.character_id,
        name=alias.name,
        source=alias.source,
    )


@router.delete("/aliases/{alias_id}", response_model=MessageOut)
def delete_alias_endpoint(
    alias_id: int,
    db: Session = Depends(get_db),
) -> MessageOut:
    alias = db.query(Alias).filter(Alias.id == alias_id).first()
    if not alias:
        raise HTTPException(status_code=404, detail="Alias not found.")
    db.delete(alias)
    db.commit()
    return MessageOut(detail=f"Alias {alias_id} deleted.")


@router.post("/characters/{character_id}/facts", response_model=FactDetailOut, status_code=201)
def add_character_fact(
    character_id: int,
    body: FactCreateItem,
    db: Session = Depends(get_db),
) -> FactDetailOut:
    char = db.query(Character).filter(Character.id == character_id).first()
    if not char:
        raise HTTPException(status_code=404, detail="Character not found.")

    fact = Fact(
        story_id=char.story_id,
        character_id=character_id,
        attribute=body.attribute.strip().lower(),
        value=body.value.strip(),
        quote=body.quote,
        chapter_id=body.chapter_id,
        confidence=body.confidence,
        source="manual",
        locked=body.locked,
    )
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return FactDetailOut.model_validate(fact)


@router.patch("/facts/{fact_id}", response_model=FactDetailOut)
def update_fact_endpoint(
    fact_id: int,
    body: FactUpdate,
    db: Session = Depends(get_db),
) -> FactDetailOut:
    fact = db.query(Fact).filter(Fact.id == fact_id).first()
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found.")

    if body.attribute is not None:
        fact.attribute = body.attribute.strip().lower()
    if body.value is not None:
        fact.value = body.value.strip()
    if body.quote is not None:
        fact.quote = body.quote
    if body.confidence is not None:
        fact.confidence = body.confidence
    if body.locked is not None:
        fact.locked = body.locked

    db.commit()
    db.refresh(fact)
    return FactDetailOut.model_validate(fact)


@router.delete("/facts/{fact_id}", response_model=MessageOut)
def delete_fact_endpoint(
    fact_id: int,
    db: Session = Depends(get_db),
) -> MessageOut:
    fact = db.query(Fact).filter(Fact.id == fact_id).first()
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found.")
    db.delete(fact)
    db.commit()
    return MessageOut(detail=f"Fact {fact_id} deleted.")


@router.post("/stories/{story_id}/characters/merge", response_model=CharacterDetailOut)
def merge_characters_endpoint(
    story_id: int,
    body: CharacterMergeRequest,
    db: Session = Depends(get_db),
) -> CharacterDetailOut:
    target = merge_characters(db, story_id, body.source_ids, body.target_id)
    if not target:
        raise HTTPException(status_code=400, detail="Failed to merge characters.")
    data = get_character_with_facts(db, target.id)
    if not data:
        raise HTTPException(status_code=500, detail="Failed to retrieve merged character.")
    return CharacterDetailOut(**data)


@router.post("/characters/{character_id}/ignore", response_model=MessageOut)
def ignore_character_endpoint(
    character_id: int,
    db: Session = Depends(get_db),
) -> MessageOut:
    ignored = ignore_character(db, character_id)
    if not ignored:
        raise HTTPException(status_code=404, detail="Character not found.")
    return MessageOut(detail="Character ignored and removed.")


@router.get("/stories/{story_id}/attribute-rules", response_model=list[AttributeRuleSchema])
def get_attribute_rules(
    story_id: int,
    db: Session = Depends(get_db),
) -> list[AttributeRuleSchema]:
    rules = db.query(AttributeRule).filter(AttributeRule.story_id == story_id).all()
    return [AttributeRuleSchema.model_validate(r) for r in rules]


@router.put("/stories/{story_id}/attribute-rules", response_model=list[AttributeRuleSchema])
def update_attribute_rules(
    story_id: int,
    rules_in: list[AttributeRuleSchema],
    db: Session = Depends(get_db),
) -> list[AttributeRuleSchema]:
    db.query(AttributeRule).filter(AttributeRule.story_id == story_id).delete(
        synchronize_session=False
    )
    created_rules: list[AttributeRule] = []
    for r in rules_in:
        rule = AttributeRule(
            story_id=story_id,
            attribute=r.attribute.strip().lower(),
            mode=r.mode,
        )
        db.add(rule)
        created_rules.append(rule)
    db.commit()
    return [AttributeRuleSchema.model_validate(r) for r in created_rules]


@router.get("/stories/{story_id}/settings", response_model=StorySettings)
def get_story_settings(
    story_id: int,
    db: Session = Depends(get_db),
) -> StorySettings:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")
    if not story.settings_json:
        return StorySettings()
    try:
        data = json.loads(story.settings_json)
        return StorySettings(**data)
    except Exception:
        return StorySettings()


@router.patch("/stories/{story_id}/settings", response_model=StorySettings)
def update_story_settings(
    story_id: int,
    body: StorySettingsUpdate,
    db: Session = Depends(get_db),
) -> StorySettings:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")

    curr = StorySettings()
    if story.settings_json:
        with contextlib.suppress(Exception):
            curr = StorySettings(**json.loads(story.settings_json))

    curr_dict = curr.model_dump()
    update_data = body.model_dump(exclude_unset=True)
    curr_dict.update(update_data)

    story.settings_json = json.dumps(curr_dict)
    db.commit()
    return StorySettings(**curr_dict)


@router.get("/stories/{story_id}/export")
def export_story(
    story_id: int,
    format: Literal["json", "md"] = Query(default="json"),
    db: Session = Depends(get_db),
) -> Response:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")

    chapters = db.query(Chapter).filter(Chapter.story_id == story_id).order_by(Chapter.index).all()
    characters = list_characters(db, story_id)
    rules = db.query(AttributeRule).filter(AttributeRule.story_id == story_id).all()
    ignored = db.query(IgnoredName).filter(IgnoredName.story_id == story_id).all()

    if format == "json":
        data = {
            "version": "1.0",
            "story": {
                "title": story.title,
                "summary": story.summary,
                "settings": json.loads(story.settings_json) if story.settings_json else {},
            },
            "attribute_rules": [{"attribute": r.attribute, "mode": r.mode} for r in rules],
            "ignored_names": [i.name for i in ignored],
            "chapters": [
                {
                    "index": c.index,
                    "title": c.title,
                    "text": c.text,
                    "exclude_from_analysis": c.exclude_from_analysis,
                }
                for c in chapters
            ],
            "characters": [get_character_with_facts(db, c.id) for c in characters],
        }
        json_str = json.dumps(data, indent=2, default=str)
        return Response(
            content=json_str,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{story.title}-bible.json"'},
        )

    # Markdown export
    md_lines = [
        f"# Story Bible: {story.title}",
        "",
        story.summary or "No summary available.",
        "",
        "## Characters",
        "",
    ]
    for c in characters:
        c_data = get_character_with_facts(db, c.id)
        if not c_data:
            continue
        md_lines.append(
            f"### {c_data['canonical_name']} [{c_data['status']}] ({c_data['source']})"
        )
        if c_data.get("aliases"):
            md_lines.append(f"- **Aliases:** {', '.join(c_data['aliases'])}")
        if c_data.get("description"):
            md_lines.append(f"- **Description:** {c_data['description']}")
        if c_data.get("notes"):
            md_lines.append(f"- **Notes:** {c_data['notes']}")
        if c_data.get("facts"):
            md_lines.append("- **Facts:**")
            for f in c_data["facts"]:
                ch_lbl = f"Ch. {f['chapter_id']}" if f.get("chapter_id") else "Author Notes"
                l_badge = " [locked]" if f.get("locked") else ""
                md_lines.append(f"  - **{f['attribute']}**: {f['value']} ({ch_lbl}){l_badge}")
        md_lines.append("")

    if rules:
        md_lines.append("## Attribute Rules")
        md_lines.append("")
        for r in rules:
            md_lines.append(f"- **{r.attribute}**: `{r.mode}`")
        md_lines.append("")

    if ignored:
        md_lines.append("## Ignored Names")
        md_lines.append("")
        for ign in ignored:
            md_lines.append(f"- {ign.name}")
        md_lines.append("")

    md_str = "\n".join(md_lines)
    return Response(
        content=md_str,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{story.title}-bible.md"'},
    )


@router.post("/stories/{story_id}/import", response_model=MessageOut)
def import_story_bible(
    story_id: int,
    body: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> MessageOut:
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")

    # Settings
    if "story" in body and isinstance(body["story"], dict):
        st_info = body["story"]
        if "settings" in st_info and isinstance(st_info["settings"], dict):
            story.settings_json = json.dumps(st_info["settings"])

    # Attribute rules
    if "attribute_rules" in body and isinstance(body["attribute_rules"], list):
        for r in body["attribute_rules"]:
            attr = r.get("attribute", "").strip().lower()
            mode = r.get("mode", "strict")
            if attr:
                existing = (
                    db.query(AttributeRule)
                    .filter(
                        AttributeRule.story_id == story_id,
                        AttributeRule.attribute == attr,
                    )
                    .first()
                )
                if existing:
                    existing.mode = mode
                else:
                    db.add(AttributeRule(story_id=story_id, attribute=attr, mode=mode))

    # Ignored names
    if "ignored_names" in body and isinstance(body["ignored_names"], list):
        for ign_name in body["ignored_names"]:
            name_clean = str(ign_name).strip()
            if name_clean:
                existing_ign = (
                    db.query(IgnoredName)
                    .filter(
                        IgnoredName.story_id == story_id,
                        func.lower(IgnoredName.name) == name_clean.lower(),
                    )
                    .first()
                )
                if not existing_ign:
                    db.add(IgnoredName(story_id=story_id, name=name_clean))

    # Characters
    if "characters" in body and isinstance(body["characters"], list):
        for c_data in body["characters"]:
            name = c_data.get("canonical_name", "").strip()
            if not name:
                continue
            char = (
                db.query(Character)
                .filter(
                    Character.story_id == story_id,
                    func.lower(Character.canonical_name) == name.lower(),
                )
                .first()
            )
            if not char:
                char = Character(
                    story_id=story_id,
                    canonical_name=name,
                    source=c_data.get("source", "manual"),
                    locked=bool(c_data.get("locked", False)),
                    status=c_data.get("status", "active"),
                    description=c_data.get("description"),
                    notes=c_data.get("notes"),
                    color=c_data.get("color"),
                    tags_json=json.dumps(c_data.get("tags", [])) if c_data.get("tags") else None,
                )
                db.add(char)
                db.flush()
            else:
                if c_data.get("description"):
                    char.description = c_data["description"]
                if c_data.get("notes"):
                    char.notes = c_data["notes"]
                if c_data.get("status"):
                    char.status = c_data["status"]
                if "locked" in c_data:
                    char.locked = bool(c_data["locked"])
                if c_data.get("color"):
                    char.color = c_data["color"]
                if c_data.get("tags"):
                    char.tags_json = json.dumps(c_data["tags"])

            # Aliases
            for alias in c_data.get("aliases", []):
                a_str = str(alias).strip()
                if a_str and a_str.lower() != name.lower():
                    exist_a = (
                        db.query(Alias)
                        .filter(
                            Alias.character_id == char.id,
                            func.lower(Alias.name) == a_str.lower(),
                        )
                        .first()
                    )
                    if not exist_a:
                        db.add(Alias(character_id=char.id, name=a_str, source="manual"))

            # Facts
            for f in c_data.get("facts", []):
                attr = f.get("attribute", "").strip().lower()
                val = f.get("value", "").strip()
                if attr and val:
                    exist_f = (
                        db.query(Fact)
                        .filter(
                            Fact.story_id == story_id,
                            Fact.character_id == char.id,
                            Fact.attribute == attr,
                            Fact.value == val,
                        )
                        .first()
                    )
                    if not exist_f:
                        db.add(
                            Fact(
                                story_id=story_id,
                                character_id=char.id,
                                attribute=attr,
                                value=val,
                                quote=f.get("quote"),
                                confidence=float(f.get("confidence", 1.0)),
                                source=f.get("source", "manual"),
                                locked=bool(f.get("locked", False)),
                            )
                        )

    db.commit()
    return MessageOut(detail="Story bible imported successfully.")
