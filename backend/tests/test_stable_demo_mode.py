"""Stable demo mode: AI_POLISH_ENABLED=false → deterministic, no warnings."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.config import settings
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.ai_recommendation_service import AiRecommendationService
from app.services.study_scheduling_engine import StudySchedulingEngine


def _evt(title, cat, start, hours=1.0, desc=None):
    return ClassifiedCalendarEvent(
        id=title,
        title=title,
        category=cat,
        start=start,
        end=start + timedelta(hours=hours),
        description=desc,
    )


def test_polish_disabled_is_deterministic_and_fast(monkeypatch):
    monkeypatch.setattr(settings, "ai_polish_enabled", False)
    monkeypatch.setattr(settings, "skip_ollama_polish", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, day.replace(hour=9), 2),
        _evt("Project", EventCategory.PROJECT, day.replace(hour=14), 1, desc="A"),
    ]
    ollama = MagicMock()
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())
    t0 = time.perf_counter()
    plan, _, mode, warnings = svc.generate_study_plan(
        events, start=day.date(), end=day.date(), now=now
    )
    assert time.perf_counter() - t0 < 2.0
    assert mode == "deterministic"
    assert warnings == []
    assert svc.last_fallback_reason is None
    assert svc.last_ollama_called is False
    assert plan.daily_plan
    assert sum(len(d.items) for d in plan.daily_plan) > 0
    ollama.invoke.assert_not_called()


def test_polish_enabled_timeout_keeps_plan_without_ui_warning(monkeypatch):
    from app.gateways.ollama_gateway import OllamaTimeoutError

    monkeypatch.setattr(settings, "ai_polish_enabled", True)
    monkeypatch.setattr(settings, "skip_ollama_polish", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, day.replace(hour=9), 2),
        _evt("Next", EventCategory.EXAM, day + timedelta(days=5), desc="Topic"),
    ]
    ollama = MagicMock()
    ollama.is_available.return_value = True
    ollama.model = "llama3.2"
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())
    svc._polish_with_ollama = MagicMock(  # type: ignore[method-assign]
        side_effect=OllamaTimeoutError("timed out")
    )
    plan, _, mode, warnings = svc.generate_study_plan(
        events, start=day.date(), end=day.date(), now=now
    )
    assert mode == "rule_based_fallback"
    assert warnings == []
    assert svc.last_fallback_reason == "timeout"
    assert svc.last_ollama_called is True
    assert plan.daily_plan
