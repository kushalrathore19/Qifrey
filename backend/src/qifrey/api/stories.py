"""Story and chapter API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from qifrey.api.schemas import (
    AnalysisStatusOut,
    ChapterBrief,
    ChapterOut,
    CharacterBriefOut,
    CharacterDetailOut,
    MessageOut,
    StoryCreate,
    StoryDetail,
    StoryOut,
)
from qifrey.config import get_settings
from qifrey.db.models import Chapter, Fact, Story
from qifrey.db.session import get_db
from qifrey.graph.store import get_character_with_facts, list_characters
from qifrey.ingestion.txt_parser import decode_upload, parse_chapters
from qifrey.pipeline.runner import analyze_story, get_story_analysis_status

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
        results.append(
            CharacterBriefOut(
                id=c.id,
                story_id=c.story_id,
                canonical_name=c.canonical_name,
                description=c.description,
                aliases=[a.name for a in c.aliases],
                fact_count=fact_count,
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
