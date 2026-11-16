"""SQLAlchemy ORM models for the Qifrey story graph."""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="Untitled")
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    characters: Mapped[list[Character]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    locations: Mapped[list[Location]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    facts: Mapped[list[Fact]] = relationship(back_populates="story", cascade="all, delete-orphan")
    relationships_: Mapped[list[Relationship]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    issues: Mapped[list[Issue]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    llm_calls: Mapped[list[LLMCall]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    analyzed_hash: Mapped[str | None] = mapped_column(String(64), default=None)

    story: Mapped[Story] = relationship(back_populates="chapters")
    facts: Mapped[list[Fact]] = relationship(back_populates="chapter")
    relationships_: Mapped[list[Relationship]] = relationship(back_populates="chapter")
    issues: Mapped[list[Issue]] = relationship(back_populates="chapter")


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"))
    canonical_name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    story: Mapped[Story] = relationship(back_populates="characters")
    aliases: Mapped[list[Alias]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )
    facts: Mapped[list[Fact]] = relationship(back_populates="character")
    source_relationships: Mapped[list[Relationship]] = relationship(
        back_populates="source_character",
        foreign_keys="Relationship.source_character_id",
    )
    target_relationships: Mapped[list[Relationship]] = relationship(
        back_populates="target_character",
        foreign_keys="Relationship.target_character_id",
    )


class Alias(Base):
    __tablename__ = "aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(300))

    character: Mapped[Character] = relationship(back_populates="aliases")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    story: Mapped[Story] = relationship(back_populates="locations")


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"))
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    attribute: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    quote: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    story: Mapped[Story] = relationship(back_populates="facts")
    character: Mapped[Character] = relationship(back_populates="facts")
    chapter: Mapped[Chapter] = relationship(back_populates="facts")


class Relationship(Base):
    __tablename__ = "character_relationships"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"))
    source_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE")
    )
    target_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE")
    )
    type: Mapped[str] = mapped_column(String(100))
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    quote: Mapped[str | None] = mapped_column(Text, default=None)

    story: Mapped[Story] = relationship(back_populates="relationships_")
    source_character: Mapped[Character] = relationship(
        back_populates="source_relationships", foreign_keys=[source_character_id]
    )
    target_character: Mapped[Character] = relationship(
        back_populates="target_relationships", foreign_keys=[target_character_id]
    )
    chapter: Mapped[Chapter] = relationship(back_populates="relationships_")


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20))  # "contradiction" | "grammar"
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), default=None
    )
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    message: Mapped[str] = mapped_column(Text)
    quote: Mapped[str | None] = mapped_column(Text, default=None)
    span_start: Mapped[int | None] = mapped_column(Integer, default=None)
    span_end: Mapped[int | None] = mapped_column(Integer, default=None)
    suggestions_json: Mapped[str | None] = mapped_column(Text, default=None)
    related_fact_ids_json: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open|dismissed|accepted|intentional
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped[Story] = relationship(back_populates="issues")
    chapter: Mapped[Chapter | None] = relationship(back_populates="issues")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped[Story] = relationship(back_populates="llm_calls")
