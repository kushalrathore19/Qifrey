"""Tests for Phase 8: author-controlled story bible and flexibility."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from qifrey.db.models import AttributeRule, Chapter, Character, Fact, IgnoredName, Story
from qifrey.graph.alias_resolver import resolve_or_create_character
from qifrey.graph.store import (
    delete_chapter_data,
    get_character_with_facts,
    ignore_character,
    merge_characters,
    upsert_character,
)
from qifrey.insights.contradictions import AdjudicationOutput, detect_contradictions
from qifrey.pipeline.llm_client import FakeLLMClient

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_reanalysis_keeps_manual_characters_and_locked_facts(db_session: Session) -> None:
    """Manual characters and locked facts must never be deleted by delete_chapter_data."""
    story = Story(title="Test Bible Story")
    db_session.add(story)
    db_session.flush()

    chapter = Chapter(
        story_id=story.id,
        index=1,
        title="Chapter 1",
        text="Alice walked into the room.",
        content_hash="hash1",
    )
    db_session.add(chapter)
    db_session.flush()

    # Create an AI character with one unlocked fact
    ai_char = Character(
        story_id=story.id,
        canonical_name="Bob",
        source="ai",
        locked=False,
    )
    db_session.add(ai_char)
    db_session.flush()

    ai_fact = Fact(
        story_id=story.id,
        character_id=ai_char.id,
        attribute="hair",
        value="black",
        chapter_id=chapter.id,
        source="ai",
        locked=False,
    )
    db_session.add(ai_fact)

    # Create a manual character with a locked fact and an unlocked manual fact
    manual_char = Character(
        story_id=story.id,
        canonical_name="Alice",
        source="manual",
        locked=True,
        status="active",
        notes="Author's main hero",
    )
    db_session.add(manual_char)
    db_session.flush()

    locked_fact = Fact(
        story_id=story.id,
        character_id=manual_char.id,
        attribute="eye_color",
        value="brown",
        chapter_id=chapter.id,
        source="manual",
        locked=True,
    )
    manual_unlocked_fact = Fact(
        story_id=story.id,
        character_id=manual_char.id,
        attribute="origin",
        value="London",
        chapter_id=chapter.id,
        source="manual",
        locked=False,
    )
    db_session.add_all([locked_fact, manual_unlocked_fact])
    db_session.commit()

    ai_fact_id = ai_fact.id
    locked_fact_id = locked_fact.id
    manual_fact_id = manual_unlocked_fact.id
    manual_char_id = manual_char.id

    # Now run delete_chapter_data on chapter
    delete_chapter_data(db_session, chapter.id)

    # The AI fact should be deleted
    assert db_session.query(Fact).filter(Fact.id == ai_fact_id).first() is None
    # Both manual/locked facts must survive
    assert db_session.query(Fact).filter(Fact.id == locked_fact_id).first() is not None
    assert db_session.query(Fact).filter(Fact.id == manual_fact_id).first() is not None
    # Both characters still exist
    assert db_session.query(Character).filter(Character.id == manual_char_id).first() is not None


def test_merge_characters_and_reanalysis_persistence(db_session: Session) -> None:
    """Merged character keeps all merged names as aliases so future extractions resolve."""
    story = Story(title="Merge Story")
    db_session.add(story)
    db_session.flush()

    # Char 1: John (Target)
    target = Character(story_id=story.id, canonical_name="John Vance", source="manual")
    # Char 2: Johnny (Source to merge)
    source = Character(story_id=story.id, canonical_name="Johnny", source="ai")
    db_session.add_all([target, source])
    db_session.flush()

    fact = Fact(
        story_id=story.id,
        character_id=source.id,
        attribute="hat",
        value="bowler",
        source="ai",
    )
    db_session.add(fact)
    db_session.commit()

    merged = merge_characters(db_session, story.id, [source.id], target.id)
    assert merged is not None
    assert merged.id == target.id

    # Johnny should now be an alias of John Vance
    target_data = get_character_with_facts(db_session, target.id)
    assert "Johnny" in target_data["aliases"]
    assert db_session.query(Character).filter(Character.id == source.id).first() is None

    # Future resolution of "Johnny" must resolve to John Vance
    resolved = resolve_or_create_character("Johnny", story.id, db_session)
    assert resolved.id == target.id
    assert resolved.canonical_name == "John Vance"


def test_ignored_name_prevents_recreation(db_session: Session) -> None:
    """Ignoring a character adds names to IgnoredName and validator/resolver drops them."""
    story = Story(title="Ignore Story")
    db_session.add(story)
    db_session.flush()

    char = Character(story_id=story.id, canonical_name="The Butler", source="ai")
    db_session.add(char)
    db_session.flush()
    char_id = char.id

    # Add alias
    upsert_character(db_session, story.id, "The Butler", aliases=["Jeeves"])

    # Ignore character
    ignored_names = ignore_character(db_session, char_id)
    assert "The Butler" in ignored_names
    assert db_session.query(Character).filter(Character.id == char_id).first() is None

    # Check IgnoredName table
    ignored = {
        r.name.lower()
        for r in db_session.query(IgnoredName).filter(IgnoredName.story_id == story.id).all()
    }
    assert "the butler" in ignored
    assert "jeeves" in ignored

    # Attempting to resolve "The Butler" returns None because it is ignored
    resolved = resolve_or_create_character("The Butler", story.id, db_session)
    assert resolved is None


def test_planned_character_becomes_active_on_mention(db_session: Session) -> None:
    """A planned character with status='planned' becomes status='active' on first appearance."""
    story = Story(title="Planned Story")
    db_session.add(story)
    db_session.flush()

    planned_char = Character(
        story_id=story.id,
        canonical_name="Lord Blackwood",
        status="planned",
        source="manual",
    )
    db_session.add(planned_char)
    db_session.commit()

    # Now resolve an occurrence of "Lord Blackwood"
    matched = resolve_or_create_character("Lord Blackwood", story.id, db_session)
    assert matched.id == planned_char.id
    assert matched.status == "active"


def test_manual_fact_conflict_generates_notes_issue(db_session: Session) -> None:
    """Manual/locked fact vs extracted fact produces 'Text conflicts with your notes'."""
    story = Story(title="Notes Conflict Story")
    db_session.add(story)
    db_session.flush()

    chapter = Chapter(
        story_id=story.id,
        index=9,
        title="Chapter 9",
        text="Maria looked up with bright blue eyes.",
        content_hash="h9",
    )
    db_session.add(chapter)
    db_session.flush()

    char = Character(
        story_id=story.id,
        canonical_name="Maria",
        source="manual",
    )
    db_session.add(char)
    db_session.flush()

    # Manual fact from author notes
    manual_fact = Fact(
        story_id=story.id,
        character_id=char.id,
        attribute="eye_color",
        value="brown",
        source="manual",
        locked=True,
    )
    # Extracted fact from chapter 9
    text_fact = Fact(
        story_id=story.id,
        character_id=char.id,
        attribute="eye_color",
        value="blue",
        chapter_id=chapter.id,
        source="ai",
        quote="Maria looked up with bright blue eyes",
    )
    db_session.add_all([manual_fact, text_fact])
    db_session.commit()

    fake_llm = FakeLLMClient(
        responses=[
            AdjudicationOutput(
                verdict="contradiction",
                explanation="Brown eyes in notes conflict with blue eyes in text.",
                severity="warning",
            )
        ]
    )

    issues = detect_contradictions(story.id, db_session, llm_client=fake_llm)
    assert len(issues) == 1
    issue = issues[0]
    assert issue.message.startswith("Text conflicts with your notes")
    assert "blue" in issue.message
    assert "brown" in issue.message


def test_attribute_rule_can_change_and_ignore(db_session: Session) -> None:
    """AttributeRule 'can_change' ignores cross-chapter differences; 'ignore' skips completely."""
    story = Story(title="Attribute Rules Story")
    db_session.add(story)
    db_session.flush()

    ch1 = Chapter(
        story_id=story.id,
        index=1,
        title="Ch 1",
        text="He wore a red coat.",
        content_hash="h1",
    )
    ch2 = Chapter(
        story_id=story.id,
        index=2,
        title="Ch 2",
        text="He wore a blue coat.",
        content_hash="h2",
    )
    db_session.add_all([ch1, ch2])
    db_session.flush()

    char = Character(story_id=story.id, canonical_name="Sherlock", source="ai")
    db_session.add(char)
    db_session.flush()

    f1 = Fact(
        story_id=story.id,
        character_id=char.id,
        attribute="clothing",
        value="red coat",
        chapter_id=ch1.id,
    )
    f2 = Fact(
        story_id=story.id,
        character_id=char.id,
        attribute="clothing",
        value="blue coat",
        chapter_id=ch2.id,
    )
    f_mood1 = Fact(
        story_id=story.id,
        character_id=char.id,
        attribute="mood",
        value="cheerful",
        chapter_id=ch1.id,
    )
    f_mood2 = Fact(
        story_id=story.id,
        character_id=char.id,
        attribute="mood",
        value="gloomy",
        chapter_id=ch1.id,
    )
    db_session.add_all([f1, f2, f_mood1, f_mood2])

    # Rule 1: clothing -> can_change (should ignore cross-chapter f1 vs f2)
    rule1 = AttributeRule(story_id=story.id, attribute="clothing", mode="can_change")
    # Rule 2: mood -> ignore (should skip mood entirely)
    rule2 = AttributeRule(story_id=story.id, attribute="mood", mode="ignore")
    db_session.add_all([rule1, rule2])
    db_session.commit()

    fake_llm = FakeLLMClient(
        responses=[
            AdjudicationOutput(
                verdict="contradiction",
                explanation="Clothing changed.",
            )
        ]
    )

    issues = detect_contradictions(story.id, db_session, llm_client=fake_llm)
    # Clothing in different chapters was skipped due to 'can_change'.
    # Mood was skipped due to 'ignore'.
    assert len(issues) == 0


def test_story_bible_api_crud_and_merge(client: TestClient) -> None:
    """Test REST API for characters, aliases, facts, merge, and ignore."""
    create_story_resp = client.post("/api/stories", json={"title": "Bible API Test"})
    assert create_story_resp.status_code == 201
    story_id = create_story_resp.json()["id"]

    # 1. Create manual character
    char_payload = {
        "canonical_name": "Katherine",
        "description": "Astronomer and mathematician",
        "aliases": ["Kate", "Kathy"],
        "status": "planned",
        "notes": "Introduced in act 2",
        "color": "#4a90e2",
        "tags": ["protagonist", "scientist"],
        "initial_facts": [
            {"attribute": "profession", "value": "astronomer", "locked": True},
        ],
    }
    resp = client.post(f"/api/stories/{story_id}/characters", json=char_payload)
    assert resp.status_code == 201
    char_data = resp.json()
    char_id = char_data["id"]
    assert char_data["canonical_name"] == "Katherine"
    assert char_data["status"] == "planned"
    assert char_data["source"] == "manual"
    assert len(char_data["aliases"]) == 2
    assert len(char_data["facts"]) == 1
    assert char_data["facts"][0]["locked"] is True

    # 2. Add an alias
    alias_resp = client.post(f"/api/characters/{char_id}/aliases", json={"name": "Prof. Kate"})
    assert alias_resp.status_code == 201
    alias_id = alias_resp.json()["id"]

    # 3. Add a fact
    fact_resp = client.post(
        f"/api/characters/{char_id}/facts",
        json={"attribute": "eye_color", "value": "hazel", "locked": False},
    )
    assert fact_resp.status_code == 201
    fact_id = fact_resp.json()["id"]

    # 4. Patch character
    patch_resp = client.patch(
        f"/api/characters/{char_id}",
        json={"status": "active", "notes": "Updated notes"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "active"
    assert patch_resp.json()["notes"] == "Updated notes"

    # 5. Patch fact
    patch_f_resp = client.patch(f"/api/facts/{fact_id}", json={"locked": True})
    assert patch_f_resp.status_code == 200
    assert patch_f_resp.json()["locked"] is True

    # 6. Delete alias
    del_alias_resp = client.delete(f"/api/aliases/{alias_id}")
    assert del_alias_resp.status_code == 200

    # 7. Create second character and merge
    c2_resp = client.post(
        f"/api/stories/{story_id}/characters",
        json={"canonical_name": "Kate Clone", "description": "Duplicate entry"},
    )
    c2_id = c2_resp.json()["id"]

    merge_resp = client.post(
        f"/api/stories/{story_id}/characters/merge",
        json={"source_ids": [c2_id], "target_id": char_id},
    )
    assert merge_resp.status_code == 200
    merged_data = merge_resp.json()
    assert "Kate Clone" in merged_data["aliases"]

    # 8. Ignore character
    c3_resp = client.post(
        f"/api/stories/{story_id}/characters",
        json={"canonical_name": "Random Passerby"},
    )
    c3_id = c3_resp.json()["id"]
    ignore_resp = client.post(f"/api/characters/{c3_id}/ignore")
    assert ignore_resp.status_code == 200

    # Verify character 3 is gone
    get_c3 = client.get(f"/api/characters/{c3_id}")
    assert get_c3.status_code == 404


def test_attribute_rules_and_settings_api(client: TestClient) -> None:
    """Test AttributeRule and StorySettings API endpoints."""
    create_story_resp = client.post("/api/stories", json={"title": "Settings Test"})
    story_id = create_story_resp.json()["id"]

    # Update and get attribute rules
    rules_payload = [
        {"attribute": "clothing", "mode": "can_change"},
        {"attribute": "eye_color", "mode": "strict"},
        {"attribute": "mood", "mode": "ignore"},
    ]
    put_rules_resp = client.put(f"/api/stories/{story_id}/attribute-rules", json=rules_payload)
    assert put_rules_resp.status_code == 200
    rules_data = put_rules_resp.json()
    assert len(rules_data) == 3
    assert {r["attribute"]: r["mode"] for r in rules_data} == {
        "clothing": "can_change",
        "eye_color": "strict",
        "mood": "ignore",
    }

    get_rules_resp = client.get(f"/api/stories/{story_id}/attribute-rules")
    assert get_rules_resp.status_code == 200
    assert len(get_rules_resp.json()) == 3

    # Update and get settings
    settings_patch = {
        "confidence_threshold": 0.85,
        "grammar_language": "en-GB",
        "disabled_grammar_rules": ["COMMA_RULE"],
    }
    patch_sett_resp = client.patch(f"/api/stories/{story_id}/settings", json=settings_patch)
    assert patch_sett_resp.status_code == 200
    assert patch_sett_resp.json()["confidence_threshold"] == 0.85
    assert patch_sett_resp.json()["grammar_language"] == "en-GB"

    get_sett_resp = client.get(f"/api/stories/{story_id}/settings")
    assert get_sett_resp.status_code == 200
    assert get_sett_resp.json()["confidence_threshold"] == 0.85


def test_export_and_import_roundtrip(client: TestClient) -> None:
    """Test Story Bible export to JSON and Markdown, and import from JSON."""
    create_story_resp = client.post("/api/stories", json={"title": "Export Story"})
    story_id = create_story_resp.json()["id"]

    # Create character and rules
    client.post(
        f"/api/stories/{story_id}/characters",
        json={
            "canonical_name": "Edward Hyde",
            "description": "A sinister counterpart",
            "aliases": ["Hyde"],
            "initial_facts": [{"attribute": "stature", "value": "dwarfish", "locked": True}],
        },
    )
    client.put(
        f"/api/stories/{story_id}/attribute-rules",
        json=[{"attribute": "stature", "mode": "strict"}],
    )

    # 1. Export JSON
    exp_json_resp = client.get(f"/api/stories/{story_id}/export?format=json")
    assert exp_json_resp.status_code == 200
    export_data = exp_json_resp.json()
    assert "characters" in export_data
    assert len(export_data["characters"]) >= 1
    assert export_data["characters"][0]["canonical_name"] == "Edward Hyde"

    # 2. Export Markdown
    exp_md_resp = client.get(f"/api/stories/{story_id}/export?format=md")
    assert exp_md_resp.status_code == 200
    assert "Story Bible: Export Story" in exp_md_resp.text
    assert "Edward Hyde" in exp_md_resp.text

    # 3. Create fresh story and import data into it
    new_story_resp = client.post("/api/stories", json={"title": "Import Target Story"})
    target_story_id = new_story_resp.json()["id"]

    import_resp = client.post(f"/api/stories/{target_story_id}/import", json=export_data)
    assert import_resp.status_code == 200

    # Verify target story has Edward Hyde
    chars_resp = client.get(f"/api/stories/{target_story_id}/characters")
    assert chars_resp.status_code == 200
    names = [c["canonical_name"] for c in chars_resp.json()]
    assert "Edward Hyde" in names
