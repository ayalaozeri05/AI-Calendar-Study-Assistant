"""Timeline normalization: recovery, rest merge, gap fill, Ollama time lock."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.schemas.brief_schema import (
    DailyPlan,
    PriorityItem,
    StructuredStudyPlan,
    StudyPlanItem,
)
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.ai_recommendation_service import (
    AiRecommendationService,
    _merge_content,
)
from app.services.study_scheduling_engine import (
    StudySchedulingEngine,
    _Placed,
    _normalize_day_timeline,
    validate_day_timeline,
)


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


def _mins(item: StudyPlanItem) -> tuple[int, int]:
    sh, sm = map(int, item.start_time.split(":"))
    eh, em = map(int, item.end_time.split(":"))
    return sh * 60 + sm, eh * 60 + em


def test_exam_recovery_begins_at_exam_end():
    now = datetime(2026, 8, 10, 7, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    exam = _evt("Automata Exam", EventCategory.EXAM, day.replace(hour=9), hours=2)
    next_exam = _evt(
        "OS Exam", EventCategory.EXAM, day + timedelta(days=7), description="Threads"
    )
    plan = StudySchedulingEngine().build(
        [exam, next_exam],
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    recovery = [i for i in plan.daily_plan[0].items if i.kind == "recovery"]
    assert recovery
    assert recovery[0].start_time == "11:00"


def test_recovery_then_lunch_has_no_gap():
    now = datetime(2026, 8, 10, 7, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    exam = _evt("Automata Exam", EventCategory.EXAM, day.replace(hour=9), hours=2)
    next_exam = _evt(
        "OS Exam", EventCategory.EXAM, day + timedelta(days=5), description="A\nB"
    )
    plan = StudySchedulingEngine().build(
        [exam, next_exam],
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    items = plan.daily_plan[0].items
    recovery = next(i for i in items if i.kind == "recovery")
    lunch = next((i for i in items if i.kind == "meal" and "Lunch" in i.title), None)
    assert recovery.end_time == "12:15"
    if lunch:
        assert lunch.start_time == "12:15"
        assert recovery.end_time == lunch.start_time


def test_break_and_meal_20_min_apart_are_normalized():
    tz = timezone.utc
    day = datetime(2026, 8, 11, tzinfo=tz).date()
    now = datetime(2026, 8, 11, 8, 0, tzinfo=tz)
    blocks = [
        _Placed(
            start=datetime(2026, 8, 11, 11, 0, tzinfo=tz),
            end=datetime(2026, 8, 11, 11, 20, tzinfo=tz),
            kind="break",
            title="Break",
            action="rest",
            reason="",
            label="Break",
        ),
        _Placed(
            start=datetime(2026, 8, 11, 12, 15, tzinfo=tz),
            end=datetime(2026, 8, 11, 13, 15, tzinfo=tz),
            kind="meal",
            title="Lunch",
            action="lunch",
            reason="",
            label="Meal",
        ),
        _Placed(
            start=datetime(2026, 8, 11, 14, 0, tzinfo=tz),
            end=datetime(2026, 8, 11, 16, 0, tzinfo=tz),
            kind="study",
            title="OS Exam",
            action="Practice",
            reason="",
            label="Study session",
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
    # Short break before lunch must not remain as a junk rest card with a gap
    kinds = [(b.kind, b.start.strftime("%H:%M"), b.end.strftime("%H:%M")) for b in out]
    assert ("break", "11:00", "11:20") not in kinds
    rest_meal = [b for b in out if b.kind in ("break", "recovery", "meal")]
    # Recovery/travel should abut lunch, or break removed entirely
    for a, b in zip(rest_meal, rest_meal[1:]):
        gap = (b.start - a.end).total_seconds() / 60.0
        if a.kind in ("break", "recovery") and b.kind == "meal":
            assert gap < 0.01, f"gap between {a.kind} and meal: {gap}"


def test_free_60_min_interval_gets_study_when_workload_remains():
    now = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
    exam = _evt(
        "OS Exam",
        EventCategory.EXAM,
        datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
        description="Scheduling\nThreads\nMemory",
    )
    plan = StudySchedulingEngine().build(
        [exam],
        range_start=datetime(2026, 8, 6).date(),
        range_end=datetime(2026, 8, 6).date(),
        now=now,
        language="en",
        variation_seed=2,
    )
    study = [i for i in plan.daily_plan[0].items if (i.kind or "study") == "study"]
    assert study
    total = sum(_mins(i)[1] - _mins(i)[0] for i in study)
    assert total >= 60


def test_free_20_min_interval_no_fake_long_study():
    tz = timezone.utc
    day = datetime(2026, 8, 11, tzinfo=tz).date()
    now = datetime(2026, 8, 11, 8, 0, tzinfo=tz)
    blocks = [
        _Placed(
            start=datetime(2026, 8, 11, 9, 0, tzinfo=tz),
            end=datetime(2026, 8, 11, 10, 0, tzinfo=tz),
            kind="study",
            title="A",
            action="x",
            reason="",
        ),
        _Placed(
            start=datetime(2026, 8, 11, 10, 20, tzinfo=tz),
            end=datetime(2026, 8, 11, 12, 0, tzinfo=tz),
            kind="study",
            title="B",
            action="y",
            reason="",
        ),
    ]
    out = _normalize_day_timeline(
        blocks,
        day=day,
        now=now,
        hebrew=False,
        remaining_workload_min=120,
        demand=[],
        seed=1,
    )
    # 20-minute hole must not become a long fake study block
    for b in out:
        if b.kind == "study":
            mins = int((b.end - b.start).total_seconds() // 60)
            assert mins != 20 or b.title in ("A", "B")
    mid = [
        b
        for b in out
        if b.start >= datetime(2026, 8, 11, 10, 0, tzinfo=tz)
        and b.end <= datetime(2026, 8, 11, 10, 20, tzinfo=tz)
        and b.kind == "study"
        and b.title not in ("A", "B")
    ]
    assert not mid


def test_fixed_dance_class_preserved():
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    exam = _evt("Exam", EventCategory.EXAM, day.replace(hour=9), hours=2)
    dance = _evt(
        "Dance", EventCategory.CLASS, day.replace(hour=16, minute=30), hours=1.5
    )
    next_ex = _evt("Next", EventCategory.EXAM, day + timedelta(days=6), description="X")
    plan = StudySchedulingEngine().build(
        [exam, dance, next_ex],
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    items = plan.daily_plan[0].items
    dance_items = [i for i in items if i.kind == "calendar" and "Dance" in i.title]
    assert dance_items
    assert dance_items[0].start_time == "16:30"
    for s in items:
        if (s.kind or "study") != "study":
            continue
        ss, se = _mins(s)
        assert se <= 16 * 60 + 30 or ss >= 18 * 60


def test_ollama_time_changes_are_ignored():
    engine = StructuredStudyPlan(
        summary="Engine",
        priority_item=PriorityItem(title="Exam", reason="Soon"),
        daily_plan=[
            DailyPlan(
                date="2026-08-11",
                items=[
                    StudyPlanItem(
                        start_time="11:00",
                        end_time="12:15",
                        title="Recovery / travel home",
                        kind="recovery",
                        action="Travel home",
                    ),
                    StudyPlanItem(
                        start_time="12:15",
                        end_time="13:15",
                        title="Lunch",
                        kind="meal",
                        action="Lunch",
                    ),
                    StudyPlanItem(
                        start_time="14:00",
                        end_time="15:30",
                        title="OS Exam",
                        kind="study",
                        action="Practice graphs",
                        reason="Weak area",
                    ),
                ],
            )
        ],
        tips=["Tip"],
    )
    llm = StructuredStudyPlan(
        summary="Polished",
        priority_item=PriorityItem(title="Changed", reason="Better reason"),
        daily_plan=[
            DailyPlan(
                date="2026-08-11",
                items=[
                    StudyPlanItem(
                        start_time="10:00",
                        end_time="11:00",
                        title="Hijacked",
                        kind="break",
                        action="Nope",
                    ),
                    StudyPlanItem(
                        start_time="11:00",
                        end_time="12:00",
                        title="Fake meal",
                        kind="meal",
                        action="Eat early",
                    ),
                    StudyPlanItem(
                        start_time="13:00",
                        end_time="16:00",
                        title="OS Exam",
                        kind="study",
                        action="Improved action",
                        reason="Improved reason",
                    ),
                ],
            )
        ],
        tips=["New tip"],
    )
    merged = _merge_content(engine, llm)
    items = merged.daily_plan[0].items
    assert items[0].start_time == "11:00"
    assert items[0].end_time == "12:15"
    assert items[0].kind == "recovery"
    assert items[0].title == "Recovery / travel home"
    assert items[2].start_time == "14:00"
    assert items[2].end_time == "15:30"
    assert items[2].action == "Improved action"
    assert items[2].reason == "Improved reason"


def test_no_two_redundant_rest_cards_consecutively():
    now = datetime(2026, 8, 10, 7, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    exam = _evt("Automata Exam", EventCategory.EXAM, day.replace(hour=9), hours=2)
    next_exam = _evt(
        "OS Exam", EventCategory.EXAM, day + timedelta(days=4), description="A\nB\nC"
    )
    plan = StudySchedulingEngine().build(
        [exam, next_exam],
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    items = plan.daily_plan[0].items
    for a, b in zip(items, items[1:]):
        if a.kind in ("break", "recovery") and b.kind in ("break", "recovery"):
            raise AssertionError(f"redundant rest pair: {a.kind} → {b.kind}")
        if a.kind == "break" and b.kind == "meal":
            sa, ea = _mins(a)
            sb, _ = _mins(b)
            assert sb - ea < 1, "break must not leave a gap before meal"


def test_every_returned_day_passes_timeline_validation():
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, day.replace(hour=9), hours=2),
        _evt("Dance", EventCategory.CLASS, day.replace(hour=16, minute=30), hours=1.5),
        _evt("Next", EventCategory.EXAM, day + timedelta(days=6), description="X\nY"),
    ]
    plan = StudySchedulingEngine().build(
        events,
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    for daily in plan.daily_plan:
        blocks = []
        for item in daily.items:
            sh, sm = map(int, (item.start_time or "0:0").split(":"))
            eh, em = map(int, (item.end_time or "0:0").split(":"))
            y, mo, d = map(int, daily.date.split("-"))
            blocks.append(
                _Placed(
                    start=datetime(y, mo, d, sh, sm, tzinfo=timezone.utc),
                    end=datetime(y, mo, d, eh, em, tzinfo=timezone.utc),
                    kind=item.kind or "study",  # type: ignore[arg-type]
                    title=item.title,
                    action=item.action or "",
                    reason=item.reason or "",
                )
            )
        errors = validate_day_timeline(
            blocks, day=day.date(), now=now, remaining_workload_min=0
        )
        # recovery→meal consecutive is allowed; reject true geometry failures
        hard = [
            e
            for e in errors
            if e
            in {
                "overlap",
                "negative_or_zero_duration",
                "study_in_past",
                "recovery_meal_gap",
                "redundant_adjacent_rest",
            }
        ]
        assert not hard, hard


def test_generate_study_plan_keeps_engine_times_when_ollama_rewrites(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ai_polish_enabled", True)
    monkeypatch.setattr(settings, "skip_ollama_polish", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, day.replace(hour=9), hours=2),
        _evt("Next", EventCategory.EXAM, day + timedelta(days=5), description="Topic"),
    ]
    engine_plan = StudySchedulingEngine().build(
        events,
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    # Fake Ollama that shifts every block earlier by 1 hour
    hijacked = engine_plan.model_copy(deep=True)
    for d in hijacked.daily_plan:
        for item in d.items:
            if item.start_time and item.end_time:
                sh, sm = map(int, item.start_time.split(":"))
                eh, em = map(int, item.end_time.split(":"))
                item.start_time = f"{max(sh - 1, 0):02d}:{sm:02d}"
                item.end_time = f"{max(eh - 1, 0):02d}:{em:02d}"
                item.action = "Polished wording"

    ollama = MagicMock()
    ollama.is_available.return_value = True
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())
    svc._polish_with_ollama = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda plan, *a, **k: _merge_content(plan, hijacked)
    )
    plan, _, mode, _ = svc.generate_study_plan(
        events,
        start=day.date(),
        end=day.date(),
        now=now,
    )
    assert mode == "ollama"
    original = {
        (d.date, i.start_time, i.end_time, i.kind, i.title)
        for d in engine_plan.daily_plan
        for i in d.items
    }
    result = {
        (d.date, i.start_time, i.end_time, i.kind, i.title)
        for d in plan.daily_plan
        for i in d.items
    }
    assert original == result
