# AI Implementation Audit — Ollama, LangChain, RAG

**Updated:** 2026-08-07 — stable demo mode (`AI_POLISH_ENABLED`)  
**Original audit date:** 2026-08-06  

---

## 0. Current product mode (stable demo)

| Item | Status |
|------|--------|
| Scheduling engine | Owns times, order, kinds (unchanged) |
| Ollama in Docker | Implemented, health-verified, **kept** |
| Optional wording polish | Implemented (wording-only payload); gated by `AI_POLISH_ENABLED` |
| Stable demo default | `AI_POLISH_ENABLED=false` → `ai_mode=deterministic` (immediate, no Ollama wait) |
| RAG | **Not implemented** (next stage) |

Precedence: `AI_POLISH_ENABLED=false` always skips polish intentionally. `SKIP_OLLAMA_POLISH` remains a deprecated diagnostic override only.

---

## 1. Executive summary

| Technology | Status | One-line finding |
|------------|--------|------------------|
| **Ollama** | Implemented + Docker health path | `OllamaGateway` (httpx `/api/chat` with hard timeouts) + `/health/ollama`; polish optional |
| **LangChain** | Dependencies retained; polish uses direct Ollama HTTP for cancellable timeouts | Packages remain for course/stack continuity; wording polish calls Ollama API via httpx |
| **RAG** | Not implemented | Deferred; will use local Ollama next |

**Normal Study Plan (demo):** deterministic engine (`ai_mode=deterministic`). Do not claim Ollama-generated when polish is disabled.

---

## 2. Ollama status

**Classification: Implemented but not live-verified**

### Evidence — implementation

| Question | Answer | Evidence |
|----------|--------|----------|
| Gateway/client implemented? | Yes | `backend/app/gateways/ollama_gateway.py` — class `OllamaGateway` |
| Who performs the request? | `OllamaGateway.invoke` | Same file, method `invoke` |
| Transport | **LangChain** `ChatOllama.invoke` for generation; **raw HTTP** (`httpx`) for `/api/tags` availability | `list_models` → `GET {base}/api/tags`; `invoke` → `ChatOllama(...)` |
| Config model | `settings.ollama_model` / env `OLLAMA_MODEL` | `backend/app/config.py`; `.env.example` has empty placeholders |
| Base URL | Default `http://localhost:11434` | `OllamaGateway.base_url` |
| Input to model | Free-text coach prompt + engine plan JSON + event metadata JSON | `AiRecommendationService._polish_with_ollama` |
| Expected output | JSON matching `StructuredStudyPlan` | Prompt: “Return ONLY valid JSON…”; parsed by `_parse_plan_json` |
| Used in visible plan? | **Only for wording** when polish succeeds: summary, tips, priority reason, study `action`/`reason`. Times/kind/title/order stay engine-owned | `_merge_content` |
| Fallback conditions | No model configured; Ollama unreachable; model missing; polish/parse exception; `force_fallback=True` | `is_available()` requires non-empty model + tag list; exceptions keep engine plan |
| API indicator | Yes — `BriefResponse.ai_mode` and `meta.ai_mode` | Values: `"ollama"` or `"rule_based_fallback"` (`brief_schema.py`, `study_brief_service.py`) |

### Evidence — live probe (2026-08-06, this machine)

| Check | Result |
|-------|--------|
| `OLLAMA_MODEL` configured | **No** (empty) |
| `GET http://127.0.0.1:11434/api/tags` | **Unavailable** (connection failed) |
| `OllamaGateway.is_available()` | **False** |
| Synthetic Ollama plan polish | **Not run** (prerequisites missing; would send no private calendar data anyway) |
| Expected production mode here | **`ai_mode=rule_based_fallback`** |

**Missing prerequisites for live Ollama:** Ollama process listening on configured base URL; `OLLAMA_MODEL` set; that model present in `/api/tags` (e.g. after `ollama pull <model>` — not performed in this audit).

---

## 3. LangChain status

**Classification: Complete** *(LangChain participates in the actual model path when Ollama polish runs)*

### Declared vs installed packages

| Package | Declared (`backend/requirements.txt`) | Installed (active env) | Imported in app code | Used at runtime |
|---------|----------------------------------------|-------------------------|----------------------|-----------------|
| `langchain` | `>=0.3` | Yes `1.3.14` | No direct import found | Indirect dependency only |
| `langchain-core` | `>=0.3` | Yes `1.5.3` | Yes — `HumanMessage`, `SystemMessage` | Yes, inside `OllamaGateway.invoke` |
| `langchain-ollama` | `>=0.2` | Yes `1.1.0` | Yes — `ChatOllama` | Yes, inside `OllamaGateway.invoke` |
| `langchain-community` | Not declared | No | No | No |
| `ollama` (Python client) | Not declared | Present (version attr unset) | **No** | **No** — not on the invoke path |
| `chromadb` | Not declared | No | No | No |
| `sentence-transformers` | Not declared | No | No | No |

`desktop/requirements.txt` has no AI packages (PySide6 + requests only). No `pyproject.toml` / poetry lock found.

### LangChain usage detail

| Question | Answer |
|----------|--------|
| Invoked on production path? | Yes, **only when** `AiRecommendationService` calls `OllamaGateway.invoke` after `is_available()` |
| Classes used | `ChatOllama`, `SystemMessage`, `HumanMessage` |
| Prompt creation | String template in `AiRecommendationService._polish_with_ollama` (not `ChatPromptTemplate`) |
| Model invoke | `llm.invoke(messages)` in `OllamaGateway.invoke` |
| Structured output helpers | **None** — no `JsonOutputParser`, `with_structured_output`, `PydanticOutputParser` |
| Retry | Manual second `invoke` if JSON parse fails (`temperature=0.0`) |
| Plan dependence | Times/structure from engine; content fields may be overwritten by merged LLM JSON |

**Not found in codebase:** `ChatPromptTemplate`, `RunnableSequence`, `|` chains, agents, `OllamaLLM`, `ollama.Client`, raw `/api/generate` or `/api/chat` HTTP for generation.

---

## 4. Structured-output status

**Classification: Partial** (schema is real; LLM JSON is best-effort; engine always owns structure)

1. **Expected schema:** `StructuredStudyPlan` (`summary`, `priority_item`, `daily_plan[]` of `StudyPlanItem`, `tips`, `planning_anchor`) in `backend/app/schemas/brief_schema.py`.
2. **Does the LLM generate it?** Optionally — asked to return same JSON structure; schedule fields are instructed not to change.
3. **Validated?** Yes — `StructuredStudyPlan.model_validate` via `_parse_plan_json`.
4. **On invalid output?** One retry invoke; then `OllamaError` → outer catch keeps **engine plan** and `ai_mode` stays / falls back to rule path.
5. **UI renders:** Always a `StructuredStudyPlan` from the engine, optionally with polished text fields. Deterministic blocks (times, calendar, recovery, breaks) are not LLM-authored.

---

## 5. RAG status

**Classification: Not implemented**

| Stage | Status | Evidence |
|-------|--------|----------|
| 1. Document upload/ingestion | Missing | No upload API/UI; no service writing `study_documents` |
| 2. Text extraction | Missing | No PDF/text loaders |
| 3. Chunking | Missing | No chunking module (unrelated “chunk” strings are Telegram/calendar helpers) |
| 4. Embeddings | Missing | No embedding library or calls; `sentence-transformers` / embedding deps absent |
| 5. Vector storage | Placeholder only | `chromadb` not installed; `.gitignore` lists `chroma*` paths; schema comment mentions Chroma |
| 6. Retrieval | Missing | No retriever / similarity search |
| 7. Prompt augmentation | Missing | Polish prompt uses calendar events + engine JSON only — **not** retrieved documents |
| 8. Use in visible AI output | Missing | No RAG context in plan path |

**Present but not RAG:**

- `backend/app/rag/__init__.py` — one-line package docstring only  
- SQL table `study_documents` in `backend/database/schema.sql` — metadata table; comment says embeddings “stay in ChromaDB” (aspirational)  
- Docs marking RAG deferred (`PRD.md`, `ARCHITECTURE.md`, `PIV_PLAN.md`, `VALIDATION.md`)

Passing Google Calendar events into a prompt is **not** RAG.

---

## 6. End-to-end plan request trace

| Step | File | Class / function | Input | Output | Deterministic / AI |
|------|------|------------------|-------|--------|--------------------|
| 1 | `desktop/widgets/brief_panel.py` | `BriefPanel._on_generate` | Click | `generate_requested` | UI |
| 2 | `desktop/pages/planner_page.py` | signal relay | — | `generate_brief_requested` | UI |
| 3 | `desktop/views/dashboard_view.py` | signal relay | — | presenter | UI |
| 4 | `desktop/presenters/dashboard_presenter.py` | `generate_range_brief` | range, flags | HTTP via client | Orchestration |
| 5 | `desktop/api_client/backend_client.py` | `generate_range_brief` | JSON body | `POST /briefs/range` | HTTP |
| 6 | `backend/app/api/briefs.py` | `generate_range_brief` | `RangeBriefRequest` | `StudyBriefService` | API |
| 7 | `backend/app/services/study_brief_service.py` | `generate_range_brief` | user + dates | events → AI service | Service |
| 8 | `backend/app/services/ai_recommendation_service.py` | `generate_study_plan` | events, range, now | `(plan, text, ai_mode)` | Hybrid gate |
| 9a | `backend/app/services/study_scheduling_engine.py` | `StudySchedulingEngine.build` | events, now, seed, anchor | Full `StructuredStudyPlan` | **Deterministic** |
| 9b | `OllamaGateway` + `_polish_with_ollama` | optional | skeleton JSON | merged content | **AI** (if available) |
| 10 | `BriefResponse` | includes `plan`, `ai_mode` | — | desktop | API |
| 11 | `desktop/.../brief_panel.py` | `set_brief` | plan dict | timeline cards | UI |

---

## 7. Deterministic engine versus AI responsibilities

### A. Deterministic (`StudySchedulingEngine`)

- Day window 09:00–21:30; today starts at planning anchor / now  
- Free-slot subtraction for calendar events + buffers  
- Exam lifecycle / hard deadlines / post-exam recovery  
- Meals, breaks, daily budgets, stage keys, fixed calendar blocks in timeline  
- `start_time` / `end_time` / `date` / `kind` / titles for calendar & study blocks  

### B. LLM contribution (when `ai_mode=ollama`)

- Rewording: `summary`, `tips`, `priority_item.reason`  
- Study item `action` / `reason` text only (`_merge_content`)  
- Instructed **not** to change times, kind, title, order  

### C. Fallback (`ai_mode=rule_based_fallback`)

- Entire visible schedule + stage wording from the engine  
- No model call when `OLLAMA_MODEL` empty, Ollama down, model missing, or polish fails  

---

## 8. Fallback behavior

```
engine.build(...) → always
if not force_fallback and ollama.is_available():
    try polish → ai_mode = "ollama"
    except → keep engine plan, log warning
else:
    ai_mode = "rule_based_fallback"
```

`is_available()` is **False** when model string is empty — current configuration on this machine.

---

## 9. Original requirement evidence

No separate lecturer PDF/assignment file was found in the repo. Evidence is taken from project planning docs (not from `REQUIREMENTS_COMPLIANCE.md`).

| Item | Classification | Source | Short paraphrase |
|------|----------------|--------|------------------|
| Ollama | Mentioned as later / deferred for MVP; listed under later phase | `docs/PRD.md` Overview + “Later phase”; stack “LLM (later)”; `docs/PIV_PLAN.md` Deferred; `docs/VALIDATION.md` #11 stub | Ollama was planned after the calendar/Telegram demo, not required for the initial MVP demo table |
| LangChain | Mentioned together with Chroma RAG as later phase | `docs/PRD.md` Later phase; `docs/PIV_PLAN.md` Deferred “Ollama + LangChain + Chroma RAG”; `docs/VALIDATION.md` #12 deferred | LangChain appears as part of deferred RAG/AI work |
| RAG / Chroma | Explicitly out of scope for MVP sprint; deferred | `docs/PRD.md` Out of scope + Later phase; `docs/ARCHITECTURE.md` rag deferred; `VALIDATION.md` #12 | Full document RAG not required for the pivot MVP |
| Local LLM | Same as Ollama later phase | PRD stack | Docker Ollama via gateway later |
| CQRS / Event Sourcing / Cursor Skill | Mentioned in PRD success criteria / VALIDATION | `docs/PRD.md`, `docs/VALIDATION.md` | Course-pattern items in project docs — separate from this AI audit |

**Original external assignment file:** not available in repository → do not invent lecturer wording beyond these project docs.

---

## 10. Missing prerequisites

1. Running Ollama on `OLLAMA_BASE_URL` (default `http://localhost:11434`)  
2. Non-empty `OLLAMA_MODEL` matching a pulled model tag  
3. For RAG (future): document pipeline, embeddings, vector store, retrieval — none exist today  
4. Docs still describe older “stub/later” wording in places while code already has a real polish path — documentation drift only  

---

## 11. Safe next steps (guidance only — not executed)

1. Start Ollama; set `OLLAMA_MODEL` to an already-pulled model; confirm `GET /api/tags`  
2. Create a study plan and confirm response `ai_mode` is `"ollama"` without logging private prompt bodies  
3. Keep treating RAG as greenfield until an ingestion→retrieve→augment path exists  
4. Optionally update stale VALIDATION/PRD “stub” rows to match the hybrid engine+polish design  

---

## Files inspected (primary)

- `backend/requirements.txt`, `desktop/requirements.txt`  
- `backend/app/gateways/ollama_gateway.py`  
- `backend/app/services/ai_recommendation_service.py`  
- `backend/app/services/study_brief_service.py`  
- `backend/app/services/study_scheduling_engine.py` (role only; not re-audited line-by-line)  
- `backend/app/config.py`, `.env.example`  
- `backend/app/api/briefs.py`, `backend/app/schemas/brief_schema.py`  
- `backend/app/rag/__init__.py`, `backend/database/schema.sql`  
- `desktop/widgets/brief_panel.py`, `desktop/presenters/dashboard_presenter.py`, `desktop/api_client/backend_client.py`  
- `docs/PRD.md`, `docs/PIV_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/VALIDATION.md`  
- Safe probes: package importability, `OllamaGateway.is_available` / `list_models`, `http://127.0.0.1:11434/api/tags`
