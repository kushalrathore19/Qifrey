"""Pydantic v2 schemas for API request/response."""

from __future__ import annotations

import datetime
from typing import Literal

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
    summary: str | None = None


class ChapterBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    index: int
    title: str
    content_hash: str
    analyzed_hash: str | None = None
    summary: str | None = None


class ChapterCreate(BaseModel):
    title: str = "New Chapter"
    text: str = ""
    index: int | None = None


class ChapterUpdate(BaseModel):
    title: str | None = None
    text: str | None = None
    index: int | None = None


class GrammarCheckRequest(BaseModel):
    text: str | None = None


class GrammarIssueOut(BaseModel):
    message: str
    rule_id: str
    span_start: int
    span_end: int
    quote: str
    suggestions: list[str] = []


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


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    type: str
    chapter_id: int | None = None
    severity: str
    message: str
    quote: str | None = None
    span_start: int | None = None
    span_end: int | None = None
    suggestions_json: str | None = None
    related_fact_ids_json: str | None = None
    status: str
    created_at: datetime.datetime


class IssueStatusUpdate(BaseModel):
    status: Literal["open", "dismissed", "accepted", "intentional"]
