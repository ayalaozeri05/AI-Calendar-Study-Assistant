"""Regression: plan generation must not hang ~5 minutes then return empty."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.gateways.ollama_gateway import OllamaTimeoutError
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.ai_recommendation_service import AiRecommendationService
from app.services.study_scheduling_engine import (
    StudySchedulingEngine,
    _Placed,
    _blocks_fingerprint,
    _normalize_day_timeline,
)


def _evt(title, cat, start, hours=1.0, desc=None):
    return ClassifiedCalendarEvent(
        id=title,
        title=title,
        category=cat,
        start=start,
        end=start + timedelta(hours=hours),
        description=desc,
    )


def test_normalization_completes_within_strict_time_limit():
    now = datetime(2026, 8, 7, 8, 0, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, datetime(2026, 8, 11, 9, tzinfo=timezone.utc), 2),
        _evt(
            "Dance",
            EventCategory.CLASS,
            datetime(2026, 8, 11, 16, 30, tzinfo=timezone.utc),
            1.5,
        ),
        _evt(
            "Next",
            EventCategory.EXAM,
            datetime(2026, 8, 18, 10, tzinfo=timezone.utc),
            desc="A\nB\nC\nD",
        ),
    ]
    t0 = time.perf_counter()
    plan = StudySchedulingEngine().build(
        events,
        range_start=now.date(),
        range_end=(now + timedelta(days=14)).date(),
        now=now,
        language="en",
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"deterministic+normalize too slow: {elapsed:.3f}s"
    assert plan.daily_plan
    assert sum(len(d.items) for d in plan.daily_plan) > 0


def test_repeated_fingerprint_stops_normalize_passes():
    tz = timezone.utc
    day = datetime(2026, 8, 11, tzinfo=tz).date()
    now = datetime(2026, 8, 11, 8, 0, tzinfo=tz)
    blocks = [
        _Placed(
            start=datetime(2026, 8, 11, 11, 0, tzinfo=tz),
            end=datetime(2026, 8, 11, 12, 15, tzinfo=tz),
            kind="recovery",
            title="Recovery",
            action="x",
            reason="",
        ),
        _Placed(
            start=datetime(2026, 8, 11, 12, 15, tzinfo=tz),
            end=datetime(2026, 8, 11, 13, 15, tzinfo=tz),
            kind="meal",
            title="Lunch",
            action="y",
            reason="",
        ),
    ]
    out = _normalize_day_timeline(
        blocks,
        day=day,
        now=now,
        hebrew=False,
        remaining_workload_min=0,
        demand=[],
        seed=1,
    )
    # Stable input should not explode
    assert len(out) <= 5
    assert _blocks_fingerprint(out)


def test_ollama_timeout_returns_deterministic_plan(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ai_polish_enabled", True)
    monkeypatch.setattr(settings, "skip_ollama_polish", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, day.replace(hour=9), 2),
        _evt("Next", EventCategory.EXAM, day + timedelta(days=5), desc="Topic"),
    ]
    engine_plan = StudySchedulingEngine().build(
        events,
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    ollama = MagicMock()
    ollama.is_available.return_value = True
    ollama.model = "llama3.2"
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())
    svc._polish_with_ollama = MagicMock(  # type: ignore[method-assign]
        side_effect=OllamaTimeoutError("timed out")
    )
    plan, text, mode, warnings = svc.generate_study_plan(
        events,
        start=day.date(),
        end=day.date(),
        now=now,
    )
    assert mode == "rule_based_fallback"
    assert plan.daily_plan
    assert sum(len(d.items) for d in plan.daily_plan) > 0
    assert text
    assert warnings == []
    assert svc.last_fallback_reason == "timeout"
    # Geometry matches a fresh deterministic build for the same seed defaults
    assert len(plan.daily_plan[0].items) == len(engine_plan.daily_plan[0].items)


def test_malformed_ollama_keeps_deterministic_plan(monkeypatch):
    from app.config import settings

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
    ollama.invoke.side_effect = ["not-json", "still-not-json"]
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())
    plan, _, mode, _ = svc.generate_study_plan(
        events,
        start=day.date(),
        end=day.date(),
        now=now,
    )
    assert mode == "rule_based_fallback"
    assert plan.daily_plan
    assert sum(len(d.items) for d in plan.daily_plan) > 0


def test_ai_polish_disabled_returns_deterministic(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ai_polish_enabled", False)
    monkeypatch.setattr(settings, "skip_ollama_polish", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, day.replace(hour=9), 2),
        _evt("Next", EventCategory.EXAM, day + timedelta(days=5), desc="Topic"),
    ]
    ollama = MagicMock()
    ollama.is_available.return_value = True
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())
    t0 = time.perf_counter()
    plan, _, mode, warnings = svc.generate_study_plan(
        events,
        start=day.date(),
        end=day.date(),
        now=now,
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0
    assert mode == "deterministic"
    assert warnings == []
    assert svc.last_fallback_reason is None
    assert plan.daily_plan
    ollama.invoke.assert_not_called()
    ollama.is_available.assert_not_called()
