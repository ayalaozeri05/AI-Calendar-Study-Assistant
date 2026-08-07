"""Deterministic scheduling engine tests."""

from datetime import datetime, timedelta, timezone

from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.ai_recommendation_service import AiRecommendationService
from app.services.study_scheduling_engine import StudySchedulingEngine, plan_fingerprint


def _evt(
    title: str,
    category: EventCategory,
    start: datetime,
    *,
    hours: float = 1.0,
    description: str | None = None,
    location: str | None = None,
) -> ClassifiedCalendarEvent:
    return ClassifiedCalendarEvent(
        id=f"{title}-{start.isoformat()}",
        title=title,
        category=category,
        start=start,
        end=start + timedelta(hours=hours),
        description=description,
        location=location,
    )


def test_today_starts_after_now_boundary():
    now = datetime(2026, 8, 5, 16, 10, tzinfo=timezone.utc)
    events = [
        _evt(
            "OS Exam",
            EventCategory.EXAM,
            now + timedelta(days=3),
            description="Virtual Memory\nThreads",
        )
    ]
    plan = StudySchedulingEngine().build(
        events,
        range_start=now.date(),
        range_end=now.date() + timedelta(days=3),
        now=now,
        language="en",
    )
    # 16:10 → ceil 15-min → 16:15
    assert plan.planning_anchor
    assert datetime.fromisoformat(plan.planning_anchor).strftime("%H:%M") == "16:15"
    today = next((d for d in plan.daily_plan if d.date == now.date().isoformat()), None)
    assert today
    for item in today.items:
        if item.start_time:
            h, m = map(int, item.start_time.split(":"))
            assert h * 60 + m >= 16 * 60 + 15


def test_future_day_starts_morning():
    now = datetime(2026, 8, 5, 16, 10, tzinfo=timezone.utc)
    events = [
        _evt("OS Exam", EventCategory.EXAM, now + timedelta(days=5), description="Threads")
    ]
    plan = StudySchedulingEngine().build(
        events,
        range_start=now.date(),
        range_end=now.date() + timedelta(days=4),
        now=now,
        language="en",
        variation_seed=0,
    )
    future_days = [d for d in plan.daily_plan if d.date > now.date().isoformat()]
    assert future_days
    first_study = next(
        i for i in future_days[0].items if (i.kind or "study") == "study"
    )
    assert first_study.start_time == "09:00"


def test_future_day_has_multiple_long_blocks():
    now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
    events = [
        _evt(
            "OS Exam",
            EventCategory.EXAM,
            now + timedelta(days=4),
            description="Scheduling\nThreads\nVirtual Memory",
        )
    ]
    plan = StudySchedulingEngine().build(
        events,
        range_start=now.date() + timedelta(days=1),
        range_end=now.date() + timedelta(days=3),
        now=now,
        language="en",
    )
    day = plan.daily_plan[0]
    study = [i for i in day.items if (i.kind or "study") == "study"]
    assert len(study) >= 2
    mins = []
    for item in study:
        h1, m1 = map(int, item.start_time.split(":"))
        h2, m2 = map(int, item.end_time.split(":"))
        mins.append((h2 * 60 + m2) - (h1 * 60 + m1))
    assert max(mins) >= 90


def test_ignores_finished_events():
    now = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
    finished = _evt("Old Homework", EventCategory.ASSIGNMENT, now - timedelta(hours=3))
    upcoming = _evt("OS Exam", EventCategory.EXAM, now + timedelta(days=4))
    plan = StudySchedulingEngine().build(
        [finished, upcoming],
        range_start=now.date(),
        range_end=now.date() + timedelta(days=4),
        now=now,
        language="en",
    )
    titles = [
        item.title
        for day in plan.daily_plan
        for item in day.items
        if (item.kind or "study") == "study"
    ]
    assert "Old Homework" not in titles


def test_exam_day_short_review_only():
    now = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    exam_start = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    events = [_evt("OS Exam", EventCategory.EXAM, exam_start, description="Threads")]
    plan = StudySchedulingEngine().build(
        events,
        range_start=now.date(),
        range_end=now.date(),
        now=now,
        language="en",
    )
    study = [
        i
        for d in plan.daily_plan
        for i in d.items
        if (i.kind or "study") == "study" and "OS" in i.title
    ]
    assert study
    for item in study:
        h1, m1 = map(int, item.start_time.split(":"))
        h2, m2 = map(int, item.end_time.split(":"))
        assert ((h2 * 60 + m2) - (h1 * 60 + m1)) <= 45
        # Must end before exam buffer (30 min before 15:00 → 14:30)
        assert h1 * 60 + m1 < 14 * 60 + 30 or h2 * 60 + m2 <= 14 * 60 + 30


def test_regenerate_varies_schedule():
    now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
    events = [
        _evt("OS Exam", EventCategory.EXAM, now + timedelta(days=6), description="A\nB\nC"),
        _evt("Algo Exam", EventCategory.EXAM, now + timedelta(days=10), description="Graphs"),
    ]
    a = StudySchedulingEngine().build(
        events,
        range_start=now.date(),
        range_end=now.date() + timedelta(days=5),
        now=now,
        language="en",
        variation_seed=1,
    )
    b = StudySchedulingEngine().build(
        events,
        range_start=now.date(),
        range_end=now.date() + timedelta(days=5),
        now=now,
        language="en",
        variation_seed=99,
    )
    assert plan_fingerprint(a) != plan_fingerprint(b)


def test_service_regenerate_keeps_structure():
    now = datetime(2026, 8, 5, 16, 30, tzinfo=timezone.utc)
    events = [
        _evt("Homework", EventCategory.ASSIGNMENT, now + timedelta(days=1)),
        _evt("OS Exam", EventCategory.EXAM, now + timedelta(days=8), description="Threads"),
    ]
    svc = AiRecommendationService()
    plan1, _, mode1, _ = svc.generate_study_plan(
        events,
        start=now.date(),
        end=now.date() + timedelta(days=8),
        force_fallback=True,
        now=now,
        variation_seed=1,
    )
    plan2, _, mode2, _ = svc.generate_study_plan(
        events,
        start=now.date(),
        end=now.date() + timedelta(days=8),
        force_fallback=True,
        now=now,
        regenerate=True,
        previous_plan=plan1.model_dump(),
        variation_seed=2,
    )
    assert mode1 == mode2 == "deterministic"
    assert plan1.daily_plan and plan2.daily_plan
