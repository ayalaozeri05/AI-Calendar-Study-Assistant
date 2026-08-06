"""Planning anchor and future-day 09:00 boundary tests."""

from datetime import datetime, timedelta, timezone

from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.study_scheduling_engine import StudySchedulingEngine, ceil_to_15_minutes


def _evt(title, category, start, *, hours=1.0, description=None):
    return ClassifiedCalendarEvent(
        id=f"{title}-{start.isoformat()}",
        title=title,
        category=category,
        start=start,
        end=start + timedelta(hours=hours),
        description=description,
    )


def test_ceil_to_15_minutes_examples():
    tz = timezone.utc
    assert ceil_to_15_minutes(datetime(2026, 8, 5, 16, 2, tzinfo=tz)).strftime("%H:%M") == "16:15"
    assert ceil_to_15_minutes(datetime(2026, 8, 5, 16, 17, tzinfo=tz)).strftime("%H:%M") == "16:30"
    assert ceil_to_15_minutes(datetime(2026, 8, 5, 16, 37, tzinfo=tz)).strftime("%H:%M") == "16:45"
    assert ceil_to_15_minutes(datetime(2026, 8, 5, 16, 53, tzinfo=tz)).strftime("%H:%M") == "17:00"
    assert ceil_to_15_minutes(datetime(2026, 8, 5, 16, 15, tzinfo=tz)).strftime("%H:%M") == "16:15"


def test_future_day_starts_exactly_0900_without_conflicts():
    now = datetime(2026, 8, 5, 16, 10, tzinfo=timezone.utc)
    events = [
        _evt("OS Exam", EventCategory.EXAM, now + timedelta(days=4), description="Threads")
    ]
    for seed in (0, 1, 7, 99):
        plan = StudySchedulingEngine().build(
            events,
            range_start=now.date() + timedelta(days=1),
            range_end=now.date() + timedelta(days=3),
            now=now,
            language="en",
            variation_seed=seed,
        )
        assert plan.daily_plan
        first = next(i for i in plan.daily_plan[0].items if (i.kind or "study") == "study")
        assert first.start_time == "09:00", f"seed={seed} got {first.start_time}"


def test_future_day_respects_morning_conflict():
    now = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    day = now.date() + timedelta(days=1)
    meeting = _evt(
        "Class",
        EventCategory.CLASS,
        datetime.combine(day, datetime.strptime("09:00", "%H:%M").time()).replace(
            tzinfo=timezone.utc
        ),
        hours=1,
    )
    exam = _evt("OS Exam", EventCategory.EXAM, now + timedelta(days=5), description="A")
    plan = StudySchedulingEngine().build(
        [meeting, exam],
        range_start=day,
        range_end=day,
        now=now,
        language="en",
    )
    study = [i for i in plan.daily_plan[0].items if (i.kind or "study") == "study"]
    assert study
    h, m = map(int, study[0].start_time.split(":"))
    assert h * 60 + m >= 10 * 60  # after 09:00–10:00 (+ buffer may push later)


def test_regenerate_reuses_anchor_not_clock():
    anchor = datetime(2026, 8, 5, 17, 0, tzinfo=timezone.utc)
    # "Now" is a few minutes later — without anchor, ceil would be 17:15; with
    # unused clock shift to next hour we previously got 18:00. Anchor keeps 17:00
    # until it has passed enough that max(anchor, ceil(now)) applies.
    now_create = datetime(2026, 8, 5, 16, 37, tzinfo=timezone.utc)
    events = [
        _evt("OS Exam", EventCategory.EXAM, now_create + timedelta(days=3), description="T")
    ]
    engine = StudySchedulingEngine()
    first = engine.build(
        events,
        range_start=now_create.date(),
        range_end=now_create.date() + timedelta(days=2),
        now=now_create,
        language="en",
        variation_seed=1,
    )
    assert first.planning_anchor
    saved = datetime.fromisoformat(first.planning_anchor)
    assert saved.strftime("%H:%M") == "16:45"

    now_regen = datetime(2026, 8, 5, 16, 42, tzinfo=timezone.utc)
    second = engine.build(
        events,
        range_start=now_create.date(),
        range_end=now_create.date() + timedelta(days=2),
        now=now_regen,
        language="en",
        variation_seed=99,
        planning_anchor=saved,
    )
    today = next(d for d in second.daily_plan if d.date == now_create.date().isoformat())
    study = [i for i in today.items if (i.kind or "study") == "study"]
    assert study
    h, m = map(int, study[0].start_time.split(":"))
    # Must stay at/after 16:45, not jump to 18:00
    assert h * 60 + m == 16 * 60 + 45


def test_regenerate_after_anchor_passed_uses_next_15_not_hour():
    saved = datetime(2026, 8, 5, 17, 0, tzinfo=timezone.utc)
    now = datetime(2026, 8, 5, 17, 4, tzinfo=timezone.utc)
    events = [
        _evt("OS Exam", EventCategory.EXAM, now + timedelta(days=3), description="T")
    ]
    plan = StudySchedulingEngine().build(
        events,
        range_start=now.date(),
        range_end=now.date() + timedelta(days=2),
        now=now,
        language="en",
        planning_anchor=saved,
        variation_seed=3,
    )
    today = next(d for d in plan.daily_plan if d.date == now.date().isoformat())
    study = [i for i in today.items if (i.kind or "study") == "study"]
    assert study
    assert study[0].start_time == "17:15"
