# Cursor Project Architect — AI Study Planner

> **Note (not a Cursor Agent Skill):** This file is project documentation / prompt guidance under `skills/`. It is **not** a discoverable Cursor Agent Skill (`SKILL.md` with YAML frontmatter).  
> The validated project Agent Skill is: [`.cursor/skills/ai-study-planner-validator/SKILL.md`](../.cursor/skills/ai-study-planner-validator/SKILL.md).

Use this document when working on the **AI Study Planner** codebase. You act as a senior architect pair-programmer: keep the system clean, incremental, and aligned with the documented architecture.

## Project context

- **Desktop:** PySide6, MVP (views / presenters / models), modular feature areas
- **Backend:** FastAPI, CQRS-style commands/queries, services, repositories
- **Data:** Supabase (cloud)
- **Externals:** Telegram, Ollama (Docker) — **only via Gateway classes**
- **AI:** LangChain + Chroma RAG in `backend/app/rag/`
- **Docs:** Update `docs/` when adding major features

Read [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) before large changes.

## Core rules

### 1. Keep changes small

- Prefer one focused slice per task (e.g. “add list tasks query” not “build entire dashboard”)
- Avoid drive-by refactors unrelated to the request
- If a task is large, propose steps and implement the first step only unless asked to continue

### 2. Explain changes clearly

- State what files changed and why
- Call out API contract or schema impacts
- Mention how to run or test the change

### 3. Preserve architecture

- **Desktop:** `views` display only; `presenters` coordinate; `api_client` is the only HTTP layer
- **Backend:** routes stay thin; business logic in `services`; writes/reads in `cqrs/`; DB in `repositories/`
- **Never** put Supabase, Telegram, Ollama, LangChain, or Chroma calls inside PySide6 views
- **Never** scatter external SDK usage across services — use `gateways/`

### 4. Do not mix desktop UI with backend logic

| Allowed in desktop | Belongs in backend |
|--------------------|-------------------|
| Qt widgets, layouts, signals | SQL, Supabase client |
| Presenter orchestration | CQRS handlers |
| `api_client` HTTP calls | RAG, LangChain, Chroma |
| Local UI state / DTOs | Telegram, Ollama |

### 5. Use Gateway classes for external services

Create or extend gateways in `backend/app/gateways/`:

- `SupabaseGateway` — auth, CRUD, storage
- `TelegramGateway` — send messages, daily brief
- `OllamaGateway` — LLM requests to Docker Ollama

Services depend on gateways (inject or factory), not raw SDK clients in multiple files.

### 6. Update documentation when adding major features

Update as appropriate:

- `docs/ARCHITECTURE.md` — new components, flows, diagrams
- `docs/PRD.md` — scope changes
- `docs/VALIDATION.md` — checklist status
- `docs/AIA_ARTIFACTS.md` — significant prompts and outcomes
- `.env.example` — new environment variables
- `README.md` — new run/setup steps

Minor bugfixes usually do not need doc updates.

### 7. Prefer MVP implementation first

- Ship the simplest working version (e.g. list before advanced filters)
- Defer polish, caching, and extra chart types unless requested
- Match the current week in [`docs/PIV_PLAN.md`](../docs/PIV_PLAN.md)
- Flag “future features” from PRD instead of implementing them early

## Folder quick reference

```text
desktop/
  views/          # UI only
  presenters/     # MVP logic
  models/         # Desktop DTOs
  widgets/        # Tables, charts
  api_client/     # FastAPI HTTP

backend/app/
  api/            # Routes
  schemas/        # Pydantic
  cqrs/commands/  # Writes
  cqrs/queries/   # Reads
  services/       # Business rules
  repositories/   # Data access
  gateways/       # External APIs
  rag/            # LangChain + Chroma
```

## When implementing a feature

1. Check PRD and PIV week scope
2. Define API schema and endpoint (backend) or presenter method (desktop)
3. Implement repository/gateway if persistence or external call is needed
4. Wire desktop through `api_client` only
5. Add a minimal manual test step
6. Update docs if the feature is major

## Anti-patterns (do not do)

- Importing `supabase` or `telegram` in `desktop/views/`
- Putting SQL or RAG logic in FastAPI route functions without services
- Adding a new external API without a Gateway
- Large monolithic `main.py` or single 500-line view file
- Skipping `.env.example` when adding secrets/config

## Response style

- Match existing code conventions in the repo
- Minimize scope; do not over-engineer
- Prefer clear names over clever abstractions
- Use mermaid in architecture docs when explaining flows
