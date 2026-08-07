# Requirements compliance matrix

**Product:** AI Calendar Study Assistant (`ai-study-planner`)  
**Audit date:** 2026-08-06  
**Branch context:** `cursor/planning-lifecycle-and-ux-fixes` (+ local UI/skill fixes)

Statuses used: **Complete** · **Partial** · **Not implemented** · **Not required / future scope**

| Requirement | Status | Implementation | Evidence | Remaining limitation |
|-------------|--------|----------------|----------|----------------------|
| Windows / PySide6 desktop | Complete | Three-screen shell: Start → Calendar → Planner (`desktop/`) | `desktop/main.py`, `views/dashboard_view.py`, pages/widgets | Demo UX only; not a packaged installer |
| FastAPI backend | Complete | FastAPI app with calendar/briefs/users/health routes | `backend/app/main.py`, `/health` returned `{"status":"ok"}` on 2026-08-06 | Local MVP hosting |
| Supabase database | Complete | Supabase gateway + health; tables used for user/activity/history | `SupabaseGateway`, `/health/supabase` → ok | Relies on project env; not multi-tenant hardened |
| Gateway Pattern | Complete | Externals via gateways: Google Calendar, Telegram, Supabase, Ollama | `backend/app/gateways/*` | — |
| CQRS | Partial | Folder layout `cqrs/commands` + `cqrs/queries` exists; business flow is service-oriented | Empty `__init__.py` packages under `cqrs/` | No separate command/query handler layer in active use |
| MVC / MVP separation | Complete | Desktop MVP: views/pages display, presenters coordinate, models hold state; API client is HTTP boundary | `desktop/presenters/`, `views/`, `models/`, `api_client/` | Some pages embed light UI logic (acceptable for MVP) |
| Event / activity log | Partial | Append-only `activity_events` writes on sync/brief actions | `activity_repository.py`, sync/brief services | **Not** full Event Sourcing — app state cannot be rebuilt solely from the log |
| Google Calendar OAuth | Complete | Installed-app OAuth + per-user token files | `GoogleCalendarGateway`, README Google setup | Local token files ≠ production multi-user auth |
| Real calendar sync | Complete | Sync primary calendar into app; no silent demo-event fallback | `/calendar/sync`, desktop Sync flow | Requires valid credentials + prior OAuth on machine |
| Event classification | Complete | EN + HE keyword classifier into academic categories | `calendar_event_classifier.py`, tests | Heuristic; not ML |
| Event description handling | Partial | Cleaner removes Tasks boilerplate; preserves mixed notes when present | `description_cleaner.py`, diagnostics tests | Google **Tasks notes** often absent from Calendar API without Tasks API |
| Time-range planning | Complete | Today / 7 / 14 / Month / Custom ranges drive events + plans | `RangeSelector`, briefs APIs | — |
| Scheduling engine | Complete | Deterministic engine owns WHEN; exam lifecycle, recovery, fixed events, stages | `study_scheduling_engine.py`, scheduling tests (56 backend tests green) | Continues to evolve with UX feedback |
| Ollama / LangChain usage | Partial | Real `ChatOllama` polish path via `OllamaGateway` + LangChain | `ollama_gateway.py`, `ai_recommendation_service.py` | On 2026-08-06 validation: `ollama_available=False`, model unset → plans use **`ai_mode=rule_based_fallback`** unless Ollama is running with a model |
| Fallback mode | Complete | Engine plan always; Ollama only polishes content when available | `AiRecommendationService.generate_study_plan` | — |
| Telegram sending | Complete | Manual Send to Telegram from Study Plan | `TelegramGateway`, brief send endpoint | User-triggered only |
| Long Telegram message splitting | Complete | Chunker + part headers under Telegram limits | `telegram_message_splitter.py`, tests | — |
| Git secret safety | Complete | `.env`, credentials, tokens, `secrets/*.json` gitignored; tracked secret scan clean | `.gitignore`; validator scan `tracked_secret_pattern_hits=0` | Operators must keep local `secrets/` untracked |
| README / setup documentation | Complete | Setup, OAuth, run backend/desktop, docs index | `README.md`, `docs/*`, `secrets/README.md` | README AI section historically lagged; Skill path documented |
| Cursor Agent Skill | Complete | Project skill `ai-study-planner-validator` with `SKILL.md` frontmatter | `.cursor/skills/ai-study-planner-validator/SKILL.md`; used 2026-08-06 | Older `skills/*.md` files are docs, not Agent Skills |
| Automatic daily/weekly Telegram delivery | Not implemented | No scheduler/cron/worker found | Manual send only | Would need a scheduler + consent UX |
| Google Tasks notes | Partial | Calendar descriptions cleaned; Tasks API not connected | Description cleaner + gateway notes | Notes living only in Google Tasks may not appear |
| RAG / document retrieval | Complete | Standalone `app/rag/` + `/rag/upload` + `/rag/ask` + desktop Study Materials | `backend/app/rag/*`, `api/rag.py` | Real Chroma retrieval; not mixed into scheduling |
| Production authentication / RLS | Not implemented | Local OAuth token files + demo user path | Token dir under `local_tokens/` | Not production multi-user; Supabase RLS not demonstrated as app auth |

## Validation snapshot (2026-08-06)

Invoked skill: **AI Study Planner Validator**  
Path: `.cursor/skills/ai-study-planner-validator/SKILL.md`

| Check | Result |
|-------|--------|
| `.env` ignored / not tracked | Pass |
| Credential/token ignore patterns | Pass |
| Tracked secret pattern scan | Pass (0 hits) |
| FastAPI import | Pass |
| `GET /health` | Pass |
| `GET /health/supabase` | Pass |
| Supabase settings configured | Pass (boolean) |
| Google credentials path set | Pass (boolean); local file existence was False in this environment |
| Google token files present | Fail/absent in this environment (0 files) |
| Telegram settings configured | Pass (boolean; no send performed) |
| Ollama available + model set | Fail/absent → expect `rule_based_fallback` |
| `pytest` | Pass — **56 passed** |
| Telegram send during validation | Not run (by design) |

## Honest AI mode note

Do not claim live Ollama polish unless a brief response reports `ai_mode=ollama`. With Ollama down or `OLLAMA_MODEL` empty, the product correctly falls back to the deterministic scheduling engine (`rule_based_fallback`).
