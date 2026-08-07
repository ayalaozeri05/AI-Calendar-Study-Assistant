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

Study plans are built by a **deterministic scheduling engine** (times, order, kinds). **Ollama runs in Docker** for optional wording polish and a **standalone RAG** path over uploaded PDFs. **Stable demo mode** defaults to `AI_POLISH_ENABLED=false`: plans return immediately with `ai_mode=deterministic` (no Ollama wait, no failure banners). Set `AI_POLISH_ENABLED=true` only for explicit Ollama polish verification. RAG does not depend on polish mode.

## Stack

| Layer | Technology |
|-------|------------|
| Desktop | PySide6 (MVP: views / presenters / models) |
| Backend | FastAPI (services, repositories, CQRS-style layout) |
| Database | Supabase |
| Calendar | Google Calendar API + OAuth (`google-auth-oauthlib`) |
| Messaging | Telegram Bot via `TelegramGateway` |
| AI | Scheduling engine + **Ollama in Docker** (optional polish + RAG) |
| RAG | PDF → chunks → `nomic-embed-text` → Chroma → retrieve → `llama3.2` |

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
| `OLLAMA_BASE_URL` | Docker Ollama on the host (`http://localhost:11434`) |
| `OLLAMA_MODEL` | Chat model (default `llama3.2`) |
| `OLLAMA_EMBED_MODEL` | Embedding model for RAG (default `nomic-embed-text`) |
| `AI_POLISH_ENABLED` | `false` = stable demo (default); `true` = optional Ollama polish |
| `CHROMA_PERSIST_DIR` | Persistent Chroma path (default `backend/chroma`) |
| `RAG_UPLOAD_DIR` | Stored PDF uploads (default `backend/uploads/rag`) |

### Stable demo startup (recommended)

Use **one** backend on **port 8000** only (do not use 8010/8011).

```powershell
# From repository root
docker compose up -d

cd backend
# Ensure shell has no leftover SKIP_OLLAMA_POLISH / AI_POLISH_ENABLED overrides
Remove-Item Env:SKIP_OLLAMA_POLISH -ErrorAction SilentlyContinue
Remove-Item Env:AI_POLISH_ENABLED -ErrorAction SilentlyContinue
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Another terminal
cd desktop
python main.py
```

Confirm stable mode:

```powershell
curl http://127.0.0.1:8000/health
# expect: "ai_polish_enabled": false
```

Create a Study Plan → expect a full plan quickly with `ai_mode=deterministic` and status **"Study plan created"** (no fallback/timeout banners).

**Port 8000 busy?** Check with `netstat -ano | findstr :8000`. Stop the old listener (Task Manager / close the previous uvicorn terminal), then start a single backend again. Do not run multiple uvicorn instances.

### Ollama in Docker (polish + RAG)

Prerequisites: [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

```powershell
docker compose up -d
docker exec -it ai-study-planner-ollama ollama pull llama3.2
docker exec -it ai-study-planner-ollama ollama pull nomic-embed-text
curl http://localhost:11434/api/tags
curl http://127.0.0.1:8000/health/ollama
```

Expected when healthy (includes `ai_polish_enabled`):

```json
{"status":"ok","service":"ollama","reachable":true,"model_configured":"llama3.2","model_available":true,"ai_polish_enabled":false}
```

#### Optional Ollama polish verification (not the default demo)

1. Set `AI_POLISH_ENABLED=true` in `.env` (and clear any process env override).
2. Restart the backend on port 8000.
3. Confirm `GET /health/ollama` → `reachable=true`, `model_available=true`, `ai_polish_enabled=true`.
4. Generate a small plan → when the model finishes, `ai_mode` should be `"ollama"`.
5. Restore `AI_POLISH_ENABLED=false` for the stable demo.

If polish is enabled and Ollama fails/times out, the deterministic plan is still returned (`ai_mode=rule_based_fallback` in meta only; the desktop shows a normal success message).

**Note — synced events are in-memory:** `POST /calendar/sync` stores classified events in the FastAPI process only. A **backend restart clears the event cache**. Sync again after restart.

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

## How RAG works (planner-integrated)

RAG is not a separate chat app. Uploaded PDFs enrich **Create Study Plan**.

```text
Calendar events  +  Uploaded PDF
        ↓
   Retriever (top-k chunks for exam/course title)
        ↓
   Relevant topics (Processes, Threads, …)
        ↓
   Scheduling engine (times, order, workload)
        ↓
   Study Plan actions (Review Processes and Threads, …)
        ↓
   Optional Ollama wording polish (if enabled)
        ↓
   Desktop + Telegram
```

| Stage | Module | Role |
|-------|--------|------|
| Loader | `document_loader.py` | `PyPDFLoader` extracts page text |
| Chunking | `text_splitter.py` | ~800 chars, ~120 overlap |
| Embeddings | `embedding_service.py` | Ollama `nomic-embed-text` |
| Vector store | `vector_store.py` | Persistent Chroma (`backend/chroma/`) |
| Retriever | `retriever.py` | Top-k=4 for the upcoming event query |
| Planner use | `AiRecommendationService` | Passes retrieved topics into the scheduling engine |
| Optional polish | `OllamaGateway` | Wording only — never changes times/order |

Without a PDF, the planner behaves exactly as before.

**Endpoints** (visible in Swagger `/docs`, tag **rag**)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/rag/upload` | multipart: PDF + `title` → index chunks |
| `GET` | `/rag/status` | whether a study PDF is indexed |
| `POST` | `/rag/ask` | optional debug Q&A over indexed material |

**Desktop:** Planner → compact **Study Material** → Upload PDF → `OperatingSystems.pdf ✓`. Then Create Study Plan uses it silently.

**Demo RAG**

```powershell
docker compose up -d
docker exec -it ai-study-planner-ollama ollama pull nomic-embed-text
docker exec -it ai-study-planner-ollama ollama pull llama3.2
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# Desktop: Planner → Upload PDF → Create Study Plan
# Or Swagger: http://127.0.0.1:8000/docs → POST /rag/upload
```

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
| http://127.0.0.1:8000/health/ollama | Docker Ollama reachability + model |
| http://127.0.0.1:8000/rag/upload | Upload study PDF (multipart) |
| http://127.0.0.1:8000/rag/status | Current indexed study material |
| http://127.0.0.1:8000/rag/ask | Debug Q&A over indexed material |
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
5. Optional: **Upload PDF** under Study Material (enriches plan topics)
6. Create the matching plan, then **Send to Telegram**
7. Use **Sync calendar** or **← Calendar** anytime

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
| [Requirements compliance](docs/REQUIREMENTS_COMPLIANCE.md) | Honest Complete / Partial / Not implemented matrix |
| [secrets/README.md](secrets/README.md) | Where to place Google OAuth client JSON |

### Cursor Agent Skill

Project skill (discoverable `SKILL.md`):

[`.cursor/skills/ai-study-planner-validator/SKILL.md`](.cursor/skills/ai-study-planner-validator/SKILL.md)

In Cursor chat, ask e.g. **“Run the AI Study Planner Validator skill”** for a safe pre-demo check (no Telegram send, no secret printing).

Legacy markdown under `skills/` is documentation only — not a Cursor Agent Skill.
