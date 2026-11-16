"""Tests for Phase 5 write mode: chapter CRUD, grammar endpoint, and incremental re-analysis."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from qifrey.db.models import Chapter, Fact, Issue, LLMCall, Story
from qifrey.db.session import get_engine
from qifrey.insights.contradictions import AdjudicationOutput
from qifrey.insights.summarizer import SummaryOutput
from qifrey.pipeline.llm_client import FakeLLMClient
from qifrey.pipeline.runner import analyze_story
from qifrey.pipeline.schemas import (
    CharacterExtraction,
    ExtractionOutput,
    FactExtraction,
)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TestChapterCRUD:
    def test_create_chapter(self, client: TestClient) -> None:
        create_resp = client.post("/api/stories", json={"title": "Write Mode Story"})
        assert create_resp.status_code == 201
        story_id = create_resp.json()["id"]

        # Create chapter 1
        resp1 = client.post(
            f"/api/stories/{story_id}/chapters",
            json={"title": "Prologue", "text": "Once upon a time..."},
        )
        assert resp1.status_code == 201
        data1 = resp1.json()
        assert data1["title"] == "Prologue"
        assert data1["index"] == 1
        assert data1["content_hash"] == _hash("Once upon a time...")

        # Create chapter 2
        resp2 = client.post(
            f"/api/stories/{story_id}/chapters",
            json={"title": "Act I", "text": "The adventure starts."},
        )
        assert resp2.status_code == 201
        data2 = resp2.json()
        assert data2["title"] == "Act I"
        assert data2["index"] == 2

    def test_update_chapter_text_recomputes_hash(self, client: TestClient) -> None:
        create_resp = client.post("/api/stories", json={"title": "Editable Story"})
        story_id = create_resp.json()["id"]

        ch_resp = client.post(
            f"/api/stories/{story_id}/chapters",
            json={"title": "Chapter 1", "text": "Draft version."},
        )
        chap_id = ch_resp.json()["id"]
        old_hash = ch_resp.json()["content_hash"]

        update_resp = client.put(
            f"/api/chapters/{chap_id}",
            json={"title": "Chapter 1 (Revised)", "text": "Polished text."},
        )
        assert update_resp.status_code == 200
        up_data = update_resp.json()
        assert up_data["title"] == "Chapter 1 (Revised)"
        assert up_data["content_hash"] == _hash("Polished text.")
        assert up_data["content_hash"] != old_hash

    def test_delete_chapter_cleans_graph_and_issues(self, client: TestClient) -> None:
        with Session(get_engine()) as db:
            story = Story(title="Temp Story")
            db.add(story)
            db.flush()

            chap = Chapter(
                story_id=story.id,
                index=1,
                title="Chapter 1",
                text="Text",
                content_hash=_hash("Text"),
            )
            db.add(chap)
            db.flush()

            # Add a fact and an issue referencing this chapter
            fact = Fact(
                story_id=story.id,
                character_id=999,
                attribute="eye_color",
                value="blue",
                chapter_id=chap.id,
            )
            db.add(fact)

            issue = Issue(
                story_id=story.id,
                type="grammar",
                chapter_id=chap.id,
                message="Sample grammar issue",
            )
            db.add(issue)
            db.commit()
            chap_id = chap.id

        # Delete chapter via endpoint
        del_resp = client.delete(f"/api/chapters/{chap_id}")
        assert del_resp.status_code == 200

        with Session(get_engine()) as db:
            assert db.query(Chapter).filter(Chapter.id == chap_id).first() is None
            assert db.query(Fact).filter(Fact.chapter_id == chap_id).count() == 0
            assert db.query(Issue).filter(Issue.chapter_id == chap_id).count() == 0


class TestGrammarEndpoint:
    def test_fast_grammar_check_no_llm(self, client: TestClient) -> None:
        create_resp = client.post("/api/stories", json={"title": "Grammar Story"})
        story_id = create_resp.json()["id"]

        ch_resp = client.post(
            f"/api/stories/{story_id}/chapters",
            json={"title": "Chapter 1", "text": "This is a clean sentence."},
        )
        chap_id = ch_resp.json()["id"]

        # Call grammar check endpoint
        resp = client.post(
            f"/api/chapters/{chap_id}/grammar",
            json={"text": "This are an bad sentence."},
        )
        assert resp.status_code == 200
        # Returns GrammarIssueOut list (empty if LanguageTool unavailable, must not crash)
        assert isinstance(resp.json(), list)


class TestIncrementalAnalysisAndStaleFacts:
    def test_edit_chapter_leaves_other_chapters_untouched(self, client: Any) -> None:
        """Editing chapter 2 and re-analyzing must analyze only ch 2 and keep ch 1 untouched."""
        with Session(get_engine()) as db:
            story = Story(title="Incremental Story")
            db.add(story)
            db.flush()

            ch1_text = "Qifrey was a calm teacher with bright green eyes."
            ch1 = Chapter(
                story_id=story.id,
                index=1,
                title="Chapter 1",
                text=ch1_text,
                content_hash=_hash(ch1_text),
                analyzed_hash=None,
            )
            db.add(ch1)

            ch2_text = "Qifrey looked into the mirror, admiring his deep blue eyes."
            ch2 = Chapter(
                story_id=story.id,
                index=2,
                title="Chapter 2",
                text=ch2_text,
                content_hash=_hash(ch2_text),
                analyzed_hash=None,
            )
            db.add(ch2)
            db.commit()
            story_id = story.id
            ch1_id = ch1.id
            ch2_id = ch2.id

        # Pass 1: Extraction for ch1 (green eyes) and ch2 (blue eyes) + contradiction adjudication
        pass1_llm = FakeLLMClient(
            responses=[
                # Ch 1 extraction
                ExtractionOutput(
                    characters=[CharacterExtraction(name="Qifrey", description="Teacher")],
                    facts=[
                        FactExtraction(
                            character="Qifrey",
                            attribute="eye_color",
                            value="green",
                            evidence_quote="bright green eyes",
                            confidence=1.0,
                        )
                    ],
                ),
                # Ch 2 extraction
                ExtractionOutput(
                    characters=[CharacterExtraction(name="Qifrey", description="Teacher")],
                    facts=[
                        FactExtraction(
                            character="Qifrey",
                            attribute="eye_color",
                            value="blue",
                            evidence_quote="deep blue eyes",
                            confidence=1.0,
                        )
                    ],
                ),
                # Contradiction adjudication
                AdjudicationOutput(
                    verdict="contradiction",
                    explanation="Eyes cannot be simultaneously green and blue.",
                ),
                # Summary for ch1
                SummaryOutput(summary="Qifrey has green eyes."),
                # Summary for ch2
                SummaryOutput(summary="Qifrey looks in mirror."),
                # Global story summary
                SummaryOutput(summary="A story about Qifrey."),
            ]
        )

        analyze_story(story_id, llm_client=pass1_llm)

        # Verify Pass 1 results
        with Session(get_engine()) as db:
            c1 = db.query(Chapter).filter(Chapter.id == ch1_id).first()
            c2 = db.query(Chapter).filter(Chapter.id == ch2_id).first()
            assert c1 is not None and c1.analyzed_hash == _hash(ch1_text)
            assert c2 is not None and c2.analyzed_hash == _hash(ch2_text)

            # Facts should have green (ch1) and blue (ch2)
            facts = db.query(Fact).filter(Fact.story_id == story_id).all()
            values = {f.value for f in facts}
            assert "green" in values
            assert "blue" in values

            # Contradiction issue created
            issues = (
                db.query(Issue)
                .filter(Issue.story_id == story_id, Issue.type == "contradiction")
                .all()
            )
            assert len(issues) == 1

            # Count extraction LLM calls in pass 1
            calls_pass1 = (
                db.query(LLMCall)
                .filter(LLMCall.story_id == story_id, LLMCall.purpose.like("extraction%"))
                .count()
            )
            assert calls_pass1 == 2

        # Now edit Chapter 2: remove blue eyes, Qifrey now holds a silver wand
        new_ch2_text = "Qifrey walked silently, holding a silver wand in his left hand."
        with Session(get_engine()) as db:
            c2 = db.query(Chapter).filter(Chapter.id == ch2_id).first()
            assert c2 is not None
            c2.text = new_ch2_text
            c2.content_hash = _hash(new_ch2_text)
            db.commit()

        # Pass 2: only Chapter 2 should be extracted!
        pass2_llm = FakeLLMClient(
            responses=[
                # Ch 2 extraction (wand, no blue eyes)
                ExtractionOutput(
                    characters=[CharacterExtraction(name="Qifrey", description="Teacher")],
                    facts=[
                        FactExtraction(
                            character="Qifrey",
                            attribute="wand_color",
                            value="silver",
                            evidence_quote="silver wand",
                            confidence=1.0,
                        )
                    ],
                ),
                # Ch 2 summary
                SummaryOutput(summary="Qifrey holds a silver wand."),
                # Global story summary
                SummaryOutput(summary="Updated story summary."),
            ]
        )

        analyze_story(story_id, llm_client=pass2_llm)

        # Verify Pass 2 results
        with Session(get_engine()) as db:
            c1 = db.query(Chapter).filter(Chapter.id == ch1_id).first()
            c2 = db.query(Chapter).filter(Chapter.id == ch2_id).first()
            assert c1 is not None and c1.analyzed_hash == _hash(ch1_text)
            assert c2 is not None and c2.analyzed_hash == _hash(new_ch2_text)

            # Chapter 1 fact (green) remains, Chapter 2 stale fact (blue) removed
            ch1_facts = db.query(Fact).filter(Fact.chapter_id == ch1_id).all()
            assert len(ch1_facts) == 1
            assert ch1_facts[0].value == "green"

            ch2_facts = db.query(Fact).filter(Fact.chapter_id == ch2_id).all()
            assert len(ch2_facts) == 1
            assert ch2_facts[0].attribute == "other:wand_color"
            assert ch2_facts[0].value == "silver"

            # Extraction calls should have increased by only 1 (only Ch 2 was extracted)
            calls_pass2 = (
                db.query(LLMCall)
                .filter(LLMCall.story_id == story_id, LLMCall.purpose.like("extraction%"))
                .count()
            )
            assert calls_pass2 == 3  # 2 in pass 1 + 1 in pass 2 (Chapter 1 was skipped)
