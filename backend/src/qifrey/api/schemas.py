"""Pydantic v2 schemas for API request/response."""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class StoryCreate(BaseModel):
    title: str = "Untitled"


class StorySettings(BaseModel):
    confidence_threshold: float = 0.7
    grammar_language: str = "en-US"
    disabled_grammar_rules: list[str] = []


class StorySettingsUpdate(BaseModel):
    confidence_threshold: float | None = None
    grammar_language: str | None = None
    disabled_grammar_rules: list[str] | None = None


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
    settings_json: str | None = None
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
    exclude_from_analysis: bool = False


class ChapterBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    index: int
    title: str
    content_hash: str
    analyzed_hash: str | None = None
    summary: str | None = None
    exclude_from_analysis: bool = False


class ChapterCreate(BaseModel):
    title: str = "New Chapter"
    text: str = ""
    index: int | None = None
    exclude_from_analysis: bool = False


class ChapterUpdate(BaseModel):
    title: str | None = None
    text: str | None = None
    index: int | None = None
    exclude_from_analysis: bool | None = None


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
    model_config = ConfigDict(from_attributes=True)

    id: int
    attribute: str
    value: str
    chapter_id: int | None = None
    quote: str | None = None
    confidence: float = 1.0
    source: str = "ai"
    locked: bool = False


class FactCreateItem(BaseModel):
    attribute: str
    value: str
    quote: str | None = None
    chapter_id: int | None = None
    confidence: float = 1.0
    locked: bool = False


class FactUpdate(BaseModel):
    attribute: str | None = None
    value: str | None = None
    quote: str | None = None
    confidence: float | None = None
    locked: bool | None = None


class RelationshipDetailOut(BaseModel):
    id: int
    type: str
    source_character_id: int
    target_character_id: int
    chapter_id: int | None = None
    quote: str | None = None


class CharacterBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    canonical_name: str
    description: str | None = None
    aliases: list[str] = []
    fact_count: int = 0
    source: str = "ai"
    locked: bool = False
    status: str = "active"
    notes: str | None = None
    color: str | None = None
    tags: list[str] = []


class CharacterDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    canonical_name: str
    description: str | None = None
    aliases: list[str] = []
    source: str = "ai"
    locked: bool = False
    status: str = "active"
    notes: str | None = None
    color: str | None = None
    tags: list[str] = []
    facts: list[FactDetailOut] = []
    relationships: list[RelationshipDetailOut] = []


class CharacterCreate(BaseModel):
    canonical_name: str
    description: str | None = None
    aliases: list[str] = []
    source: str = "manual"
    locked: bool = False
    status: str = "active"
    notes: str | None = None
    color: str | None = None
    tags: list[str] = []
    initial_facts: list[FactCreateItem] = []


class CharacterUpdate(BaseModel):
    canonical_name: str | None = None
    description: str | None = None
    status: str | None = None
    notes: str | None = None
    color: str | None = None
    tags: list[str] | None = None
    locked: bool | None = None


class AliasCreate(BaseModel):
    name: str


class AliasOut(BaseModel):
    id: int
    character_id: int
    name: str
    source: str = "manual"


class CharacterMergeRequest(BaseModel):
    source_ids: list[int]
    target_id: int


class AttributeRuleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    attribute: str
    mode: Literal["strict", "can_change", "ignore"] = "strict"


class IgnoredNameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    name: str


class AnalysisStatusOut(BaseModel):
    story_id: int
    status: str
    current_chapter: int
    total_chapters: int
    error: str | None = None


class GrammarStatusOut(BaseModel):
    available: bool
    message: str | None = None


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
    status: str = "open"
    created_at: datetime.datetime


class IssueStatusUpdate(BaseModel):
    status: Literal["open", "dismissed", "accepted", "intentional"]
