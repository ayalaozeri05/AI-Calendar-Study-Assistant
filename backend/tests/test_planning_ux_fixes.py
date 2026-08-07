"""Past filtering, exam recovery, full-day spread, remaining-today maximization."""

from datetime import datetime, timedelta, timezone

from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.study_scheduling_engine import StudySchedulingEngine


def _evt(
    title: str,
    category: EventCategory,
    start: datetime,
    *,
    hours: float = 1.0,
    description: str | None = None,
) -> ClassifiedCalendarEvent:
    return ClassifiedCalendarEvent(
        id=f"{title}-{start.isoformat()}",
        title=title,
        category=category,
        start=start,
        end=start + timedelta(hours=hours),
        description=description,
    )


def test_today_hides_past_calendar_events():
    now = datetime(2026, 8, 5, 17, 30, tzinfo=timezone.utc)
    past = _evt("Morning lecture", EventCategory.CLASS, now.replace(hour=12, minute=0), hours=1)
    future = _evt("Evening class", EventCategory.CLASS, now.replace(hour=19, minute=0), hours=1)
    exam = _evt("OS Exam", EventCategory.EXAM, now + timedelta(days=3), description="Threads")
    plan = StudySchedulingEngine().build(
        [past, future, exam],
        range_start=now.date(),
        range_end=now.date(),
        now=now,
        language="en",
    )
    assert plan.daily_plan
    items = plan.daily_plan[0].items
    titles = [i.title for i in items if i.kind == "calendar"]
    assert "Morning lecture" not in titles
    assert "Evening class" in titles
    for item in items:
        if item.end_time:
            h, m = map(int, item.end_time.split(":"))
            assert h * 60 + m > 17 * 60 + 30 or item.start_time >= "17:30"


def test_today_study_never_before_now():
    now = datetime(2026, 8, 5, 17, 30, tzinfo=timezone.utc)
    events = [
        _evt("OS Exam", EventCategory.EXAM, now + timedelta(days=2), description="A\nB\nC"),
    ]
    plan = StudySchedulingEngine().build(
        events,
        range_start=now.date(),
        range_end=now.date(),
        now=now,
        language="en",
    )
    for day in plan.daily_plan:
        for item in day.items:
            if item.start_time:
                h, m = map(int, item.start_time.split(":"))
                assert h * 60 + m >= 17 * 60 + 30


def test_exam_recovery_blocks_immediate_study():
    now = datetime(2026, 8, 10, 7, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    exam = _evt("Automata Exam", EventCategory.EXAM, day.replace(hour=9), hours=2)
    next_exam = _evt("OS Exam", EventCategory.EXAM, day + timedelta(days=7), description="Threads")
    plan = StudySchedulingEngine().build(
        [exam, next_exam],
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    items = plan.daily_plan[0].items
    recovery = [i for i in items if i.kind == "recovery"]
    assert recovery
    # Exam 09:00–11:00 → recovery begins at 11:00 and abuts lunch (12:15)
    assert any(i.start_time == "11:00" for i in recovery)
    assert any(i.end_time == "12:15" for i in recovery)
    meals = [i for i in items if i.kind == "meal"]
    if meals:
        # No unexplained gap between recovery and lunch
        assert any(i.start_time == "12:15" for i in meals)
    for item in items:
        if (item.kind or "study") != "study":
            continue
        h, m = map(int, item.start_time.split(":"))
        assert h * 60 + m >= 13 * 60, f"Study too soon after exam: {item.start_time}"


def test_heavy_future_day_extends_into_evening():
    now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
    exam = _evt(
        "OS Exam",
        EventCategory.EXAM,
        datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
        description="Scheduling\nThreads\nMemory\nSync",
    )
    plan = StudySchedulingEngine().build(
        [exam],
        range_start=datetime(2026, 8, 6).date(),
        range_end=datetime(2026, 8, 6).date(),
        now=now,
        language="en",
        variation_seed=1,
    )
    day = plan.daily_plan[0]
    study = [i for i in day.items if (i.kind or "study") == "study"]
    assert study
    assert study[0].start_time == "09:00"
    last = max(
        int(i.end_time.split(":")[0]) * 60 + int(i.end_time.split(":")[1]) for i in study
    )
    assert last >= 18 * 60, f"Heavy day ended too early at {last // 60}:{last % 60:02d}"


def test_today_evening_maximizes_remaining_window():
    now = datetime(2026, 8, 5, 17, 30, tzinfo=timezone.utc)
    events = [
        _evt(
            "OS Exam",
            EventCategory.EXAM,
            datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
            description="Threads\nMemory",
        ),
    ]
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
        if (i.kind or "study") == "study"
    ]
    assert study
    # Should place more than a single short block when ~4h remain
    total = 0
    for i in study:
        h1, m1 = map(int, i.start_time.split(":"))
        h2, m2 = map(int, i.end_time.split(":"))
        total += (h2 * 60 + m2) - (h1 * 60 + m1)
    assert total >= 90
    assert any(i.end_time >= "20:00" for i in study) or len(study) >= 2


def test_varied_actions_on_heavy_day():
    now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
    exam = _evt(
        "OS Exam",
        EventCategory.EXAM,
        datetime(2026, 8, 9, 15, 0, tzinfo=timezone.utc),
        description="A\nB\nC",
    )
    plan = StudySchedulingEngine().build(
        [exam],
        range_start=datetime(2026, 8, 6).date(),
        range_end=datetime(2026, 8, 6).date(),
        now=now,
        language="en",
    )
    actions = [
        (i.action or "").strip()
        for i in plan.daily_plan[0].items
        if (i.kind or "study") == "study" and (i.action or "").strip()
    ]
    assert len(actions) >= 2
    assert len(set(actions)) >= 2


def test_plan_continues_around_dance_class():
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    exam = _evt("Exam", EventCategory.EXAM, day.replace(hour=9), hours=2)
    dance = _evt("Dance", EventCategory.CLASS, day.replace(hour=16, minute=30), hours=1.5)
    next_ex = _evt("Next", EventCategory.EXAM, day + timedelta(days=6), description="X")
    plan = StudySchedulingEngine().build(
        [exam, dance, next_ex],
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    items = plan.daily_plan[0].items
    assert any(i.kind == "calendar" and "Dance" in i.title for i in items)
    assert any(i.kind == "recovery" for i in items)
    study = [i for i in items if (i.kind or "study") == "study"]
    assert study, "Should keep planning study around fixed events"
    # Study after recovery and not overlapping dance
    for s in study:
        sh, sm = map(int, s.start_time.split(":"))
        eh, em = map(int, s.end_time.split(":"))
        ss, se = sh * 60 + sm, eh * 60 + em
        assert se <= 16 * 60 + 30 or ss >= 18 * 60
