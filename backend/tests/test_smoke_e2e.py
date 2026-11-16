"""End-to-end smoke test: upload sample, analyze, verify graph, issues, and write mode."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from qifrey.pipeline.llm_client import FakeLLMClient
from qifrey.pipeline.runner import analyze_story
from qifrey.pipeline.schemas import (
    CharacterExtraction,
    ExtractionOutput,
    FactExtraction,
    LocationExtraction,
)


def test_full_e2e_smoke_run(client: TestClient) -> None:
    # 1. Locate public domain sample
    sample_path = (
        Path(__file__).resolve().parent.parent.parent / "data/samples/jekyll_and_hyde_sample.txt"
    )
    assert sample_path.exists(), f"Sample text not found at {sample_path}"

    with sample_path.open("rb") as f:
        file_bytes = f.read()

    # 2. Upload story
    upload_resp = client.post(
        "/api/stories/upload",
        files={"file": ("jekyll_and_hyde.txt", file_bytes, "text/plain")},
        data={"title": "Dr. Jekyll and Mr. Hyde"},
    )
    assert upload_resp.status_code == 201
    story = upload_resp.json()
    story_id = story["id"]
    assert story["title"] == "Dr. Jekyll and Mr. Hyde"

    # 3. Check parsed chapters
    chapters_resp = client.get(f"/api/stories/{story_id}/chapters")
    assert chapters_resp.status_code == 200
    chapters = chapters_resp.json()
    assert len(chapters) == 2
    assert "Story of the Door" in chapters[0]["title"]
    assert "Search for Mr. Hyde" in chapters[1]["title"]

    # 4. Run Analysis with mocked LLM responses
    fake_llm = FakeLLMClient(
        responses=[
            # Chapter 1 extraction
            ExtractionOutput(
                characters=[
                    CharacterExtraction(
                        name="Mr. Utterson",
                        aliases=["Utterson"],
                        description="A lawyer of rugged countenance.",
                        evidence_quote="Mr. Utterson the lawyer",
                    )
                ],
                locations=[LocationExtraction(name="London", description="Busy quarter")],
                facts=[
                    FactExtraction(
                        character="Mr. Utterson",
                        attribute="occupation",
                        value="lawyer",
                        evidence_quote="Mr. Utterson the lawyer",
                        confidence=1.0,
                    )
                ],
                relationships=[],
            ),
            # Chapter 2 extraction
            ExtractionOutput(
                characters=[
                    CharacterExtraction(
                        name="Edward Hyde",
                        aliases=["Mr. Hyde"],
                        description="Friend and benefactor of Henry Jekyll.",
                        evidence_quote="friend and benefactor Edward Hyde",
                    )
                ],
                locations=[],
                facts=[],
                relationships=[],
            ),
        ]
    )

    analyze_story(story_id, llm_client=fake_llm)

    # 5. Verify story profile and characters
    chars_resp = client.get(f"/api/stories/{story_id}/characters")
    assert chars_resp.status_code == 200
    chars = chars_resp.json()
    assert len(chars) >= 2
    canonical_names = {c["canonical_name"] for c in chars}
    assert "Mr. Utterson" in canonical_names
    assert "Edward Hyde" in canonical_names

    # 6. Verify Character Detail
    utterson = next(c for c in chars if c["canonical_name"] == "Mr. Utterson")
    detail_resp = client.get(f"/api/characters/{utterson['id']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert len(detail["facts"]) == 1
    assert detail["facts"][0]["attribute"] == "occupation"
    assert detail["facts"][0]["value"] == "lawyer"

    # 7. Verify Issues API
    issues_resp = client.get(f"/api/stories/{story_id}/issues")
    assert issues_resp.status_code == 200

    # 8. Test Write Mode: Add, Update, and Grammar check
    new_ch_resp = client.post(
        f"/api/stories/{story_id}/chapters",
        json={"title": "Dr. Jekyll Was Quite at Ease", "text": "A fortnight later..."},
    )
    assert new_ch_resp.status_code == 201
    new_ch_id = new_ch_resp.json()["id"]

    grammar_resp = client.post(
        f"/api/chapters/{new_ch_id}/grammar",
        json={"text": "This is an sample sentence."},
    )
    assert grammar_resp.status_code == 200
    assert isinstance(grammar_resp.json(), list)

    update_resp = client.put(
        f"/api/chapters/{new_ch_id}",
        json={"title": "Revised Chapter 3", "text": "A fortnight later, at a friendly dinner..."},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "Revised Chapter 3"
