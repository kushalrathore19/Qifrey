# Contributing to Qifrey

Thank you for your interest in contributing to Qifrey!

## Working Rules

1. **Keep it within the brief**: Consult `docs/PROJECT_BRIEF.md` before adding new features.
2. **Privacy & Security**: Never commit secrets, API keys, `.env` files, `.db` SQLite files, or manuscripts that are not public domain.
3. **Type hints everywhere**: All Python code must include explicit type hints. Frontend code is strictly typed in TypeScript.
4. **Code Quality**:
   - Backend: format and check with `ruff` (`ruff check .`, `ruff format .`).
   - Frontend: check and build with `oxlint` and `tsc` (`npm run lint`, `npm run build`).
5. **Testing**: Every module must have tests. All LLM calls must be mockable with `FakeLLMClient`; tests must never call a real API or incur paid costs.
6. **Commit Style**: Use small, focused commits with Conventional Commits syntax:
   `feat:`, `fix:`, `docs:`, `test:`, `chore:`.

## Development Workflow

```bash
# 1. Backend setup
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest

# 2. Frontend setup
cd ../frontend
npm install
npm run lint
npm run build

# 3. Running evaluation
cd ../backend
python -m eval.run_eval --gold eval/gold --out eval/reports
```
