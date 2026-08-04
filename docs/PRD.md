# Product Requirements Document (PRD)

## Product name

**AI Calendar Study Assistant**

*(Repository folder remains `ai-study-planner` — reuse existing codebase, no restart.)*

## Overview

AI Calendar Study Assistant is a PySide6 desktop application for students. It reads academic events from **Google Calendar**, classifies them into study-related categories, generates a **daily or weekly study brief**, and sends the brief through **Telegram**. Supabase stores user profiles, synced event metadata, brief history, and an activity log.

The original “full study planner with RAG documents” scope is **deferred**. AI/Ollama remains a **small later phase** with a placeholder service interface only.

## Target user

University/college students who:

- Already use Google Calendar for classes, exams, and study blocks
- Want an automated summary of what to focus on today or this week
- Prefer receiving the brief on Telegram without opening the desktop app daily

## Problem

Calendar apps list events but do not **interpret** them for study planning. Students manually scan titles to decide priorities. There is no automated brief that groups exams, assignments, and study sessions into actionable output.

## Solution

Reuse the existing **FastAPI + PySide6 + Supabase** architecture:

- **Google Calendar Gateway** fetches events from the student’s calendar
- **Classification service** parses event titles by prefix (`Study:`, `Assignment:`, etc.)
- **Brief service** builds Today and Weekly study briefs from classified events
- **Telegram Gateway** delivers the brief
- **Desktop dashboard** drives the demo flow with clear status/errors
- **Supabase** persists profiles, optional synced data, chat/brief history, and `activity_events` (MVP Event Sourcing)

## Google Calendar event format

Event titles use a **prefix** before a colon:

| Prefix | Example title | Meaning |
|--------|---------------|---------|
| `Study` | `Study: Database Systems project` | Dedicated study block |
| `Assignment` | `Assignment: Algorithms exercise` | Homework / submission |
| `Exam` | `Exam: Operating Systems` | Test or exam |
| `Class` | `Class: Software Engineering` | Lecture / seminar |
| `Project` | `Project: AI Study Planner` | Project milestone |
| `Other` | *(no recognized prefix)* | Uncategorized |

Backend classifies every synced event into one of these categories.

## MVP features (demo by Thursday evening)

| # | Feature | Description |
|---|---------|-------------|
| 1 | Demo user flow | Load demo student from Supabase (`users_profile`) |
| 2 | Google Calendar sync | Backend Gateway fetches events; desktop triggers sync |
| 3 | Event classification | Prefix-based parser assigns category |
| 4 | Today Study Brief | Text summary of today’s classified events |
| 5 | Weekly Study Brief | Text summary for the current week |
| 6 | Telegram delivery | Send generated brief to student’s Telegram chat |
| 7 | Dashboard | Buttons: Load Demo Student, Sync Calendar, Show Today Events, Generate Brief, Send to Telegram; status/error area |
| 8 | Tables | Table of today’s / synced events (type, title, time) |
| 9 | Chart (minimal) | e.g. event count by category (bar/pie) |
| 10 | Activity log | Write sync/brief/send actions to `activity_events` |
| 11 | AI placeholder | `AiRecommendationService` interface stub — no heavy RAG yet |

## Out of scope (this sprint)

- Full user registration/auth (demo user is enough for MVP)
- Database schema changes
- Document upload and Chroma RAG pipeline
- Full AI chat UI
- Mobile app
- Multi-calendar / shared calendars

## Later phase (post-demo)

- Ollama Gateway + lightweight recommendations on top of brief text
- LangChain + Chroma for study document RAG (reuse existing `rag/` package)
- Supabase Auth and RLS policies
- Persist synced events in dedicated table (if schema extended)

## Success criteria

- Demo student loads; calendar sync returns classified events
- Today brief generates from real or seeded calendar data
- Brief sends successfully to Telegram
- Dashboard shows clear success/error states
- Course patterns visible: PySide6 MVP, FastAPI CQRS, Supabase, Gateways, external integration, PIV docs, Cursor artifacts

## Technology stack

| Layer | Technology |
|-------|------------|
| Desktop UI | PySide6 6.5+ (MVP) |
| API | FastAPI |
| Database | Supabase (existing tables) |
| Calendar | Google Calendar API via `GoogleCalendarGateway` |
| Messaging | Telegram Bot via `TelegramGateway` |
| LLM (later) | Ollama (Docker) via `OllamaGateway` |
| Event log | `activity_events` table (MVP Event Sourcing) |
| Dev process | PIV |
| AI assistant | Cursor |

## Existing Supabase tables (unchanged for now)

| Table | Use in pivot |
|-------|----------------|
| `users_profile` | Demo student, `telegram_chat_id` |
| `courses` | Optional grouping (reuse if needed) |
| `tasks` | Optional manual tasks (lower priority) |
| `study_documents` | Deferred (RAG later) |
| `ai_chat_history` | Store brief text or future AI Q&A |
| `activity_events` | Log sync, brief generated, Telegram sent |
