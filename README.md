# AI Calendar Study Assistant

> **Repository:** `ai-study-planner` (legacy name) · **Product:** AI Calendar Study Assistant

A **PySide6 desktop application** for students that reads **Google Calendar** academic events, classifies them into study-related categories, builds a **daily or weekly study brief**, and sends the brief to **Telegram**.

## What it does (MVP)

1. Load a demo student profile
2. Sync events from Google Calendar (or built-in demo events)
3. Classify events by title prefix (`Study:`, `Assignment:`, `Exam:`, `Class:`, `Project:`, `Other`)
4. Generate **Today Study Brief** and **Weekly Study Brief**
5. Send the brief to Telegram
6. Show events in a table, category chart, and clear status/errors

AI/Ollama is a **later phase** (`AiRecommendationService` stub is already wired into briefs).

## Stack

| Layer | Technology |
|-------|------------|
| Desktop | PySide6 (MVP: views / presenters / models) |
| Backend | FastAPI (services, repositories, CQRS-style layout) |
| Database | Supabase |
| Calendar | Google Calendar API via `GoogleCalendarGateway` |
| Messaging | Telegram Bot via `TelegramGateway` |
| AI (stub) | `AiRecommendationService` (Ollama later) |
| Dev process | PIV · Cursor |

**Rule:** Desktop talks **only** to FastAPI. FastAPI talks to externals through **Gateway** classes.

## Documentation

| Document | Description |
|----------|-------------|
| [PRD](docs/PRD.md) | Product requirements |
| [PIV Plan](docs/PIV_PLAN.md) | Sprint plan |
| [Architecture](docs/ARCHITECTURE.md) | System design |
| [AIA Artifacts](docs/AIA_ARTIFACTS.md) | Cursor / AI development log + demo script |
| [Validation](docs/VALIDATION.md) | Course requirements checklist |

Cursor skills: [`skills/calendar_study_agent_skill.md`](skills/calendar_study_agent_skill.md)

## Setup

```powershell
copy .env.example .env
```

Fill in `.env` (never commit real secrets):

| Variable | Required for |
|----------|----------------|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | Demo user + activity log |
| `TELEGRAM_BOT_TOKEN`, `DEMO_TELEGRAM_CHAT_ID` | Send brief to Telegram |
| `GOOGLE_CALENDAR_CREDENTIALS_FILE` | Real Google sync (optional; demo events if empty) |

## Run backend

```powershell
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

| URL | Description |
|-----|-------------|
| http://127.0.0.1:8000/docs | Swagger UI |
| http://127.0.0.1:8000/health | API health |
| http://127.0.0.1:8000/health/supabase | Supabase health |

## Run desktop

```powershell
cd desktop
pip install -r requirements.txt
python main.py
```

### Demo click path

1. **Load Demo Student**
2. **Sync Google Calendar** (uses demo events if Google is not configured)
3. **Show Today Events**
4. **Generate Today Brief**
5. **Send Brief to Telegram** (needs Telegram env vars)

## Current status

MVP path is implemented: Supabase, Google Calendar gateway (with demo fallback), study briefs, Telegram gateway, PySide6 dashboard with table + chart.

See [PIV Plan](docs/PIV_PLAN.md) and [Validation](docs/VALIDATION.md).
