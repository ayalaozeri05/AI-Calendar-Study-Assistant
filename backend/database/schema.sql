-- AI Study Planner — Supabase / PostgreSQL schema
--
-- Apply manually in the Supabase SQL Editor when ready (not wired in app yet).
-- Uses gen_random_uuid() (built into PostgreSQL 13+, default on Supabase).
-- Timestamps use timestamptz with UTC default.

-- ---------------------------------------------------------------------------
-- users_profile
-- Extended profile for each student. id is intended to match auth.users.id
-- once Supabase Auth is connected in a later iteration.
-- ---------------------------------------------------------------------------
CREATE TABLE users_profile (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    full_name       TEXT,
    telegram_chat_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE users_profile IS
    'Student profile: identity, display name, and Telegram chat id for daily briefs.';

COMMENT ON COLUMN users_profile.telegram_chat_id IS
    'Telegram chat id used by TelegramGateway to send the daily study brief.';

-- ---------------------------------------------------------------------------
-- courses
-- Academic courses owned by a user. Tasks and documents may optionally link here.
-- ---------------------------------------------------------------------------
CREATE TABLE courses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users_profile (id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT,
    color           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE courses IS
    'Courses created by a student; groups tasks and study documents.';

COMMENT ON COLUMN courses.color IS
    'Optional UI color token (e.g. hex) for charts and course badges in the desktop app.';

CREATE INDEX idx_courses_user_id ON courses (user_id);

-- ---------------------------------------------------------------------------
-- tasks
-- Academic tasks with deadlines, effort estimates, and priority for recommendations.
-- ---------------------------------------------------------------------------
CREATE TABLE tasks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users_profile (id) ON DELETE CASCADE,
    course_id           UUID REFERENCES courses (id) ON DELETE SET NULL,
    title               TEXT NOT NULL,
    description         TEXT,
    due_date            TIMESTAMPTZ,
    estimated_minutes   INTEGER,
    difficulty          INTEGER,
    status              TEXT,
    priority_score      INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE tasks IS
    'Study tasks and assignments; drives dashboard urgency, recommendations, and Telegram briefs.';

COMMENT ON COLUMN tasks.status IS
    'Workflow label, e.g. pending, in_progress, completed, postponed.';

COMMENT ON COLUMN tasks.difficulty IS
    'Relative difficulty scale (e.g. 1–5); used by recommendation logic.';

COMMENT ON COLUMN tasks.priority_score IS
    'Computed or manual priority for ordering what to study today.';

CREATE INDEX idx_tasks_user_id ON tasks (user_id);
CREATE INDEX idx_tasks_course_id ON tasks (course_id);
CREATE INDEX idx_tasks_due_date ON tasks (due_date);
CREATE INDEX idx_tasks_status ON tasks (status);

-- ---------------------------------------------------------------------------
-- study_documents
-- Metadata for uploaded study files. File bytes live in storage; vectors in Chroma.
-- ---------------------------------------------------------------------------
CREATE TABLE study_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users_profile (id) ON DELETE CASCADE,
    course_id       UUID REFERENCES courses (id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    file_name       TEXT,
    file_path       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE study_documents IS
    'Metadata for study materials; file_path points to Supabase Storage or local path; RAG embeddings stay in ChromaDB.';

CREATE INDEX idx_study_documents_user_id ON study_documents (user_id);
CREATE INDEX idx_study_documents_course_id ON study_documents (course_id);

-- ---------------------------------------------------------------------------
-- ai_chat_history
-- Persisted Q&A from the AI study agent for review and audit.
-- ---------------------------------------------------------------------------
CREATE TABLE ai_chat_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users_profile (id) ON DELETE CASCADE,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ai_chat_history IS
    'History of student questions and AI answers from the RAG-backed chat agent.';

CREATE INDEX idx_ai_chat_history_user_id ON ai_chat_history (user_id);
CREATE INDEX idx_ai_chat_history_created_at ON ai_chat_history (created_at DESC);

-- ---------------------------------------------------------------------------
-- activity_events
-- Append-only event log for a simple MVP Event Sourcing pattern: record what
-- happened (created, updated, completed) without replaying full domain state.
-- ---------------------------------------------------------------------------
CREATE TABLE activity_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users_profile (id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,
    entity_type     TEXT,
    entity_id       UUID,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE activity_events IS
    'Append-only activity log (MVP Event Sourcing): task created, document uploaded, AI query, etc.';

COMMENT ON COLUMN activity_events.event_type IS
    'Action name, e.g. task_created, task_completed, document_uploaded, ai_question_asked.';

COMMENT ON COLUMN activity_events.entity_type IS
    'Related entity kind: course, task, study_document, etc.';

COMMENT ON COLUMN activity_events.entity_id IS
    'Optional UUID of the related row; polymorphic (no single FK) because entity_type varies.';

CREATE INDEX idx_activity_events_user_id ON activity_events (user_id);
CREATE INDEX idx_activity_events_created_at ON activity_events (created_at DESC);
CREATE INDEX idx_activity_events_entity ON activity_events (entity_type, entity_id);

-- ---------------------------------------------------------------------------
-- updated_at helper for tasks
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
