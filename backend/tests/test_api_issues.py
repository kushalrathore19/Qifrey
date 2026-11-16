"""Tests for issues API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from qifrey.db.models import Chapter, Issue, Story
from qifrey.db.session import get_engine


def test_list_and_patch_issues(client: TestClient) -> None:
    # 1. Create a story and issues in DB
    with Session(get_engine()) as db:
        story = Story(title="Issues Story")
        db.add(story)
        db.flush()

        ch = Chapter(
            story_id=story.id,
            index=1,
            title="Ch 1",
            text="Text",
            content_hash="h1",
        )
        db.add(ch)
        db.flush()

        i1 = Issue(
            story_id=story.id,
            chapter_id=ch.id,
            type="contradiction",
            severity="warning",
            message="Contradiction in eye_color",
            quote="blue eyes vs green eyes",
            status="open",
        )
        i2 = Issue(
            story_id=story.id,
            chapter_id=ch.id,
            type="grammar",
            severity="warning",
            message="Possible spelling error",
            quote="bad word",
            status="open",
        )
        db.add_all([i1, i2])
        db.commit()

        story_id = story.id
        i1_id = i1.id
        i2_id = i2.id

    # 2. List all issues for story
    resp = client.get(f"/api/stories/{story_id}/issues")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # 3. Filter by type=contradiction
    resp_contra = client.get(f"/api/stories/{story_id}/issues?type=contradiction")
    assert resp_contra.status_code == 200
    assert len(resp_contra.json()) == 1
    assert resp_contra.json()[0]["type"] == "contradiction"

    # 4. Filter by type=grammar
    resp_gram = client.get(f"/api/stories/{story_id}/issues?type=grammar")
    assert resp_gram.status_code == 200
    assert len(resp_gram.json()) == 1
    assert resp_gram.json()[0]["type"] == "grammar"

    # 5. Patch issue status to "dismissed"
    patch_resp = client.patch(f"/api/issues/{i1_id}", json={"status": "dismissed"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "dismissed"

    # 6. Filter by status=open
    resp_open = client.get(f"/api/stories/{story_id}/issues?status=open")
    assert resp_open.status_code == 200
    assert len(resp_open.json()) == 1
    assert resp_open.json()[0]["id"] == i2_id

    # 7. Filter by status=dismissed
    resp_dismissed = client.get(f"/api/stories/{story_id}/issues?status=dismissed")
    assert resp_dismissed.status_code == 200
    assert len(resp_dismissed.json()) == 1
    assert resp_dismissed.json()[0]["id"] == i1_id

    # 8. Patch nonexistent issue returns 404
    resp_404 = client.patch("/api/issues/999999", json={"status": "accepted"})
    assert resp_404.status_code == 404
