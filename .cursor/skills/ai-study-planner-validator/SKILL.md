---
name: ai-study-planner-validator
description: >-
  Runs a repeatable pre-demo and pre-submission validation for the AI Study
  Planner (ai-study-planner) repository. Use when the user asks to validate the
  project, run a compliance check, prepare for demo/submission, audit secrets
  safety, verify FastAPI health, integrations config, or automated tests —
  without exposing secrets or sending Telegram messages.
---

# AI Study Planner Validator

Project-local validation skill for **AI Calendar Study Assistant** (`ai-study-planner`).

## When to use

- Pre-demo checklist
- Pre-submission compliance audit
- After major planner/backend changes
- When the user says “validate the project” or “run the study planner validator”

## Hard rules (never violate)

- Never print real tokens, API keys, OAuth client secrets, or `.env` values
- Never commit `.env`, `secrets/`, `token.json`, or credential JSON files
- Never modify production Supabase data
- Never reset the database
- Never send Telegram messages unless the user explicitly requests it
- Never start a new Google OAuth flow unless the user explicitly requests it
- Do not change scheduling engine logic while only validating

## Procedure

Run every step. Record Pass / Fail / Skip with a short reason. Prefer safe probes (file presence, boolean status, HTTP health) over dumping configuration values.

### 1. Secrets safety

1. Confirm `.env` is listed in `.gitignore`.
2. Confirm OAuth credential/token patterns are ignored (`secrets/*.json`, `token.json`, `*credentials*.json`, `local_tokens/`).
3. Run a tracked-file scan for likely secrets (e.g. `git ls-files` + search for `BEGIN PRIVATE KEY`, `client_secret`, long `ya29.` tokens). Report only whether matches were found — never echo secret contents.
4. Confirm `secrets/` is untracked if present.

### 2. Backend import and health

From `backend/`:

1. `python -c "from app.main import app; print('import_ok')"`
2. If a server is already running (or start briefly with uvicorn when safe):
   - `GET /health` → expect healthy JSON
   - `GET /health/supabase` → report configured/reachable status without printing keys

If the server cannot be started in this environment, mark health checks **Skip** and note how to run them manually.

### 3. Integrations (config presence only)

Without printing secret values, verify configuration fields / paths exist:

| Integration | Safe check |
|-------------|------------|
| Supabase | Settings expose URL/key fields; health route exists |
| Google Calendar | Credentials path configured; token file presence as boolean |
| Telegram | Bot token / chat id settings fields exist (boolean configured) |
| Ollama | Base URL + model settings fields exist; optional `is_available()` boolean |

Do **not** invoke Telegram send. Optional Ollama availability ping is allowed if it does not print prompts or calendar content.

### 4. Automated tests

From `backend/`:

```text
python -m pytest tests/ -q --tb=line
```

Report pass/fail counts. If pytest is missing, install only into the active env if appropriate, or mark Skip.

### 5. Desktop smoke (optional)

If PySide6 is available, import `pages.planner_page` and `widgets.summary_card` without launching a full GUI event loop when possible. Full GUI interaction remains a manual check.

## Report format

Return a concise report:

```markdown
# AI Study Planner Validator report

Date: YYYY-MM-DD
Purpose: pre-demo | pre-submission | ad-hoc

## Passed
- ...

## Failed
- ...

## Skipped
- ...

## Manual checks still required
- Desktop empty state / Hebrew summary columns
- Real Google OAuth + sync on the demo machine
- Ollama live polish (ai_mode=ollama vs rule_based_fallback)
- Telegram send (only when user requests)

## Files changed
- (none for validation-only runs)
```

## Evidence

When the user asks for AIA evidence, append a short entry to `docs/AIA_ARTIFACTS.md` with:

- Skill name: AI Study Planner Validator
- Skill path: `.cursor/skills/ai-study-planner-validator/SKILL.md`
- Date used
- Validation purpose
- Short result
- Manual checks remaining
