# Qifrey — Master of Ink and Brush

Qifrey reads a fiction manuscript and builds a living map of characters, facts,
and contradictions so authors never lose track of their own world.

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Copy and fill in your keys
cp .env.example .env

# Run the server
uvicorn qifrey.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # → http://localhost:5173
```

### Run Tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm test
```

### How to Evaluate

Qifrey includes an evaluation harness in `backend/eval/` to evaluate extraction accuracy (precision, recall, F1) across characters, aliases, locations, and facts, benchmark against naive baselines, and test contradiction detection on planted errors:

```bash
cd backend

# Run evaluation on gold standard stories (outputs reports to eval/reports/)
python -m eval.run_eval --gold eval/gold --out eval/reports

# Force offline/fake LLM evaluation (even if an API key is set)
python -m eval.run_eval --gold eval/gold --out eval/reports --fake

# Inject contradictions and legitimate changes into a story to test detector robustness
python -m eval.inject_contradictions --input eval/gold/example_story.json --out eval/gold/modified.json --key eval/gold/answer_key.json --n 1
```

Reports are written to `eval/reports/<timestamp>.md` and `.csv`, detailing precision/recall/F1, baseline comparisons, token counts, and estimated LLM costs.

## Project Structure

```
backend/
  src/qifrey/         # FastAPI application
    api/               # Route handlers
    db/                # SQLAlchemy models & session
    ingestion/         # .txt parsing
    pipeline/          # LLM extraction (future)
    graph/             # Story graph logic (future)
    insights/          # Contradiction detection (future)
    grammar/           # LanguageTool integration (future)
  tests/               # pytest test suite
frontend/
  src/                 # React + Vite + TypeScript
docs/
  PROJECT_BRIEF.md     # Product specification
```

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.x, Pydantic v2, SQLite
- **Frontend:** React, Vite, TypeScript, Tailwind CSS, React Router, TanStack Query
- **LLM:** Provider interface (Anthropic first)
- **Grammar:** LanguageTool via language_tool_python
