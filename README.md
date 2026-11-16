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
