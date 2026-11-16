"""Tests for story and chapter API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

SAMPLE_TXT = """Chapter 1: The Start

This is the beginning of the story. Our hero sets out on a journey.

Chapter 2: The Middle

The adventure continues with many twists and turns along the way.

Chapter 3: The End

Everything wraps up nicely and the hero returns home.
"""


class TestHealth:
    def test_health(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestUploadStory:
    def test_upload_txt(self, client: TestClient) -> None:
        resp = client.post(
            "/api/stories/upload",
            files={"file": ("test_story.txt", SAMPLE_TXT.encode(), "text/plain")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "test_story"
        assert data["id"] is not None

    def test_upload_with_title(self, client: TestClient) -> None:
        resp = client.post(
            "/api/stories/upload",
            files={"file": ("story.txt", SAMPLE_TXT.encode(), "text/plain")},
            data={"title": "My Great Novel"},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "My Great Novel"

    def test_upload_non_txt_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/api/stories/upload",
            files={"file": ("story.pdf", b"not a txt", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "txt" in resp.json()["detail"].lower()

    def test_upload_too_large(self, client: TestClient) -> None:
        big = b"x" * (5 * 1024 * 1024 + 1)
        resp = client.post(
            "/api/stories/upload",
            files={"file": ("big.txt", big, "text/plain")},
        )
        assert resp.status_code == 400
        assert "5 MB" in resp.json()["detail"]

    def test_upload_creates_chapters(self, client: TestClient) -> None:
        resp = client.post(
            "/api/stories/upload",
            files={"file": ("story.txt", SAMPLE_TXT.encode(), "text/plain")},
        )
        story_id = resp.json()["id"]
        ch_resp = client.get(f"/api/stories/{story_id}/chapters")
        assert ch_resp.status_code == 200
        chapters = ch_resp.json()
        assert len(chapters) == 3
        assert chapters[0]["index"] == 1
        assert chapters[2]["index"] == 3


class TestCreateBlankStory:
    def test_create_blank(self, client: TestClient) -> None:
        resp = client.post("/api/stories", json={"title": "New Story"})
        assert resp.status_code == 201
        assert resp.json()["title"] == "New Story"

    def test_create_default_title(self, client: TestClient) -> None:
        resp = client.post("/api/stories", json={})
        assert resp.status_code == 201
        assert resp.json()["title"] == "Untitled"


class TestListGetDeleteStories:
    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/stories")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_stories(self, client: TestClient) -> None:
        client.post("/api/stories", json={"title": "Story A"})
        client.post("/api/stories", json={"title": "Story B"})
        resp = client.get("/api/stories")
        assert len(resp.json()) == 2

    def test_get_story(self, client: TestClient) -> None:
        create_resp = client.post("/api/stories", json={"title": "My Story"})
        story_id = create_resp.json()["id"]
        resp = client.get(f"/api/stories/{story_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "My Story"

    def test_get_nonexistent(self, client: TestClient) -> None:
        resp = client.get("/api/stories/9999")
        assert resp.status_code == 404

    def test_delete_story(self, client: TestClient) -> None:
        create_resp = client.post("/api/stories", json={"title": "To Delete"})
        story_id = create_resp.json()["id"]
        del_resp = client.delete(f"/api/stories/{story_id}")
        assert del_resp.status_code == 200
        assert client.get(f"/api/stories/{story_id}").status_code == 404

    def test_delete_nonexistent(self, client: TestClient) -> None:
        resp = client.delete("/api/stories/9999")
        assert resp.status_code == 404


class TestChapters:
    def test_list_chapters_nonexistent_story(self, client: TestClient) -> None:
        resp = client.get("/api/stories/9999/chapters")
        assert resp.status_code == 404

    def test_get_chapter(self, client: TestClient) -> None:
        upload_resp = client.post(
            "/api/stories/upload",
            files={"file": ("story.txt", SAMPLE_TXT.encode(), "text/plain")},
        )
        story_id = upload_resp.json()["id"]
        chapters = client.get(f"/api/stories/{story_id}/chapters").json()
        ch_id = chapters[0]["id"]
        resp = client.get(f"/api/chapters/{ch_id}")
        assert resp.status_code == 200
        assert "text" in resp.json()
        assert resp.json()["index"] == 1

    def test_get_nonexistent_chapter(self, client: TestClient) -> None:
        resp = client.get("/api/chapters/9999")
        assert resp.status_code == 404
