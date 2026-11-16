"""Tests for alias resolution logic."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from qifrey.db.models import Character, Story
from qifrey.graph.alias_resolver import (
    clear_resolution_cache,
    resolve_or_create_character,
    strip_honorifics,
)
from qifrey.pipeline.llm_client import FakeLLMClient
from qifrey.pipeline.schemas import AliasResolutionOutput


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_resolution_cache()


def test_strip_honorifics() -> None:
    assert strip_honorifics("Dr. John Watson") == "John Watson"
    assert strip_honorifics("Miss Mitchell") == "Mitchell"
    assert strip_honorifics("Detective Inspector Lestrade") == "Inspector Lestrade"
    assert strip_honorifics("Lord Blackwood") == "Blackwood"
    assert strip_honorifics("Sarah") == "Sarah"


def test_resolve_exact_and_case_insensitive(client: Any) -> None:
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="Test Story")
        db.add(story)
        db.flush()

        char = Character(story_id=story.id, canonical_name="Sarah Mitchell")
        db.add(char)
        db.commit()

        # Exact
        res1 = resolve_or_create_character("Sarah Mitchell", story.id, db)
        assert res1.id == char.id

        # Case-insensitive
        res2 = resolve_or_create_character("sarah mitchell", story.id, db)
        assert res2.id == char.id


def test_resolve_honorific_and_surname_miss_mitchell(client: Any) -> None:
    """Cover alias resolution: 'Sarah' / 'Miss Mitchell' -> matches 'Sarah Mitchell'."""
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="Mystery")
        db.add(story)
        db.flush()

        sarah = Character(story_id=story.id, canonical_name="Sarah Mitchell")
        db.add(sarah)
        db.commit()

        # "Miss Mitchell" should resolve to Sarah Mitchell
        # via honorific strip + single surname match
        res_miss = resolve_or_create_character("Miss Mitchell", story.id, db)
        assert res_miss.id == sarah.id

        # "Sarah" should also resolve to Sarah Mitchell as unambiguous single name match
        res_sarah = resolve_or_create_character("Sarah", story.id, db)
        assert res_sarah.id == sarah.id

        # Verify aliases were attached
        db.refresh(sarah)
        alias_names = [a.name.lower() for a in sarah.aliases]
        assert "miss mitchell" in alias_names or "mitchell" in alias_names


def test_resolve_ambiguous_uses_llm(client: Any) -> None:
    """When multiple characters share a surname, resolve ambiguity using LLM."""
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="Two Mitchells")
        db.add(story)
        db.flush()

        sarah = Character(
            story_id=story.id, canonical_name="Sarah Mitchell", description="A young scholar"
        )
        john = Character(
            story_id=story.id, canonical_name="John Mitchell", description="A retired captain"
        )
        db.add_all([sarah, john])
        db.commit()

        # Mock LLM to resolve "Mitchell" to "Sarah Mitchell"
        fake_llm = FakeLLMClient(
            responses=[
                AliasResolutionOutput(
                    is_same_person=True,
                    canonical_name="Sarah Mitchell",
                    confidence=0.95,
                    explanation="Context clearly describes the scholar",
                )
            ]
        )

        res = resolve_or_create_character("Mitchell", story.id, db, llm_client=fake_llm)
        assert res.id == sarah.id


def test_create_new_character_when_no_match(client: Any) -> None:
    from qifrey.db.session import get_engine

    with Session(get_engine()) as db:
        story = Story(title="New Character Story")
        db.add(story)
        db.commit()

        char = resolve_or_create_character("Qifrey", story.id, db, description="Master of ink")
        assert char.id is not None
        assert char.canonical_name == "Qifrey"
        assert char.description == "Master of ink"
