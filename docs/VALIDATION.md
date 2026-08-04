# Validation Checklist

Maps **Windows Systems Engineering / course requirements** to **AI Calendar Study Assistant** (repo: `ai-study-planner`).

**Legend:** `[ ]` not started · `[~]` in progress · `[x]` done

**Demo target:** Thursday evening

---

## Desktop application

| # | Requirement | How this project satisfies it | Status |
|---|-------------|-------------------------------|--------|
| 1 | Desktop UI using PySide6 / 6.5 | `desktop/main.py` + dashboard | `[x]` |
| 2 | MVP pattern (View / Presenter / Model) | `views/`, `presenters/`, `models/` | `[x]` |
| 3 | Modular UI | Dashboard + `widgets/category_chart.py` | `[x]` |
| 4 | Tables | Events table (time, category, title, end) | `[x]` |
| 5 | Graphs / charts | Category bar chart (`CategoryChartWidget`) | `[x]` |

---

## Backend

| # | Requirement | How this project satisfies it | Status |
|---|-------------|-------------------------------|--------|
| 6 | FastAPI backend server | Health, users, calendar, briefs routers | `[x]` |
| 7 | CQRS / MVC organization | Thin API + services + repositories | `[x]` |
| 8 | Cloud database (Supabase) | Schema applied + `SupabaseGateway` | `[x]` |

---

## External integrations (Gateway pattern)

| # | Requirement | How this project satisfies it | Status |
|---|-------------|-------------------------------|--------|
| 9 | Gateway classes | Supabase, Google Calendar, Telegram gateways | `[x]` |
| 10 | External service integration | Calendar sync + Telegram send | `[x]` |
| 11 | Ollama in Docker | Placeholder `AiRecommendationService`; Ollama later | `[~]` stub |
| 12 | LangChain + RAG / Chroma | Deferred post-demo; `rag/` package retained | `[ ]` deferred |
| 13 | Telegram integration | `TelegramGateway` + `/briefs/send-telegram` | `[x]` |

---

## Functional capabilities (pivot)

| # | Requirement | How this project satisfies it | Status |
|---|-------------|-------------------------------|--------|
| 14 | Users / demo flow | `POST /users/demo` + Load Demo Student | `[x]` |
| 15 | Data display | Today events table + chart | `[x]` |
| 16 | Viewing details | Event rows + brief text panel | `[x]` |
| 17 | AI agent (course) | Rule-based tip in brief via stub | `[~]` stub |
| 18 | Entering data | Calendar sync as primary data source | `[x]` |
| 19 | Study recommendations | Brief sections + AI tip | `[x]` |
| 20 | Daily / weekly brief | `/briefs/today`, `/briefs/weekly` | `[x]` |
| 21 | Google Calendar | Gateway + demo fallback + classifier | `[x]` |

---

## Process, repo, and AI artifacts

| # | Requirement | How this project satisfies it | Status |
|---|-------------|-------------------------------|--------|
| 22 | PIV process | [PIV_PLAN.md](PIV_PLAN.md) | `[x]` |
| 23 | Documentation | PRD, architecture, validation, PIV, AIA | `[x]` |
| 24 | GitHub / code repository | Project in git | `[~]` user push |
| 25 | Cursor / code-agent artifacts | [AIA_ARTIFACTS.md](AIA_ARTIFACTS.md) | `[x]` |
| 26 | Cursor Skill file | `calendar_study_agent_skill.md` | `[x]` |
| 27 | Event Sourcing (MVP) | `activity_events` on sync/brief/telegram | `[x]` |

---

## Database

- [x] Schema applied in Supabase
- [x] Tables present
- [x] Foreign keys as designed
- [x] `activity_events` written by services

---

## Demo checklist (Thursday evening)

### Backend

- [x] `GET /health` → ok
- [x] `GET /health/supabase` → ok (with `.env`)
- [x] `POST /calendar/sync` classifies events
- [x] `GET /calendar/events/today`
- [x] `POST /briefs/today`
- [x] `POST /briefs/send-telegram` (needs Telegram env)
- [x] `activity_events` logged

### Desktop

- [x] App launches
- [x] Load Demo Student
- [x] Sync Google Calendar / demo events
- [x] Today events table
- [x] Generate Today Brief
- [x] Send Brief to Telegram (env configured)
- [x] Status/errors visible
- [x] Category chart
- [x] No Google/Telegram/Supabase imports in `views/`

### Integration

- [x] Desktop → FastAPI → Google Calendar (or demo)
- [x] Desktop → FastAPI → Telegram
- [x] Desktop → FastAPI → Supabase
- [ ] Live end-to-end demo rehearsed on presentation machine

---

## Sign-off

| Area | Date | Notes |
|------|------|-------|
| Calendar + classification | | |
| Brief + Telegram | | |
| Desktop dashboard | | |
| Supabase + activity log | | |
| AI placeholder | | |
| Documentation + demo | | |
