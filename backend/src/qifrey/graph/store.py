"""Storage operations for characters, facts, locations, and relationships."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qifrey.db.models import Alias, Character, Fact, Location, Relationship

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def upsert_character(
    db: Session,
    story_id: int,
    canonical_name: str,
    *,
    description: str | None = None,
    aliases: list[str] | None = None,
) -> Character:
    """Find an existing character by canonical name or create a new one."""
    char = (
        db.query(Character)
        .filter(
            Character.story_id == story_id,
            Character.canonical_name == canonical_name.strip(),
        )
        .first()
    )

    if not char:
        char = Character(
            story_id=story_id,
            canonical_name=canonical_name.strip(),
            description=description,
        )
        db.add(char)
        db.flush()
    elif description and not char.description:
        char.description = description

    if aliases:
        existing_aliases = {a.name.strip().lower() for a in char.aliases}
        for alias_name in aliases:
            norm = alias_name.strip().lower()
            if norm and norm != char.canonical_name.lower() and norm not in existing_aliases:
                db.add(Alias(character_id=char.id, name=alias_name.strip()))
                existing_aliases.add(norm)
        db.flush()

    return char


def upsert_location(
    db: Session,
    story_id: int,
    name: str,
    *,
    description: str | None = None,
) -> Location:
    """Find an existing location by name or create a new one."""
    clean_name = name.strip()
    loc = (
        db.query(Location)
        .filter(Location.story_id == story_id, Location.name == clean_name)
        .first()
    )
    if not loc:
        loc = Location(story_id=story_id, name=clean_name, description=description)
        db.add(loc)
        db.flush()
    elif description and not loc.description:
        loc.description = description

    return loc


def upsert_fact(
    db: Session,
    *,
    story_id: int,
    character_id: int,
    attribute: str,
    value: str,
    chapter_id: int,
    quote: str | None = None,
    confidence: float = 1.0,
) -> Fact:
    """Insert or update a fact for a character."""
    existing = (
        db.query(Fact)
        .filter(
            Fact.story_id == story_id,
            Fact.character_id == character_id,
            Fact.attribute == attribute.strip(),
            Fact.value == value.strip(),
            Fact.chapter_id == chapter_id,
        )
        .first()
    )

    if existing:
        if quote:
            existing.quote = quote
        existing.confidence = max(existing.confidence, confidence)
        return existing

    new_fact = Fact(
        story_id=story_id,
        character_id=character_id,
        attribute=attribute.strip(),
        value=value.strip(),
        chapter_id=chapter_id,
        quote=quote,
        confidence=confidence,
    )
    db.add(new_fact)
    db.flush()
    return new_fact


def upsert_relationship(
    db: Session,
    *,
    story_id: int,
    source_character_id: int,
    target_character_id: int,
    type_: str,
    chapter_id: int,
    quote: str | None = None,
) -> Relationship:
    """Insert or update a relationship between two characters."""
    existing = (
        db.query(Relationship)
        .filter(
            Relationship.story_id == story_id,
            Relationship.source_character_id == source_character_id,
            Relationship.target_character_id == target_character_id,
            Relationship.type == type_.strip(),
            Relationship.chapter_id == chapter_id,
        )
        .first()
    )

    if existing:
        if quote:
            existing.quote = quote
        return existing

    new_rel = Relationship(
        story_id=story_id,
        source_character_id=source_character_id,
        target_character_id=target_character_id,
        type=type_.strip(),
        chapter_id=chapter_id,
        quote=quote,
    )
    db.add(new_rel)
    db.flush()
    return new_rel


def delete_chapter_data(db: Session, chapter_id: int) -> None:
    """Delete all facts and relationships whose provenance is that chapter."""
    db.query(Fact).filter(Fact.chapter_id == chapter_id).delete(synchronize_session=False)
    db.query(Relationship).filter(Relationship.chapter_id == chapter_id).delete(
        synchronize_session=False
    )
    db.flush()


def list_characters(db: Session, story_id: int) -> list[Character]:
    """Return all characters for a story, ordered by canonical name."""
    return (
        db.query(Character)
        .filter(Character.story_id == story_id)
        .order_by(Character.canonical_name)
        .all()
    )


def get_character_with_facts(db: Session, character_id: int) -> dict[str, Any] | None:
    """Return detailed dictionary for a character, including aliases, facts, and relationships."""
    char = db.query(Character).filter(Character.id == character_id).first()
    if not char:
        return None

    facts = (
        db.query(Fact)
        .filter(Fact.character_id == character_id)
        .order_by(Fact.chapter_id, Fact.attribute)
        .all()
    )

    relationships = (
        db.query(Relationship)
        .filter(
            (Relationship.source_character_id == character_id)
            | (Relationship.target_character_id == character_id)
        )
        .all()
    )

    return {
        "id": char.id,
        "story_id": char.story_id,
        "canonical_name": char.canonical_name,
        "description": char.description,
        "aliases": [a.name for a in char.aliases],
        "facts": [
            {
                "id": f.id,
                "attribute": f.attribute,
                "value": f.value,
                "chapter_id": f.chapter_id,
                "quote": f.quote,
                "confidence": f.confidence,
            }
            for f in facts
        ],
        "relationships": [
            {
                "id": r.id,
                "type": r.type,
                "source_character_id": r.source_character_id,
                "target_character_id": r.target_character_id,
                "chapter_id": r.chapter_id,
                "quote": r.quote,
            }
            for r in relationships
        ],
    }
