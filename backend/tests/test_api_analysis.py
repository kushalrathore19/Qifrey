"""Tests for story analysis API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from qifrey.pipeline.llm_client import FakeLLMClient, set_llm_client
from qifrey.pipeline.schemas import (
    CharacterExtraction,
    ExtractionOutput,
    FactExtraction,
    RelationshipExtraction,
)

SAMPLE_TXT = """Chapter 1: The Detective

Inspector John Vance adjusted his tweed coat.
He was forty-two years old and known for his keen mind.
His trusted assistant, Dr. Clark, stood beside him in London.
"""


def test_analyze_and_query_characters(client: TestClient) -> None:
    # 1. Upload story
    upload_resp = client.post(
        "/api/stories/upload",
        files={"file": ("case.txt", SAMPLE_TXT.encode(), "text/plain")},
    )
    assert upload_resp.status_code == 201
    story_id = upload_resp.json()["id"]

    # 2. Check initial analysis status
    status_resp = client.get(f"/api/stories/{story_id}/analysis-status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] in ("idle", "completed")

    # 3. Setup fake LLM responses
    fake_llm = FakeLLMClient(
        responses=[
            ExtractionOutput(
                characters=[
                    CharacterExtraction(name="John Vance", description="Police inspector"),
                    CharacterExtraction(name="Dr. Clark", description="Medical assistant"),
                ],
                facts=[
                    FactExtraction(
                        character="John Vance",
                        attribute="age",
                        value="42",
                        evidence_quote="forty-two years old",
                    ),
                    FactExtraction(
                        character="John Vance",
                        attribute="clothing",
                        value="tweed coat",
                        evidence_quote="adjusted his tweed coat",
                    ),
                ],
                relationships=[
                    RelationshipExtraction(
                        a="John Vance",
                        b="Dr. Clark",
                        type="assistant",
                        evidence_quote="His trusted assistant, Dr. Clark",
                    )
                ],
            )
        ]
    )
    set_llm_client(fake_llm)

    # 4. Trigger analysis
    analyze_resp = client.post(f"/api/stories/{story_id}/analyze")
    assert analyze_resp.status_code == 200
    assert "scheduled" in analyze_resp.json()["detail"].lower()

    # In TestClient, BackgroundTasks run synchronously before response returns
    # Check status
    post_status = client.get(f"/api/stories/{story_id}/analysis-status")
    assert post_status.status_code == 200
    assert post_status.json()["status"] == "completed"

    # 5. Query characters for story
    chars_resp = client.get(f"/api/stories/{story_id}/characters")
    assert chars_resp.status_code == 200
    characters = chars_resp.json()
    assert len(characters) >= 2
    names = [c["canonical_name"] for c in characters]
    assert "John Vance" in names
    assert "Dr. Clark" in names

    vance = next(c for c in characters if c["canonical_name"] == "John Vance")
    assert vance["fact_count"] >= 2

    # 6. Query character detail
    vance_id = vance["id"]
    detail_resp = client.get(f"/api/characters/{vance_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["canonical_name"] == "John Vance"
    assert len(detail["facts"]) >= 2
    attributes = {f["attribute"] for f in detail["facts"]}
    assert "age" in attributes
    assert "clothing" in attributes
    assert len(detail["relationships"]) >= 1

    # Cleanup
    set_llm_client(None)


def test_character_detail_not_found(client: TestClient) -> None:
    resp = client.get("/api/characters/999999")
    assert resp.status_code == 404
