"""Exam lifecycle, full-day planning, past papers, and fixed calendar events."""

from datetime import datetime, timedelta, timezone

from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.study_scheduling_engine import StudySchedulingEngine
from app.services.telegram_plan_formatter import format_plan_for_telegram


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


def _study_for(plan, title_substr: str):
    return [
        i
        for d in plan.daily_plan
        for i in d.items
        if (i.kind or "study") == "study" and title_substr in i.title
    ]


def _item_end_dt(day_iso: str, item, tz=timezone.utc) -> datetime:
    h, m = map(int, item.end_time.split(":"))
    y, mo, d = map(int, day_iso.split("-"))
    return datetime(y, mo, d, h, m, tzinfo=tz)


def test_no_prep_after_exam_start():
    """Exam Aug 13 15:00–16:00 — no study for it after 15:00, none on Aug 14+."""
    now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
    exam_start = datetime(2026, 8, 13, 15, 0, tzinfo=timezone.utc)
    next_exam = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    events = [
        _evt("OS Exam", EventCategory.EXAM, exam_start, description="Threads"),
        _evt("Networks Exam", EventCategory.EXAM, next_exam, description="TCP"),
    ]
    plan = StudySchedulingEngine().build(
        events,
        range_start=now.date(),
        range_end=now.date() + timedelta(days=14),
        now=now,
        language="en",
    )

    exam_day = "2026-08-13"
    for day in plan.daily_plan:
        for item in day.items:
            if (item.kind or "study") != "study":
                continue
            if "OS Exam" not in item.title:
                continue
            end = _item_end_dt(day.date, item)
            assert end <= exam_start, f"OS prep after exam: {day.date} {item.start_time}-{item.end_time}"

    # No OS prep on Aug 14 / 15
    for day in plan.daily_plan:
        if day.date in ("2026-08-14", "2026-08-15"):
            os_study = [i for i in day.items if (i.kind or "study") == "study" and "OS" in i.title]
            assert not os_study, f"Unexpected OS study on {day.date}"

    # After exam day, next priority study should appear (Networks)
    post = [d for d in plan.daily_plan if d.date >= "2026-08-14"]
    net = [
        i
        for d in post
        for i in d.items
        if (i.kind or "study") == "study" and "Networks" in i.title
    ]
    assert net, "After OS exam, Networks should become the study focus"


def test_exam_day_light_review_only_for_that_exam():
    now = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
    exam_start = datetime(2026, 8, 13, 15, 0, tzinfo=timezone.utc)
    plan = StudySchedulingEngine().build(
        [_evt("OS Exam", EventCategory.EXAM, exam_start, description="Threads")],
        range_start=now.date(),
        range_end=now.date(),
        now=now,
        language="en",
    )
    study = _study_for(plan, "OS")
    assert study
    for item in study:
        h1, m1 = map(int, item.start_time.split(":"))
        h2, m2 = map(int, item.end_time.split(":"))
        assert (h2 * 60 + m2) - (h1 * 60 + m1) <= 45
        assert h2 * 60 + m2 <= 15 * 60  # end <= exam start
        action = (item.action or "").lower()
        assert "new material" in action or "final" in (item.phase or "").lower() or "light" in action or "formula" in action


def test_future_heavy_day_uses_full_window():
    now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
    exam = datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    plan = StudySchedulingEngine().build(
        [
            _evt(
                "OS Exam",
                EventCategory.EXAM,
                exam,
                description="Scheduling\nThreads\nMemory",
            )
        ],
        range_start=datetime(2026, 8, 6).date(),
        range_end=datetime(2026, 8, 7).date(),
        now=now,
        language="en",
        variation_seed=0,
    )
    day = next(d for d in plan.daily_plan if d.date == "2026-08-06")
    study = [i for i in day.items if (i.kind or "study") == "study"]
    assert study
    assert study[0].start_time == "09:00"
    # Several blocks when heavy
    assert len(study) >= 2
    last_end = max(
        int(i.end_time.split(":")[0]) * 60 + int(i.end_time.split(":")[1]) for i in study
    )
    # Should use afternoon/evening when workload is heavy (not finish ~14:45)
    assert last_end >= 15 * 60
    kinds = {i.kind for i in day.items}
    assert "meal" in kinds or any("Lunch" in (i.title or "") for i in day.items)
    assert any((i.kind or "") == "break" for i in day.items) or len(study) >= 2


def test_light_workload_not_artificially_full():
    now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
    far = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    plan = StudySchedulingEngine().build(
        [_evt("Far Exam", EventCategory.EXAM, far, description="Intro")],
        range_start=datetime(2026, 8, 6).date(),
        range_end=datetime(2026, 8, 6).date(),
        now=now,
        language="en",
    )
    day = plan.daily_plan[0]
    study = [i for i in day.items if (i.kind or "study") == "study"]
    total = 0
    for i in study:
        h1, m1 = map(int, i.start_time.split(":"))
        h2, m2 = map(int, i.end_time.split(":"))
        total += (h2 * 60 + m2) - (h1 * 60 + m1)
    assert total <= 240  # light: not a packed 6–8h day


def test_past_paper_and_timed_mock_progression():
    now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
    exam = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
    plan = StudySchedulingEngine().build(
        [_evt("OS Exam", EventCategory.EXAM, exam, description="Threads\nMemory")],
        range_start=now.date(),
        range_end=exam.date(),
        now=now,
        language="en",
        variation_seed=0,
    )
    actions = " ".join(
        (i.action or "") + " " + (i.phase or "")
        for d in plan.daily_plan
        for i in d.items
        if (i.kind or "study") == "study"
    ).lower()
    assert "topic" in actions or "practice" in actions or "theory" in actions
    assert "past" in actions or "mock" in actions or "timed" in actions

    day_before = next(d for d in plan.daily_plan if d.date == "2026-08-09")
    study = [i for i in day_before.items if (i.kind or "study") == "study"]
    mockish = [
        i
        for i in study
        if "mock" in (i.action or "").lower()
        or "timed" in (i.action or "").lower()
        or "past exam" in (i.action or "").lower()
        or "mock" in (i.phase or "").lower()
    ]
    assert mockish
    # Prefer a long mock block when free
    longest = 0
    for i in mockish:
        h1, m1 = map(int, i.start_time.split(":"))
        h2, m2 = map(int, i.end_time.split(":"))
        longest = max(longest, (h2 * 60 + m2) - (h1 * 60 + m1))
    assert longest >= 90  # at least a substantial mock window (150–180 when free allows)

    exam_day = next(d for d in plan.daily_plan if d.date == "2026-08-10")
    exam_study = [i for i in exam_day.items if (i.kind or "study") == "study"]
    for i in exam_study:
        h1, m1 = map(int, i.start_time.split(":"))
        h2, m2 = map(int, i.end_time.split(":"))
        assert (h2 * 60 + m2) - (h1 * 60 + m1) <= 45


def test_fixed_events_exam_and_dance_in_plan_and_telegram():
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    exam = day.replace(hour=9, minute=0)
    dance = day.replace(hour=16, minute=30)
    next_exam = datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)
    events = [
        _evt("מבחן באוטומטים", EventCategory.EXAM, exam, hours=2.0),
        _evt("שיעור ריקוד", EventCategory.CLASS, dance, hours=1.5),
        _evt("OS Exam", EventCategory.EXAM, next_exam, description="Threads"),
    ]
    plan = StudySchedulingEngine().build(
        events,
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    assert plan.daily_plan
    items = plan.daily_plan[0].items
    cals = [i for i in items if i.kind == "calendar"]
    titles = {i.title for i in cals}
    assert "מבחן באוטומטים" in titles
    assert "שיעור ריקוד" in titles

    # No study overlaps fixed events
    def rng(i):
        h1, m1 = map(int, i.start_time.split(":"))
        h2, m2 = map(int, i.end_time.split(":"))
        return h1 * 60 + m1, h2 * 60 + m2

    for study in items:
        if (study.kind or "study") != "study":
            continue
        ss, se = rng(study)
        for cal in cals:
            cs, ce = rng(cal)
            assert se <= cs or ss >= ce, f"Study overlaps {cal.title}"

    text = format_plan_for_telegram(plan)
    assert "מבחן באוטומטים" in text
    assert "שיעור ריקוד" in text
    assert "CALENDAR EVENT" in text


def test_distinct_stages_across_prep_days():
    now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
    exam = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
    plan = StudySchedulingEngine().build(
        [_evt("OS Exam", EventCategory.EXAM, exam, description="A\nB\nC")],
        range_start=now.date(),
        range_end=exam.date() - timedelta(days=1),
        now=now,
        language="en",
    )
    actions = []
    for d in plan.daily_plan:
        for i in d.items:
            if (i.kind or "study") == "study" and i.action:
                actions.append(i.action.strip())
    assert len(set(actions)) >= 2, "Prep days should not repeat the same action text"
