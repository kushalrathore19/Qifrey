Problem: Authors of long fiction lose track of their own world (eye colors, timelines,
who is who under which alias). Qifrey reads a manuscript and builds the memory for them.

Product (MVP):
- Library page: list of stories; buttons "Upload .txt" and "New story".
- Story profile page: AI summary + list of characters in the main panel; right sidebar
  with two tabs: "Contradictions" and "Grammar".
- Character detail drawer: aliases, attributes with chapter references.
- Editor page: write a story chapter by chapter, auto-save, "Analyze" button.
- Only .txt input is supported. No scanner/NER pre-step.

Pipeline: Story library (SQLite) -> Context builder -> LLM extraction -> Validator ->
Story graph (SQLite tables) -> Insights (contradictions, summary). A separate branch runs
grammar checks (LanguageTool). Author corrections (dismiss / accept / mark intentional)
are stored and respected in future runs.

Design principles:
1. Graph-first: the graph is the memory, not the raw text.
2. LLM extracts, algorithms validate, the author has the final say.
3. Incremental: each chapter has a content hash; only changed chapters are re-analyzed.
4. Human-correctable: dismissed/intentional issues must not reappear.
5. Privacy-aware: no training on manuscripts, API key only via env, local DB.

Tech stack:
- Backend: Python 3.11, FastAPI, SQLAlchemy 2.x, Pydantic v2, SQLite, pytest, ruff.
- LLM: provider interface with an Anthropic implementation first; model name and key from
  env (QIFREY_LLM_PROVIDER, QIFREY_LLM_MODEL, ANTHROPIC_API_KEY). Easy to add others later.
- Grammar: language_tool_python (LanguageTool).
- Frontend: React + Vite + TypeScript, React Router, TanStack Query, Tailwind CSS.

Data model (SQLAlchemy):
Story(id, title, summary, created_at, updated_at)
Chapter(id, story_id, index, title, text, content_hash, analyzed_hash)
Character(id, story_id, canonical_name, description)
Alias(id, character_id, name)
Location(id, story_id, name, description)
Fact(id, story_id, character_id, attribute, value, chapter_id, quote, confidence)
Relationship(id, story_id, source_character_id, target_character_id, type, chapter_id, quote)
Issue(id, story_id, type[contradiction|grammar], chapter_id, severity, message, quote,
      span_start, span_end, suggestions_json, related_fact_ids_json,
      status[open|dismissed|accepted|intentional], created_at)
LLMCall(id, story_id, purpose, model, prompt_hash, input_tokens, output_tokens,
        latency_ms, created_at)

API (all under /api):
POST /stories/upload (multipart .txt, optional title) | POST /stories (blank, title)
GET /stories | GET /stories/{id} | DELETE /stories/{id}
GET /stories/{id}/chapters | POST /stories/{id}/chapters
GET/PUT/DELETE /chapters/{id}
POST /stories/{id}/analyze | GET /stories/{id}/analysis-status
GET /stories/{id}/characters | GET /characters/{id}
GET /stories/{id}/issues?type=contradiction|grammar&status=open
PATCH /issues/{id} (status change)
