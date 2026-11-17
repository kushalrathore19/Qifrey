"""Storage operations for characters, facts, locations, and relationships."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from qifrey.db.models import Alias, Character, Fact, IgnoredName, Location, Relationship

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def upsert_character(
    db: Session,
    story_id: int,
    canonical_name: str,
    *,
    description: str | None = None,
    aliases: list[str] | None = None,
    source: str = "ai",
    locked: bool = False,
    status: str = "active",
    notes: str | None = None,
    color: str | None = None,
    tags: list[str] | None = None,
) -> Character | None:
    """Find an existing character by canonical name or create a new one."""
    clean_name = canonical_name.strip()

    # Check if name is in IgnoredName
    ignored = (
        db.query(IgnoredName)
        .filter(
            IgnoredName.story_id == story_id,
            IgnoredName.name == clean_name,
        )
        .first()
    )
    if ignored:
        return None

    char = (
        db.query(Character)
        .filter(
            Character.story_id == story_id,
            Character.canonical_name == clean_name,
        )
        .first()
    )

    tags_str = json.dumps(tags) if tags else None

    if not char:
        char = Character(
            story_id=story_id,
            canonical_name=clean_name,
            description=description,
            source=source,
            locked=locked,
            status=status,
            notes=notes,
            color=color,
            tags_json=tags_str,
        )
        db.add(char)
        db.flush()
    else:
        # If existing character is planned, transition to active
        if char.status == "planned":
            char.status = "active"
        if not char.locked:
            if description and not char.description:
                char.description = description
            if notes and not char.notes:
                char.notes = notes
            if color and not char.color:
                char.color = color

    if aliases:
        existing_aliases = {a.name.strip().lower() for a in char.aliases}
        for alias_name in aliases:
            norm = alias_name.strip().lower()
            if norm and norm != char.canonical_name.lower() and norm not in existing_aliases:
                db.add(Alias(character_id=char.id, name=alias_name.strip(), source=source))
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
    chapter_id: int | None = None,
    quote: str | None = None,
    confidence: float = 1.0,
    source: str = "ai",
    locked: bool = False,
) -> Fact:
    """Insert or update a fact for a character."""
    clean_attr = attribute.strip()
    clean_val = value.strip()

    query = db.query(Fact).filter(
        Fact.story_id == story_id,
        Fact.character_id == character_id,
        Fact.attribute == clean_attr,
        Fact.value == clean_val,
    )
    if chapter_id is not None:
        query = query.filter(Fact.chapter_id == chapter_id)
    else:
        query = query.filter(Fact.chapter_id.is_(None))

    existing = query.first()

    if existing:
        if not existing.locked:
            if quote:
                existing.quote = quote
            existing.confidence = max(existing.confidence, confidence)
        return existing

    new_fact = Fact(
        story_id=story_id,
        character_id=character_id,
        attribute=clean_attr,
        value=clean_val,
        chapter_id=chapter_id,
        quote=quote,
        confidence=confidence,
        source=source,
        locked=locked,
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
    chapter_id: int | None = None,
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
    """Delete AI/unlocked facts and relationships for a chapter.

    Never deletes manual or locked facts.
    """
    db.query(Fact).filter(
        Fact.chapter_id == chapter_id,
        Fact.source != "manual",
        Fact.locked.is_(False),
    ).delete(synchronize_session=False)
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

    tags: list[str] = []
    if char.tags_json:
        try:
            tags = json.loads(char.tags_json)
        except Exception:
            tags = []

    return {
        "id": char.id,
        "story_id": char.story_id,
        "canonical_name": char.canonical_name,
        "description": char.description,
        "source": char.source,
        "locked": char.locked,
        "status": char.status,
        "notes": char.notes,
        "color": char.color,
        "tags": tags,
        "aliases": [a.name for a in char.aliases],
        "facts": [
            {
                "id": f.id,
                "attribute": f.attribute,
                "value": f.value,
                "chapter_id": f.chapter_id,
                "quote": f.quote,
                "confidence": f.confidence,
                "source": f.source,
                "locked": f.locked,
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


def merge_characters(
    db: Session,
    story_id: int,
    source_ids: list[int],
    target_id: int,
) -> Character:
    """Merge source characters into target character. Preserves names as aliases on target."""
    target = (
        db.query(Character)
        .filter(Character.id == target_id, Character.story_id == story_id)
        .first()
    )
    if not target:
        raise ValueError(f"Target character {target_id} not found")

    existing_aliases = {a.name.strip().lower() for a in target.aliases}

    for s_id in source_ids:
        if s_id == target_id:
            continue
        source = (
            db.query(Character)
            .filter(Character.id == s_id, Character.story_id == story_id)
            .first()
        )
        if not source:
            continue

        # Add source canonical name as an alias of target
        norm_canonical = source.canonical_name.strip().lower()
        if (
            norm_canonical != target.canonical_name.strip().lower()
            and norm_canonical not in existing_aliases
        ):
            db.add(
                Alias(
                    character_id=target.id,
                    name=source.canonical_name.strip(),
                    source="manual",
                )
            )
            existing_aliases.add(norm_canonical)

        # Move aliases from source to target
        for a in source.aliases:
            norm_a = a.name.strip().lower()
            if norm_a != target.canonical_name.strip().lower() and norm_a not in existing_aliases:
                db.add(
                    Alias(
                        character_id=target.id,
                        name=a.name.strip(),
                        source=a.source,
                    )
                )
                existing_aliases.add(norm_a)

        # Move facts from source to target
        for f in list(source.facts):
            dup = (
                db.query(Fact)
                .filter(
                    Fact.character_id == target.id,
                    Fact.attribute == f.attribute,
                    Fact.value == f.value,
                    Fact.chapter_id == f.chapter_id,
                )
                .first()
            )
            if not dup:
                f.character_id = target.id
            else:
                db.delete(f)

        # Move relationships
        db.query(Relationship).filter(Relationship.source_character_id == source.id).update(
            {"source_character_id": target.id}, synchronize_session=False
        )
        db.query(Relationship).filter(Relationship.target_character_id == source.id).update(
            {"target_character_id": target.id}, synchronize_session=False
        )

        db.delete(source)

    db.commit()
    db.refresh(target)
    return target


def ignore_character(db: Session, character_id: int) -> list[str]:
    """Delete an AI character and add its canonical name and aliases to IgnoredName."""
    char = db.query(Character).filter(Character.id == character_id).first()
    if not char:
        raise ValueError(f"Character {character_id} not found")

    story_id = char.story_id
    aliases = db.query(Alias).filter(Alias.character_id == character_id).all()
    names_to_ignore = [char.canonical_name] + [a.name for a in aliases]

    for name in names_to_ignore:
        clean = name.strip()
        if clean:
            existing = (
                db.query(IgnoredName)
                .filter(
                    IgnoredName.story_id == story_id,
                    IgnoredName.name == clean,
                )
                .first()
            )
            if not existing:
                db.add(IgnoredName(story_id=story_id, name=clean))

    db.delete(char)
    db.commit()
    return names_to_ignore
