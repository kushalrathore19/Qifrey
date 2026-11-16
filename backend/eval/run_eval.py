"""Run evaluation pipeline on gold standard chapters and produce reports."""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from eval.baseline import run_baseline_on_gold
from eval.metrics import (
    MetricScore,
    evaluate_aliases,
    evaluate_characters,
    evaluate_contradictions,
    evaluate_facts,
    evaluate_locations,
)
from qifrey.config import get_settings
from qifrey.db.models import Base, Chapter, Fact, Issue, LLMCall, Location, Story
from qifrey.db.session import get_engine, get_session_factory, reset_engine
from qifrey.graph.store import list_characters
from qifrey.insights.contradictions import AdjudicationOutput
from qifrey.insights.summarizer import SummaryOutput
from qifrey.pipeline.llm_client import AnthropicClient, FakeLLMClient, LLMClient
from qifrey.pipeline.runner import analyze_story
from qifrey.pipeline.schemas import (
    CharacterExtraction,
    ExtractionOutput,
    FactExtraction,
    LocationExtraction,
)

BASE_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)

# Anthropic Claude 3.5 Sonnet pricing (USD per 1M tokens)
INPUT_PRICE_PER_M = 3.00
OUTPUT_PRICE_PER_M = 15.00


def _build_fake_responses_from_gold(gold_story: dict[str, Any]) -> list[Any]:
    """Construct mock responses from gold data so tests/offline evaluation runs cleanly."""
    responses: list[Any] = []
    chapters = gold_story.get("chapters", [])

    for ch in chapters:
        c_exts = [
            CharacterExtraction(
                name=c.get("canonical_name", ""),
                aliases=c.get("aliases", []),
                description=c.get("description", "A character"),
                evidence_quote=c.get("canonical_name", ""),
            )
            for c in ch.get("characters", [])
        ]
        l_exts = [
            LocationExtraction(
                name=loc.get("name") if isinstance(loc, dict) else str(loc),
                description="A setting",
            )
            for loc in ch.get("locations", [])
        ]
        f_exts = [
            FactExtraction(
                character=f.get("character", ""),
                attribute=f.get("attribute", ""),
                value=f.get("value", ""),
                evidence_quote=f.get("quote", f.get("value", "")),
                confidence=1.0,
            )
            for f in ch.get("facts", [])
        ]
        responses.append(
            ExtractionOutput(
                characters=c_exts,
                locations=l_exts,
                facts=f_exts,
                relationships=[],
            )
        )

    # Contradiction adjudications
    for _ in gold_story.get("contradictions", []):
        responses.append(
            AdjudicationOutput(
                verdict="contradiction",
                explanation="Values conflict directly with no valid explanation in text.",
            )
        )

    # Chapter summaries and global summary
    for ch in chapters:
        responses.append(SummaryOutput(summary=f"Summary of chapter {ch.get('index', 1)}."))
    responses.append(SummaryOutput(summary="Global summary of the story."))

    return responses


def evaluate_gold_file(
    gold_path: Path,
    llm_client: LLMClient,
) -> dict[str, Any]:
    """Run full evaluation on a single gold standard JSON story."""
    with gold_path.open("r", encoding="utf-8") as f:
        gold_data = json.load(f)

    # Setup isolated database in memory
    os.environ["QIFREY_DB_PATH"] = ":memory:"
    reset_engine()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    factory = get_session_factory()

    story_title = gold_data.get("title", gold_path.stem)

    with factory() as db:
        story = Story(title=story_title)
        db.add(story)
        db.flush()

        for ch in gold_data.get("chapters", []):
            text = ch.get("text", "")
            ch_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            db.add(
                Chapter(
                    story_id=story.id,
                    index=ch.get("index", 1),
                    title=ch.get("title", f"Chapter {ch.get('index', 1)}"),
                    text=text,
                    content_hash=ch_hash,
                )
            )
        db.commit()
        story_id = story.id

    # Run Qifrey analysis pipeline
    analyze_story(story_id, llm_client=llm_client)

    # Extract results from DB
    with factory() as db:
        extracted_chars_db = list_characters(db, story_id)
        extracted_characters = [
            {
                "canonical_name": c.canonical_name,
                "aliases": [a.name for a in c.aliases],
            }
            for c in extracted_chars_db
        ]

        extracted_locs_db = db.query(Location).filter(Location.story_id == story_id).all()
        extracted_locations = [{"name": loc.name} for loc in extracted_locs_db]

        extracted_facts_db = db.query(Fact).filter(Fact.story_id == story_id).all()
        char_map = {c.id: c.canonical_name for c in extracted_chars_db}
        extracted_facts = [
            {
                "character": char_map.get(f.character_id, "Unknown"),
                "attribute": f.attribute,
                "value": f.value,
            }
            for f in extracted_facts_db
        ]

        detected_issues_db = db.query(Issue).filter(Issue.story_id == story_id).all()
        detected_issues = [
            {
                "type": iss.type,
                "message": iss.message,
                "quote": iss.quote,
            }
            for iss in detected_issues_db
        ]

        # Gather LLM calls recorded in DB
        llm_calls_db = db.query(LLMCall).filter(LLMCall.story_id == story_id).all()
        llm_calls = [
            {
                "purpose": call.purpose,
                "model": call.model,
                "input_tokens": call.input_tokens,
                "output_tokens": call.output_tokens,
                "latency_ms": call.latency_ms,
            }
            for call in llm_calls_db
        ]

    # Aggregate gold elements
    gold_chars: list[dict[str, Any]] = []
    seen_gc: set[str] = set()
    gold_locs: list[dict[str, Any]] = []
    seen_gl: set[str] = set()
    gold_facts: list[dict[str, Any]] = []

    for ch in gold_data.get("chapters", []):
        for c in ch.get("characters", []):
            c_name = c.get("canonical_name", "").lower()
            if c_name not in seen_gc:
                seen_gc.add(c_name)
                gold_chars.append(c)
        for loc in ch.get("locations", []):
            l_name = (loc.get("name") if isinstance(loc, dict) else str(loc)).lower()
            if l_name not in seen_gl:
                seen_gl.add(l_name)
                gold_locs.append(loc if isinstance(loc, dict) else {"name": loc})
        for f in ch.get("facts", []):
            gold_facts.append(f)

    gold_contradictions = gold_data.get("contradictions", [])

    # Compute Qifrey metrics
    char_score, gold_to_ext = evaluate_characters(gold_chars, extracted_characters)
    alias_score = evaluate_aliases(gold_chars, extracted_characters, gold_to_ext)
    loc_score = evaluate_locations(gold_locs, extracted_locations)
    fact_score = evaluate_facts(gold_facts, extracted_facts, gold_chars)
    contra_score = evaluate_contradictions(gold_contradictions, detected_issues)

    # Compute Baseline metrics
    baseline_scores = run_baseline_on_gold(gold_data)

    # Cost calculation
    total_input_tokens = sum(c["input_tokens"] for c in llm_calls)
    total_output_tokens = sum(c["output_tokens"] for c in llm_calls)
    total_latency_ms = sum(c["latency_ms"] for c in llm_calls)
    estimated_cost_usd = (total_input_tokens * INPUT_PRICE_PER_M / 1_000_000) + (
        total_output_tokens * OUTPUT_PRICE_PER_M / 1_000_000
    )

    return {
        "story_title": story_title,
        "gold_file": gold_path.name,
        "chapter_count": len(gold_data.get("chapters", [])),
        "metrics": {
            "characters": char_score,
            "aliases": alias_score,
            "locations": loc_score,
            "facts": fact_score,
            "contradictions": contra_score,
        },
        "baseline_metrics": baseline_scores,
        "usage": {
            "total_calls": len(llm_calls),
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "latency_ms": total_latency_ms,
            "estimated_cost_usd": round(estimated_cost_usd, 5),
            "calls": llm_calls,
        },
    }


def write_reports(results: list[dict[str, Any]], out_dir: Path) -> tuple[Path, Path]:
    """Generate timestamped Markdown and CSV reports."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / f"{timestamp}.md"
    csv_path = out_dir / f"{timestamp}.csv"

    # Markdown Report
    with md_path.open("w", encoding="utf-8") as f:
        f.write(f"# Qifrey Evaluation Report ({timestamp})\n\n")

        for res in results:
            f.write(f"## Story: {res['story_title']} (`{res['gold_file']}`)\n\n")
            f.write(f"- **Chapters:** {res['chapter_count']}\n")
            f.write(f"- **Total LLM Calls:** {res['usage']['total_calls']}\n")
            u = res["usage"]
            f.write(
                f"- **Tokens:** {u['input_tokens']} in / {u['output_tokens']} out "
                f"(Total: {u['total_tokens']})\n"
            )
            f.write(f"- **Estimated Cost:** ${u['estimated_cost_usd']:.4f} USD\n")
            f.write(f"- **Total LLM Latency:** {u['latency_ms']} ms\n\n")

            f.write("### Qifrey Extraction & Insights Performance\n\n")
            f.write("| Entity / Task | Precision | Recall | F1 | TP | FP | FN |\n")
            f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n")
            for task, score in res["metrics"].items():
                f.write(
                    f"| {task.capitalize()} | {score.precision:.2%} | {score.recall:.2%} | "
                    f"**{score.f1:.2%}** | {score.tp} | {score.fp} | {score.fn} |\n"
                )
            f.write("\n")

            f.write("### Qifrey vs Naive Baseline\n\n")
            f.write("| Entity | Qifrey F1 | Baseline F1 | Qifrey Recall | Baseline Recall |\n")
            f.write("| :--- | :---: | :---: | :---: | :---: |\n")
            q_char = res["metrics"]["characters"]
            b_char = res["baseline_metrics"].get("characters", MetricScore(0, 0, 0, 0, 0, 0))
            q_loc = res["metrics"]["locations"]
            b_loc = res["baseline_metrics"].get("locations", MetricScore(0, 0, 0, 0, 0, 0))
            f.write(
                f"| Characters | **{q_char.f1:.2%}** | {b_char.f1:.2%} | "
                f"**{q_char.recall:.2%}** | {b_char.recall:.2%} |\n"
            )
            f.write(
                f"| Locations | **{q_loc.f1:.2%}** | {b_loc.f1:.2%} | "
                f"**{q_loc.recall:.2%}** | {b_loc.recall:.2%} |\n\n"
            )

    # CSV Report
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp",
                "story",
                "entity_task",
                "precision",
                "recall",
                "f1",
                "tp",
                "fp",
                "fn",
                "input_tokens",
                "output_tokens",
                "estimated_cost_usd",
            ]
        )
        for res in results:
            for task, score in res["metrics"].items():
                writer.writerow(
                    [
                        timestamp,
                        res["story_title"],
                        task,
                        f"{score.precision:.4f}",
                        f"{score.recall:.4f}",
                        f"{score.f1:.4f}",
                        score.tp,
                        score.fp,
                        score.fn,
                        res["usage"]["input_tokens"],
                        res["usage"]["output_tokens"],
                        res["usage"]["estimated_cost_usd"],
                    ]
                )

    return md_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Qifrey evaluation on gold datasets.")
    parser.add_argument(
        "--gold",
        default="eval/gold",
        help="Directory or specific JSON file with gold data.",
    )
    parser.add_argument(
        "--out",
        default="eval/reports",
        help="Directory to save evaluation reports.",
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Force FakeLLMClient for fast offline evaluation.",
    )
    args = parser.parse_args()

    gold_input = Path(args.gold)
    if not gold_input.is_absolute():
        gold_input = (BASE_DIR / gold_input).resolve()

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = (BASE_DIR / out_dir).resolve()

    # Discover gold JSON files
    gold_files: list[Path] = []
    if gold_input.is_file() and gold_input.suffix == ".json":
        gold_files.append(gold_input)
    elif gold_input.is_dir():
        for p in sorted(gold_input.glob("*.json")):
            if p.name != "template.json":
                gold_files.append(p)

    if not gold_files:
        print(f"No gold JSON files found in {gold_input}")
        sys.exit(1)

    settings = get_settings()
    has_api_key = bool(settings.anthropic_api_key)

    results: list[dict[str, Any]] = []

    for g_path in gold_files:
        print(f"\nEvaluating: {g_path.name}...")

        # Setup LLM client
        if args.fake or not has_api_key:
            if not args.fake:
                print("Notice: No ANTHROPIC_API_KEY found. Using FakeLLMClient for offline eval.")
            with g_path.open("r", encoding="utf-8") as f:
                gold_content = json.load(f)
            fake_responses = _build_fake_responses_from_gold(gold_content)
            client: LLMClient = FakeLLMClient(responses=fake_responses)
        else:
            client = AnthropicClient(
                api_key=settings.anthropic_api_key,
                model=settings.llm_model,
            )

        res = evaluate_gold_file(g_path, client)
        results.append(res)

        print(f"  Characters F1:    {res['metrics']['characters'].f1:.2%}")
        print(f"  Aliases F1:       {res['metrics']['aliases'].f1:.2%}")
        print(f"  Locations F1:     {res['metrics']['locations'].f1:.2%}")
        print(f"  Facts F1:         {res['metrics']['facts'].f1:.2%}")
        print(f"  Contradictions F1:{res['metrics']['contradictions'].f1:.2%}")
        print(
            f"  Tokens: {res['usage']['total_tokens']} | "
            f"Est Cost: ${res['usage']['estimated_cost_usd']:.4f}"
        )

    md_path, csv_path = write_reports(results, out_dir)
    print("\nEvaluation complete!")
    print(f"  Markdown report: {md_path}")
    print(f"  CSV report:      {csv_path}")


if __name__ == "__main__":
    main()
