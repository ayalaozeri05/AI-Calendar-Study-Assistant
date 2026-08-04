# PIV Development Plan

**Product:** AI Calendar Study Assistant · **Repo:** `ai-study-planner`

This project follows **PIV**: **P**roduct/Planning, **I**terative Implementation, **V**alidation.

Given the **close submission deadline**, the plan is a **compressed sprint** to a demo-ready MVP by **Thursday evening**. Existing Week 1 work (scaffold, Supabase schema, `SupabaseGateway`) is **reused**, not discarded.

---

## Completed — Foundation (reuse)

| Item | Status |
|------|--------|
| FastAPI scaffold, health routes | Done |
| PySide6 shell, MVP folder layout | Done |
| Supabase schema applied (6 tables) | Done |
| `SupabaseGateway` + `/health/supabase` | Done |
| Documentation + Cursor skills | Updated for pivot |

---

## Sprint 1 — Documentation pivot — Done

**Product / Planning**

- Update PRD, architecture, validation for calendar-first MVP
- Define event prefix classification rules
- Add `calendar_study_agent_skill.md` for Cursor

**Validation**

- Docs reflect new scope without deleting existing architecture
- Course requirement mapping updated in VALIDATION.md

---

## Sprint 2 — Google Calendar + classification — Done

**Product / Planning**

- Google OAuth or service-account flow (MVP: single demo calendar)
- API endpoints: `POST /calendar/sync`, `GET /calendar/events/today`
- Classification rules documented in PRD

**Iterative Implementation**

- `GoogleCalendarGateway` in `backend/app/gateways/`
- `CalendarEventClassifier` service (prefix → category)
- CQRS query: list today’s events
- Log `calendar_synced` to `activity_events`
- `.env.example`: `GOOGLE_CALENDAR_*` placeholders

**Validation**

- Gateway fetches events from demo calendar
- Events classified correctly for sample titles
- No Google SDK in desktop

---

## Sprint 3 — Brief service + Telegram — Done

**Product / Planning**

- Brief text template (today vs weekly)
- Telegram message format (Markdown/plain)

**Iterative Implementation**

- `StudyBriefService` — builds today/weekly brief from classified events
- `TelegramGateway` — send message to `users_profile.telegram_chat_id`
- Endpoints: `POST /briefs/today`, `POST /briefs/weekly`, `POST /briefs/send-telegram`
- Log `brief_generated`, `telegram_sent` to `activity_events`

**Validation**

- Brief text includes categorized sections
- Test message arrives in Telegram
- Errors return clear JSON (missing chat id, bad token)

---

## Sprint 4 — Desktop dashboard (demo UI) — Done

**Product / Planning**

- Single dashboard view with action buttons and status panel
- Table widget for today’s events

**Iterative Implementation**

- `DashboardView` + `DashboardPresenter`
- `api_client` methods for all backend actions
- Buttons: Load Demo Student · Sync Google Calendar · Show Today Events · Generate Today Brief · Send Brief to Telegram
- Status label / error dialog for failures
- Simple chart: events by category (Qt Charts or minimal matplotlib)

**Validation**

- Full demo flow works end-to-end from desktop
- Presenters only — no external SDKs in views
- Empty/error states handled

---

## Sprint 5 — Polish + demo prep — Done (rehearse live)

**Product / Planning**

- Demo script in AIA_ARTIFACTS.md
- Final VALIDATION.md pass

**Iterative Implementation**

- `AiRecommendationService` placeholder (interface + stub response)
- UI polish, window title update
- README run instructions verified on demo machine

**Validation**

- [VALIDATION.md](VALIDATION.md) checklist mostly green
- Record demo video or live run steps
- GitHub repo up to date

---

## Deferred (after demo)

- Ollama + LangChain + Chroma RAG
- Full auth / RLS
- Schema extensions for persisted calendar events
- Courses/tasks CRUD UI

---

## Ongoing practices

- Small commits; one gateway or one endpoint per step
- Update docs after each major feature
- Log Cursor prompts in [AIA_ARTIFACTS.md](AIA_ARTIFACTS.md)
- Do not delete working Supabase or Gateway code unless necessary
