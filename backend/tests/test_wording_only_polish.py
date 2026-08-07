"""Wording-only Ollama polish: no schedule geometry in the prompt."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.config import settings
from app.schemas.brief_schema import StructuredStudyPlan
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.ai_recommendation_service import (
    AiRecommendationService,
    _apply_wording_bundle,
    _build_wording_polish_prompt,
    _extract_wording_bundle,
)
from app.services.study_scheduling_engine import StudySchedulingEngine


def test_wording_bundle_excludes_times_and_dates():
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)
    events = [
        ClassifiedCalendarEvent(
            id="p1",
            title="Tiny Capstone",
            category=EventCategory.PROJECT,
            start=day,
            end=day + timedelta(hours=1),
            description="Milestone A",
        )
    ]
    plan = StudySchedulingEngine().build(
        events,
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    bundle, slot_map = _extract_wording_bundle(plan)
    blob = str(bundle)
    assert "start_time" not in blob
    assert "end_time" not in blob
    assert "2026-08-11" not in blob
    assert "items" in bundle
    assert slot_map
    prompt = _build_wording_polish_prompt(bundle, language="en", regenerate=False)
    assert "start_time" not in prompt
    assert "calendar" not in prompt.lower() or "Do not invent a schedule" in prompt
    assert len(prompt) < 2500


def test_apply_wording_preserves_geometry():
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)
    events = [
        ClassifiedCalendarEvent(
            id="p1",
            title="Tiny Capstone",
            category=EventCategory.PROJECT,
            start=day,
            end=day + timedelta(hours=1),
            description="Milestone A",
        )
    ]
    plan = StudySchedulingEngine().build(
        events,
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    before = [
        (d.date, i.start_time, i.end_time, i.kind, i.title)
        for d in plan.daily_plan
        for i in d.items
    ]
    bundle, slot_map = _extract_wording_bundle(plan)
    polished = {
        "summary": "Polished summary",
        "priority_reason": "Polished priority",
        "tips": ["Polished tip"],
        "items": [
            {"action": f"Action {n}", "reason": f"Reason {n}"}
            for n in range(len(bundle["items"]))
        ],
    }
    out = _apply_wording_bundle(plan, polished, slot_map)
    after = [
        (d.date, i.start_time, i.end_time, i.kind, i.title)
        for d in out.daily_plan
        for i in d.items
    ]
    assert before == after
    assert out.summary == "Polished summary"


def test_fast_mock_ollama_wording_path(monkeypatch):
    monkeypatch.setattr(settings, "ai_polish_enabled", True)
    monkeypatch.setattr(settings, "skip_ollama_polish", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)
    events = [
        ClassifiedCalendarEvent(
            id="p1",
            title="Tiny Capstone",
            category=EventCategory.PROJECT,
            start=day,
            end=day + timedelta(hours=1),
            description="Milestone A",
        )
    ]
    ollama = MagicMock()
    ollama.is_available.return_value = True
    ollama.model = "llama3.2"
    ollama.invoke.return_value = (
        '{"summary":"S","priority_reason":"R","tips":["T"],'
        '"items":[{"action":"Do the milestone","reason":"Deadline soon"}]}'
    )
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())
    plan, _, mode, _ = svc.generate_study_plan(
        events, start=day.date(), end=day.date(), now=now
    )
    assert mode == "ollama"
    assert isinstance(plan, StructuredStudyPlan)
    assert plan.summary == "S"
    # Prompt must be wording-only (no full schedule dump).
    sent = ollama.invoke.call_args.args[0]
    assert "Draft JSON:" in sent
    assert "start_time" not in sent
