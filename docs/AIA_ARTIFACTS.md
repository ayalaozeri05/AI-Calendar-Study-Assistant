# AI-Assisted Artifacts (AIA)

Development of **AI Calendar Study Assistant** (repo: `ai-study-planner`) uses **Cursor** as the primary AI coding assistant.

## Purpose

- Record iterative, AI-assisted development
- Preserve pivot decisions and significant prompts
- Support demo narrative and grading evidence

## What Cursor is used for

| Activity | Examples |
|----------|----------|
| **Generate** | Gateways, brief service, dashboard presenter, schemas |
| **Refactor** | Pivot from full planner to calendar assistant |
| **Review** | Architecture boundaries, secret handling |
| **Document** | PRD, PIV, architecture, validation |
| **Debug** | Health routes, imports, API contracts |

## Project rules for Cursor

**Discoverable Cursor Agent Skill (required format):**  
[`.cursor/skills/ai-study-planner-validator/SKILL.md`](../.cursor/skills/ai-study-planner-validator/SKILL.md) — *AI Study Planner Validator*

Legacy markdown guidance (not Agent Skills):  
[`skills/calendar_study_agent_skill.md`](../skills/calendar_study_agent_skill.md),  
[`skills/cursor_project_architect.md`](../skills/cursor_project_architect.md)

---

## Artifact log

### 2026-08-07 — Stable demo mode (`AI_POLISH_ENABLED`)

**Decision:** Keep full Ollama-in-Docker + wording-polish implementation; default desktop Study Plan uses the deterministic engine only (`ai_mode=deterministic`). No timeout/fallback UI banners in normal mode. RAG still deferred.

**Outcome:** Config flag `AI_POLISH_ENABLED` (default false); desktop shows "Study plan created"; Ollama verification path documented when flag is true.

---

### 2025-06 — Initial scaffold

**Prompt:** Create FastAPI + PySide6 MVP scaffold with docs and skills.

**Outcome:** `backend/`, `desktop/`, `docs/`, `skills/`; health endpoint.

---

### 2025-06 — Supabase schema + gateway

**Prompt:** Apply schema via MCP; connect FastAPI through SupabaseGateway.

**Outcome:** Six tables live; `GET /health/supabase`.

---

### 2026-08 — Pivot to AI Calendar Study Assistant

**Prompt:** Pivot docs for Google Calendar → brief → Telegram; reuse structure.

**Outcome:** Docs + `calendar_study_agent_skill.md`; RAG deferred.

---

### 2026-08 — Sprint 2: Calendar gateway + classifier

**Prompt:** Implement GoogleCalendarGateway, classifier, sync/today endpoints.

**Outcome:**
- `GoogleCalendarGateway` with demo fallback
- `CalendarEventClassifier`
- `POST /calendar/sync`, `GET /calendar/events/today`
- `activity_events` log `calendar_synced`

---

### 2026-08 — Sprint 3: Briefs + Telegram

**Prompt:** StudyBriefService, TelegramGateway, brief APIs.

**Outcome:**
- `/briefs/today`, `/briefs/weekly`, `/briefs/send-telegram`
- `AiRecommendationService` stub tip in brief
- Persist brief to `ai_chat_history` when possible

---

### 2026-08 — Sprint 4: Desktop dashboard

**Prompt:** PySide6 dashboard for demo flow with table + chart.

**Outcome:**
- MVP View / Presenter / Model / `api_client`
- Buttons for demo, sync, today, brief, Telegram
- Category bar chart widget

---

### 2026-08 — Sprint 5: Polish + demo prep

**Prompt:** Demo telegram chat id from env; update validation/README/demo script.

**Outcome:**
- `DEMO_TELEGRAM_CHAT_ID` applied on `POST /users/demo`
- Validation checklist marked against implemented MVP
- README demo click path

---

## Demo script (Thursday evening)

### Setup (before presentation)

1. Copy `.env.example` → `.env` with Supabase keys
2. Optional Telegram: `TELEGRAM_BOT_TOKEN` + `DEMO_TELEGRAM_CHAT_ID`
3. Start backend: `cd backend` → `uvicorn app.main:app --reload`
4. Start desktop: `cd desktop` → `python main.py`

### Live demo (~5 minutes)

1. Open desktop window — show architecture verbally: **Desktop → FastAPI → Gateways**
2. Click **Load Demo Student** — status shows student email / Telegram chat id
3. Click **Sync Google Calendar** — table fills (demo events if no Google file)
4. Point at **category chart** (Exam / Study / Assignment / …)
5. Click **Show Today Events** — confirm filter for today
6. Click **Generate Today Brief** — brief panel shows sections + Tip
7. Click **Send Brief to Telegram** — show phone notification (if configured)
8. Mention **Supabase** `activity_events` as MVP Event Sourcing
9. Mention **Cursor** skills + this AIA log as AI-assisted development evidence
10. Mention **PIV** compressed sprint to deadline

### Fallback if Telegram is unavailable

- Still demo steps 1–6
- Explain Gateway is implemented; env not set on demo machine
- Show Swagger `/docs` for `/briefs/send-telegram`

### Fallback if Supabase is unavailable

- Health endpoints show error clearly
- Explain Gateway returns structured failure (status banner)

---

### 2026-08 — Git safety audit before GitHub upload

**Action:**
> Prepare repository for safe GitHub upload; audit secrets and `.gitignore`.

**Outcome:**
- Expanded `.gitignore` for `.env`, credentials, caches, venvs, Chroma paths
- Removed real Telegram/Supabase values from `.env.example` (placeholders only)
- Verified `.env` is ignored and not staged
- Local commit created for working MVP snapshot

**Decision:**
- Never commit `.env` or credential JSON files; use `.env.example` only

---

### 2026-08 — Real Google Calendar OAuth (per-user)

**Prompt (summary):**
> Replace mock/service-account calendar flow with InstalledAppFlow OAuth, per-user token files, connect/status/sync APIs, EN+HE classifier, desktop Connect button.

**Outcome:**
- `GoogleCalendarGateway` uses `google-auth-oauthlib` + readonly scope
- Tokens stored under `local_tokens/google_calendar/<user_id>.json` (gitignored)
- Endpoints: `/calendar/status`, `/calendar/connect`, `/calendar/sync`, `/events/today`, `/events/week`
- Desktop: Connect Google Calendar + connection status label
- Demo/mock events removed from primary sync path (clear errors instead)

**Decision:**
- OAuth client JSON ≠ user token; document both in README / secrets/README.md

---

### 2026-08-06 — Cursor Agent Skill + compliance validation

**Skill name:** AI Study Planner Validator  
**Skill file path:** `.cursor/skills/ai-study-planner-validator/SKILL.md`  
**Date used:** 2026-08-06  
**Validation purpose:** Pre-demo / pre-submission safe compliance run (no Telegram send, no OAuth restart, no DB reset)

**How invoked:** Agent read and executed the Skill procedure against the local repository (secrets audit, FastAPI import, health probes, integration config booleans, pytest).

**Short result:**
- Secrets: `.env` / credential patterns ignored; tracked secret-pattern scan = 0 hits; `secrets/` untracked
- Backend: import ok; `/health` ok; `/health/supabase` ok
- Integrations (booleans only): Supabase + Telegram settings present; Google credentials path configured; local creds/token files not present in this environment; Ollama unavailable / model unset → expect `rule_based_fallback`
- Tests: **56 passed**
- Telegram send: not performed

**Manual checks remaining:**
- Desktop Today empty state (compact under EVENTS) + Hebrew Highest Priority column stability
- Live Google OAuth + sync on the demo machine
- Live Ollama polish confirming `ai_mode=ollama` when model is running
- Optional Telegram send only when explicitly requested

**Related docs:** [`docs/REQUIREMENTS_COMPLIANCE.md`](REQUIREMENTS_COMPLIANCE.md)

**UI fixes in same sprint (not scheduling-logic changes):**
- Compact range-aware empty state under EVENTS
- Fixed LTR three-column summary strip (`dir="auto"` only on priority title text)
