# AI Calendar Study Assistant

> **Repository:** `ai-study-planner` · **Product:** AI Calendar Study Assistant

A **PySide6 desktop application** for students that connects to **Google Calendar via OAuth**, classifies academic events, builds a **daily/weekly study brief**, and sends it to **Telegram**.

## What it does (MVP)

1. Load a demo student profile (Supabase)
2. **Connect Google Calendar** (browser OAuth, per-user token)
3. **Sync** real events from the primary calendar
4. Classify events (English + Hebrew keywords): Exam, Assignment, Project, Study, Class, Meeting, Other
5. Generate **Today Study Brief** or **Weekly Study Brief** (includes title + description)
6. Send **Today** or **Weekly** brief to Telegram
7. Show events in a table (with description) + category chart with friendly status messages

AI/Ollama is a **later phase** (`AiRecommendationService` stub is wired into briefs).

## Stack

| Layer | Technology |
|-------|------------|
| Desktop | PySide6 (MVP: views / presenters / models) |
| Backend | FastAPI (services, repositories, CQRS-style layout) |
| Database | Supabase |
| Calendar | Google Calendar API + OAuth (`google-auth-oauthlib`) |
| Messaging | Telegram Bot via `TelegramGateway` |
| AI (stub) | `AiRecommendationService` (Ollama later) |

**Rule:** Desktop talks **only** to FastAPI. FastAPI talks to externals through **Gateway** classes.

## Setup

```powershell
copy .env.example .env
```

| Variable | Required for |
|----------|----------------|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | Demo user + activity log |
| `TELEGRAM_BOT_TOKEN`, `DEMO_TELEGRAM_CHAT_ID` | Send brief to Telegram |
| `GOOGLE_CALENDAR_CREDENTIALS_PATH` | Path to Desktop OAuth client JSON |
| `GOOGLE_CALENDAR_TOKEN_DIR` | Per-user token directory (default `local_tokens/google_calendar`) |

### Google Cloud setup (required for real calendar)

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select one)
3. Enable **Google Calendar API**
4. Configure **OAuth consent screen** (External or Internal; add your Google account as a test user while in Testing)
5. Create **OAuth client ID** → Application type: **Desktop app**
6. Download the JSON client file
7. Save it as `secrets/google_calendar_credentials.json` (or set `GOOGLE_CALENDAR_CREDENTIALS_PATH`)
8. Restart the backend

**Credentials vs tokens:**

- OAuth **client JSON** = app credentials (shared)
- `local_tokens/google_calendar/<user_id>.json` = each user's token after they approve access (not in Git)

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
| http://127.0.0.1:8000/calendar/status?user_id=... | Google connection status |

## Run desktop

```powershell
cd desktop
pip install -r requirements.txt
python main.py
```

### Desktop click path (three screens)

1. **Start Planner** — loads your student profile quietly (no demo/UUID wording)
2. **Calendar** — Connect Google Calendar (if needed) → **Sync Calendar**
3. After sync, **Planner opens automatically**
4. Choose a range: **Today / 7 Days / 14 Days / This Month / Custom**
5. Create the matching plan, then **Send to Telegram**
6. Use **Sync calendar** or **← Calendar** anytime

Workload timeline shows busy days (hidden for Today). Descriptions are cleaned of Google Tasks boilerplate.

There is **no silent demo-event fallback**. Empty calendars show a calm empty state, not an error.

## Documentation

| Document | Description |
|----------|-------------|
| [PRD](docs/PRD.md) | Product requirements |
| [PIV Plan](docs/PIV_PLAN.md) | Sprint plan |
| [Architecture](docs/ARCHITECTURE.md) | System design |
| [AIA Artifacts](docs/AIA_ARTIFACTS.md) | Cursor / AI development log |
| [Validation](docs/VALIDATION.md) | Course requirements checklist |
| [secrets/README.md](secrets/README.md) | Where to place Google OAuth client JSON |

Cursor skill: [`skills/calendar_study_agent_skill.md`](skills/calendar_study_agent_skill.md)
