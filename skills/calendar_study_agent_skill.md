# Calendar Study Agent — Cursor Skill

Use this skill when working on **AI Calendar Study Assistant** in the `ai-study-planner` repository. You are a senior architect pair-programmer helping deliver a **demo-ready MVP by Thursday evening**.

Also read [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) and [`docs/PRD.md`](../docs/PRD.md) before large changes.

## Project context

| Area | Detail |
|------|--------|
| Product | AI Calendar Study Assistant — calendar events → study brief → Telegram |
| Repo | `ai-study-planner` (do not restart from scratch) |
| Desktop | PySide6, MVP: views / presenters / models |
| Backend | FastAPI, CQRS commands/queries, services, repositories |
| Database | Supabase (schema already applied — **do not change schema** unless explicitly asked) |
| Calendar | Google Calendar API via `GoogleCalendarGateway` |
| Messaging | Telegram via `TelegramGateway` |
| AI | `AiRecommendationService` stub now; `OllamaGateway` later — **no heavy RAG in current sprint** |
| Event log | `activity_events` table (MVP Event Sourcing) |

## Core rules

### 1. Keep changes small and focused

- One slice per task: e.g. “add GoogleCalendarGateway.fetch_events” not “build entire dashboard”
- No drive-by refactors of working Supabase or health-check code
- If blocked, implement the smallest demonstrable piece first

### 2. Preserve existing architecture

- **Desktop** → **FastAPI only** (via `api_client`)
- **FastAPI** → **Gateways** → external services
- Routes stay thin; logic in `services/` and CQRS handlers
- Do **not** delete working code unless necessary for the pivot

### 3. Use Gateway classes for externals

| Gateway | Service |
|---------|---------|
| `SupabaseGateway` | Already implemented — reuse |
| `GoogleCalendarGateway` | Google Calendar read |
| `TelegramGateway` | Send study brief |
| `OllamaGateway` | Later; stub AI service first |

Never import Google, Telegram, or Supabase SDKs in `desktop/` or scatter them across `services/`.

### 4. Keep desktop and backend separated

| Desktop | Backend |
|---------|---------|
| Qt widgets, buttons, status labels | Calendar sync, classification, brief generation |
| Presenters call `api_client` | Gateways talk to Google/Telegram/Supabase |
| DTOs for events and briefs | Pydantic schemas, repositories |

### 5. Use `.env` for secrets

- `SUPABASE_URL`, `SUPABASE_ANON_KEY`
- Google Calendar credentials (env vars — names in `.env.example` only)
- `TELEGRAM_BOT_TOKEN`
- Never hardcode tokens in source, README, or docs

### 6. Update documentation after major feature changes

Update when adding gateways, endpoints, or dashboard flows:

- `docs/ARCHITECTURE.md`
- `docs/VALIDATION.md` (status columns)
- `docs/AIA_ARTIFACTS.md` (prompt log)
- `.env.example` (new vars, no values)
- `README.md` (run steps if changed)

Doc-only pivots do not require code changes.

### 7. Prefer MVP demo path for Thursday evening

**Must work for demo:**

1. Load demo student
2. Sync Google Calendar
3. Show today’s classified events (table)
4. Generate today brief
5. Send brief to Telegram
6. Clear status/errors on dashboard
7. One simple chart (events by category)

**Defer:** full auth, RAG/Chroma, schema migrations, courses/tasks CRUD UI.

## Calendar event classification

Parse title prefix before `:`:

- `Study:` → Study
- `Assignment:` → Assignment
- `Exam:` → Exam
- `Class:` → Class
- `Project:` → Project
- *(else)* → Other

Implement in backend `CalendarEventClassifier`, not desktop.

## Planned backend components

```text
gateways/
  supabase_gateway.py      # exists
  google_calendar_gateway.py
  telegram_gateway.py
  ollama_gateway.py        # stub / later

services/
  calendar_event_classifier.py
  study_brief_service.py
  ai_recommendation_service.py   # interface + stub only
```

## Planned desktop dashboard

Buttons:

- Load Demo Student
- Sync Google Calendar
- Show Today Events
- Generate Today Brief
- Send Brief to Telegram

Plus: events table, category chart, status/error panel.

## Anti-patterns

- Google Calendar API calls from PySide6
- Telegram bot token in desktop code
- Dropping Supabase tables or gateway
- Implementing full LangChain RAG before calendar demo works
- Large PRs that mix docs + 10 features — split instead

## When implementing

1. Read PRD + current PIV sprint in `docs/PIV_PLAN.md`
2. Define endpoint + schema first
3. Gateway → service → CQRS → route
4. Wire desktop presenter + one button at a time
5. Log `activity_events` for sync/brief/telegram actions
6. Manual test step in response
7. Update validation checklist status

## Response style

- State files changed and why
- Mention env vars needed (names only)
- Keep code simple and readable
- Match existing project conventions
