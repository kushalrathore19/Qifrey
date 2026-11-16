"""Pydantic v2 schemas for API request/response."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class StoryCreate(BaseModel):
    title: str = "Untitled"


class StoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    chapter_count: int = 0


class StoryDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    index: int
    title: str
    text: str
    content_hash: str
    analyzed_hash: str | None = None


class ChapterBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    index: int
    title: str
    content_hash: str
    analyzed_hash: str | None = None


class MessageOut(BaseModel):
    detail: str


class FactDetailOut(BaseModel):
    id: int
    attribute: str
    value: str
    chapter_id: int
    quote: str | None = None
    confidence: float = 1.0


class RelationshipDetailOut(BaseModel):
    id: int
    type: str
    source_character_id: int
    target_character_id: int
    chapter_id: int
    quote: str | None = None


class CharacterBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    canonical_name: str
    description: str | None = None
    aliases: list[str] = []
    fact_count: int = 0


class CharacterDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    canonical_name: str
    description: str | None = None
    aliases: list[str] = []
    facts: list[FactDetailOut] = []
    relationships: list[RelationshipDetailOut] = []


class AnalysisStatusOut(BaseModel):
    story_id: int
    status: str
    current_chapter: int
    total_chapters: int
    error: str | None = None
