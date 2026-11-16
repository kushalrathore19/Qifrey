- Read docs/PROJECT_BRIEF.md before every task. Do not add features outside the brief.
- Never commit secrets, .env files, *.db files, or manuscripts that are not public domain.
- Type hints everywhere; format/lint with ruff (backend) and eslint/prettier (frontend).
- Every module gets tests. LLM calls must be mockable; tests never call a real API.
- Small, focused commits using conventional messages (feat:, fix:, docs:, test:, chore:).
- After each phase: run the tests, push to origin main, and create a git tag phase-N.
- If something is ambiguous or blocked (auth, missing tool), stop and tell me. Do not
  invent workarounds or fake data.
- End every phase with: what was built, how to run it, and what is NOT yet verified.
