"""RAG topics enrich study-plan actions without changing schedule geometry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.ai_recommendation_service import AiRecommendationService
from app.services.study_scheduling_engine import StudySchedulingEngine


class _FakeRag:
    def topics_for_events(self, events):
        out = {}
        for event in events:
            if str(getattr(event.category, "value", event.category)).lower() == "exam":
                out[event.id] = ["Processes", "Threads", "Synchronization", "Deadlocks"]
        return out

    def has_indexed_material(self) -> bool:
        return True


class _FakeRagCourseKeyOnly:
    """Topics keyed only by course:… — simulates id-mismatch between retrieve and schedule."""

    def topics_for_events(self, events):
        from app.rag.document_matcher import course_lookup_key

        out = {}
        for event in events:
            if str(getattr(event.category, "value", event.category)).lower() == "exam":
                out[course_lookup_key(event.title)] = [
                    "Deadlocks",
                    "Virtual Memory",
                    "Paging",
                    "Scheduling",
                    "Threads",
                ]
        return out

    def has_indexed_material(self) -> bool:
        return True


def test_engine_uses_rag_topics_in_actions():
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    exam = ClassifiedCalendarEvent(
        id="e1",
        title="Operating Systems",
        category=EventCategory.EXAM,
        start=now + timedelta(days=5),
        end=now + timedelta(days=5, hours=2),
    )
    plan = StudySchedulingEngine().build(
        [exam],
        range_start=now.date(),
        range_end=(now + timedelta(days=2)).date(),
        now=now,
        language="en",
        rag_topics={"e1": ["Processes", "Threads", "Synchronization"]},
    )
    actions = [
        item.action
        for day in plan.daily_plan
        for item in day.items
        if (item.kind or "") == "study" and item.action
    ]
    assert actions
    assert any(
        any(t.lower() in (a or "").lower() for t in ("processes", "threads", "synchronization"))
        for a in actions
    )
    # Still timed blocks — geometry owned by the engine.
    assert any(item.start_time and item.end_time for day in plan.daily_plan for item in day.items)


def test_ai_service_applies_rag_before_engine(monkeypatch):
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    exam = ClassifiedCalendarEvent(
        id="e1",
        title="Operating Systems",
        category=EventCategory.EXAM,
        start=now + timedelta(days=4),
        end=now + timedelta(days=4, hours=2),
    )
    service = AiRecommendationService(rag=_FakeRag())  # type: ignore[arg-type]
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "ai_polish_enabled", False)
    monkeypatch.setattr(app_settings, "skip_ollama_polish", False)

    plan, text, ai_mode, _warnings = service.generate_study_plan(
        [exam],
        start=now.date(),
        end=(now + timedelta(days=1)).date(),
        now=now,
        force_fallback=True,
    )
    assert ai_mode in {"deterministic", "rule_based_fallback"}
    assert service.last_rag_used is True
    assert service.last_rag_topic_count >= 1
    assert any(
        "Processes" in (item.action or "")
        or "Threads" in (item.action or "")
        or "Synchronization" in (item.action or "")
        or "Deadlocks" in (item.action or "")
        for day in plan.daily_plan
        for item in day.items
    )
    # Telegram formatter consumes the same plan actions via format_plan_text.
    assert "Operating Systems" in text or "Processes" in text or "Threads" in text


def test_course_key_topics_appear_in_study_actions(monkeypatch):
    """Even without event-id keys, OS exam plan must list retrieved topics."""
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    exam = ClassifiedCalendarEvent(
        id="exam-os-1",
        title="Operating Systems Exam",
        category=EventCategory.EXAM,
        start=now + timedelta(days=5),
        end=now + timedelta(days=5, hours=2),
    )
    service = AiRecommendationService(rag=_FakeRagCourseKeyOnly())  # type: ignore[arg-type]
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "ai_polish_enabled", False)
    monkeypatch.setattr(app_settings, "skip_ollama_polish", False)

    plan, _text, _ai_mode, _warnings = service.generate_study_plan(
        [exam],
        start=now.date(),
        end=(now + timedelta(days=2)).date(),
        now=now,
        force_fallback=True,
    )
    actions = [
        item.action or ""
        for day in plan.daily_plan
        for item in day.items
        if (item.kind or "") == "study"
    ]
    joined = " ".join(actions).lower()
    assert service.last_rag_used is True
    assert "deadlock" in joined
    assert "paging" in joined or "virtual memory" in joined or "thread" in joined
    assert not any(
        a.strip().lower() in {"review theory.", "practice questions.", "organize syllabus and review core theory."}
        for a in actions
    ) or any("deadlock" in a.lower() for a in actions)


def test_openapi_exposes_rag_routes():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/rag/upload" in paths
    assert "/rag/ask" in paths
    assert "/rag/status" in paths
    assert "/rag/documents/{document_id}" in paths
    assert "post" in paths["/rag/upload"]
    assert "post" in paths["/rag/ask"]
    assert "delete" in paths["/rag/documents/{document_id}"]
