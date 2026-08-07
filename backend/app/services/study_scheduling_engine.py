"""Deterministic study scheduling engine.

Owns WHEN study happens. Enforces exam lifecycle, fixed calendar events,
full-day future planning, and progressive prep stages (incl. past papers / mocks).
"""

from __future__ import annotations

import logging
import re
import time as pytime
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, time, timezone
from typing import Literal

from app.rag.document_matcher import course_lookup_key
from app.schemas.brief_schema import (
    DailyPlan,
    PriorityItem,
    StructuredStudyPlan,
    StudyPlanItem,
)
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory

logger = logging.getLogger(__name__)

BlockKind = Literal["study", "break", "meal", "calendar", "recovery"]

_DAY_START = time(9, 0)
_DAY_END = time(21, 30)
_LUNCH = (time(12, 15), time(13, 15))
_DINNER = (time(19, 30), time(20, 15))

# Rest-like kinds — must not stack with unexplained gaps between them.
_REST_KINDS = frozenset({"break", "recovery", "meal"})
_GAP_MERGE_MIN = 30  # merge/relabel rest when gap is shorter than this
_LIGHT_TASK_MIN = 30
_STUDY_FILL_MIN = 45
_MAX_FOCUS_MIN = 150
_MAX_NORMALIZE_PASSES = 3
_MAX_REPAIR_PASSES = 2
_MAX_BLOCKS_PER_DAY = 30

# Pedagogical stages — varied coach-style activities
_STAGE_EN = {
    "theory_review": "Organize syllabus and review core theory",
    "topic_practice": "Solve topic-based practice questions",
    "past_questions": "Work through past exam questions and note patterns",
    "mistake_review": "Review mistakes and rebuild weak areas",
    "timed_mock": "Complete a full timed mock / past exam",
    "weak_topic_revision": "Revise weak topics from your error log",
    "final_review": "Light final review — formulas, flashcards, calm prep only",
    "flashcards": "Drill flashcards on key definitions and concepts",
    "formula_review": "Memorize and re-derive essential formulas",
    "summary_notes": "Write a one-page summary of today's material",
    "oral_recall": "Quick oral recall — explain topics out loud without notes",
    "mental_prep": "Mental preparation — calm focus, checklist, travel plan",
    "evening_preview": "Light preview of tomorrow's priorities",
}
_STAGE_HE = {
    "theory_review": "ארגון הסילבוס וסקירת תיאוריה מרכזית",
    "topic_practice": "פתרון תרגילים לפי נושאים",
    "past_questions": "תרגול שאלות ממבחנים קודמים וזיהוי דפוסים",
    "mistake_review": "חזרה על טעויות וחיזוק נקודות חלשות",
    "timed_mock": "מבחן לדוגמה מלא בתנאי זמן",
    "weak_topic_revision": "חזרה על נושאים חלשים מיומן הטעויות",
    "final_review": "חזרה קלה אחרונה — נוסחאות, כרטיסיות והכנה רגועה בלבד",
    "flashcards": "תרגול כרטיסיות על הגדרות ומושגים מרכזיים",
    "formula_review": "שינון ונגזרת של נוסחאות חשובות",
    "summary_notes": "כתיבת סיכום עמוד אחד של חומר היום",
    "oral_recall": "שליפה בעל פה — הסבר נושאים בלי מחברת",
    "mental_prep": "הכנה מנטלית — מיקוד, רשימת בדיקה ותכנון הגעה",
    "evening_preview": "מבט קל על סדרי העדיפויות של מחר",
}

_STAGE_KEYS_BY_PHASE = {
    "early": ["theory_review", "summary_notes", "flashcards", "topic_practice"],
    "middle": ["topic_practice", "past_questions", "mistake_review", "formula_review", "oral_recall"],
    "late": ["past_questions", "timed_mock", "mistake_review", "weak_topic_revision", "formula_review"],
    "eve": ["flashcards", "formula_review", "oral_recall", "summary_notes", "evening_preview", "mental_prep"],
    "exam_day": ["final_review", "flashcards", "formula_review", "mental_prep"],
}


@dataclass
class _Interval:
    start: datetime
    end: datetime

    def duration_min(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() // 60))


@dataclass
class _Target:
    event: ClassifiedCalendarEvent
    kind: Literal["exam", "assignment", "project"]
    due: datetime
    topics: list[str] = field(default_factory=list)
    weight: float = 1.0


@dataclass
class _Demand:
    target: _Target
    minutes: int
    stage: str
    topic: str | None
    hard_deadline: datetime | None = None  # study must end by this (exam start)


@dataclass
class _Placed:
    start: datetime
    end: datetime
    kind: BlockKind
    title: str
    action: str
    reason: str
    event_id: str | None = None
    phase: str = ""
    category: str | None = None
    label: str | None = None


class StudySchedulingEngine:
    def build(
        self,
        events: list[ClassifiedCalendarEvent],
        *,
        range_start: date,
        range_end: date,
        now: datetime | None = None,
        language: str = "en",
        variation_seed: int = 0,
        planning_anchor: datetime | None = None,
        rag_topics: dict[str, list[str]] | None = None,
    ) -> StructuredStudyPlan:
        now = _aware(now or datetime.now().astimezone())
        today = now.date()
        seed = int(variation_seed or 0)
        topic_hints = rag_topics or {}

        if planning_anchor is not None:
            saved = ceil_to_15_minutes(_aware(planning_anchor))
            effective_today_start = max(saved, ceil_to_15_minutes(now))
            anchor_out = saved
        else:
            effective_today_start = ceil_to_15_minutes(now)
            anchor_out = effective_today_start

        logger.debug("planning_anchor=%s effective_today_start=%s", anchor_out, effective_today_start)

        hebrew = language == "he"
        all_events = list(events)
        # Global targets at "now" only for summary; per-day filtering is authoritative
        global_targets = _select_targets(
            [e for e in all_events if not _already_ended(e, now)],
            now,
            rag_topics=topic_hints,
        )

        placed_by_day: dict[str, list[_Placed]] = {}
        day = max(range_start, today)
        day_index = 0
        while day <= range_end:
            blocks = self._schedule_day(
                day=day,
                now=now,
                today_start=effective_today_start,
                all_events=all_events,
                hebrew=hebrew,
                seed=seed + day_index * 17,
                day_index=day_index,
                rag_topics=topic_hints,
            )
            if blocks:
                placed_by_day[day.isoformat()] = blocks
            day += timedelta(days=1)
            day_index += 1

        daily_plan = [
            DailyPlan(
                date=key,
                items=[
                    StudyPlanItem(
                        start_time=b.start.strftime("%H:%M"),
                        end_time=b.end.strftime("%H:%M"),
                        title=b.title,
                        action=b.action,
                        reason=b.reason,
                        kind=b.kind,
                        phase=b.phase or None,
                        category=b.category,
                        label=b.label,
                    )
                    for b in blocks
                ],
            )
            for key, blocks in sorted(placed_by_day.items())
        ]

        # Priority reflects still-active items at "now"
        return StructuredStudyPlan(
            summary=_summary(global_targets, daily_plan, hebrew),
            priority_item=_priority_item(global_targets, hebrew, now),
            daily_plan=daily_plan,
            tips=_coach_tips(global_targets, daily_plan, hebrew, now=now),
            planning_anchor=anchor_out.isoformat(),
        )

    def _schedule_day(
        self,
        *,
        day: date,
        now: datetime,
        today_start: datetime,
        all_events: list[ClassifiedCalendarEvent],
        hebrew: bool,
        seed: int,
        day_index: int,
        rag_topics: dict[str, list[str]] | None = None,
    ) -> list[_Placed]:
        # Timeline for TODAY always starts at max(now, 09:00) via today_start
        day_cursor = (
            today_start
            if day == now.date()
            else datetime.combine(day, _DAY_START, tzinfo=now.tzinfo)
        )
        now_aware = _aware(now)

        # Future calendar events only (today: end > now)
        fixed = _fixed_events_for_day(all_events, day, now.tzinfo, now=now_aware)
        recovery = _exam_recovery_blocks(all_events, day, now.tzinfo, hebrew, now=now_aware)

        day_targets = _select_targets_for_moment(
            all_events, day_cursor, rag_topics=rag_topics
        )

        free = _free_slots_for_day(
            day,
            now,
            all_events,
            today_start=today_start,
            seed=seed,
        )
        remaining_free = sum(g.duration_min() for g in free)

        demand = _build_demand(
            day_targets,
            day=day,
            moment=day_cursor,
            seed=seed,
            day_index=day_index,
            hebrew=hebrew,
            remaining_free_min=remaining_free,
            is_today=(day == now.date()),
        )

        study_blocks: list[_Placed] = []
        if free and demand:
            study_blocks = _fill_day(
                free, demand, day=day, hebrew=hebrew, seed=seed
            )

        merged = list(fixed) + list(recovery) + list(study_blocks)
        _insert_meal_markers(merged, day, hebrew, now=now_aware if day == now.date() else None)
        merged.sort(key=lambda p: p.start)

        # Hard filter: never show anything that already ended
        if day == now.date():
            merged = [p for p in merged if p.end > now_aware]

        # Deterministic geometry fix before any LLM polish.
        remaining_workload = sum(max(d.minutes, 0) for d in demand)
        merged = _normalize_day_timeline(
            merged,
            day=day,
            now=now_aware,
            hebrew=hebrew,
            remaining_workload_min=remaining_workload,
            demand=demand,
            seed=seed,
        )
        return merged


# ---------------------------------------------------------------------------
# Targets — per-moment (exam lifecycle)
# ---------------------------------------------------------------------------


def _select_targets(
    events: list[ClassifiedCalendarEvent],
    moment: datetime,
    *,
    rag_topics: dict[str, list[str]] | None = None,
) -> list[_Target]:
    return _select_targets_for_moment(events, moment, rag_topics=rag_topics)


def _select_targets_for_moment(
    events: list[ClassifiedCalendarEvent],
    moment: datetime,
    *,
    rag_topics: dict[str, list[str]] | None = None,
) -> list[_Target]:
    """Only exams/assignments/projects that have not started/ended yet at moment."""
    targets: list[_Target] = []
    for event in events:
        if event.category == EventCategory.EXAM:
            kind: Literal["exam", "assignment", "project"] = "exam"
            # Exam is no longer a prep target once it has started
            if _aware(event.start) <= moment:
                continue
        elif event.category == EventCategory.ASSIGNMENT:
            kind = "assignment"
            if _already_ended(event, moment):
                continue
        elif event.category == EventCategory.PROJECT:
            kind = "project"
            if _already_ended(event, moment):
                continue
        else:
            continue

        due = _aware(event.start)
        days = max((due - moment).total_seconds() / 86400.0, 0.05)
        if kind == "exam":
            weight = 140.0 / days
        elif kind == "assignment":
            weight = 100.0 / days
        else:
            weight = 80.0 / days
        desc_topics = _topics_from_description(event.description)
        hints = rag_topics or {}
        hint_topics = list(hints.get(str(event.id), []) or [])
        if not hint_topics:
            hint_topics = list(hints.get(course_lookup_key(event.title), []) or [])
        targets.append(
            _Target(
                event=event,
                kind=kind,
                due=due,
                topics=_merge_topics(hint_topics, desc_topics),
                weight=weight,
            )
        )
    targets.sort(key=lambda t: (-t.weight, t.due))
    return targets


def _merge_topics(primary: list[str], secondary: list[str], *, limit: int = 12) -> list[str]:
    """Prefer RAG topics, then description topics; de-dupe case-insensitively."""
    seen: set[str] = set()
    out: list[str] = []
    for topic in list(primary or []) + list(secondary or []):
        text = (topic or "").strip()
        if len(text) < 2:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _topics_from_description(description: str | None) -> list[str]:
    if not description:
        return []
    topics: list[str] = []
    for raw in description.splitlines():
        line = raw.strip(" -•*\t")
        if not line:
            continue
        if re.fullmatch(r"(exam|assignment|project|homework)\s*:?", line, re.I):
            continue
        m = re.match(r"(exam|assignment|project)\s*:\s*(.+)", line, re.I)
        if m:
            line = m.group(2).strip()
        for part in re.split(r"[,;]|\band\b|\bו\b", line):
            t = part.strip(" -•*")
            if len(t) >= 2:
                topics.append(t)
    seen: set[str] = set()
    out: list[str] = []
    for t in topics:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out[:12]


def _stage_key_for(target: _Target, day: date, seed: int = 0, slot: int = 0) -> str:
    days_until = (target.due.date() - day).days
    if target.kind == "exam":
        if days_until <= 0:
            pool = _STAGE_KEYS_BY_PHASE["exam_day"]
        elif days_until <= 2:
            pool = _STAGE_KEYS_BY_PHASE["late"]
        elif days_until <= 6:
            pool = _STAGE_KEYS_BY_PHASE["middle"]
        else:
            pool = _STAGE_KEYS_BY_PHASE["early"]
    else:
        if days_until <= 1:
            pool = ["topic_practice", "mistake_review", "summary_notes", "oral_recall"]
        else:
            pool = _STAGE_KEYS_BY_PHASE["early"]
    return pool[(seed + slot + day.toordinal()) % len(pool)]


def _stage_for(target: _Target, day: date, hebrew: bool, seed: int = 0, slot: int = 0) -> str:
    stages = _STAGE_HE if hebrew else _STAGE_EN
    if target.kind != "exam" and (target.due.date() - day).days <= 0:
        return (
            "Finish the assignment and check your answers"
            if not hebrew
            else "השלמת המשימה ובדיקת תשובות"
        )
    key = _stage_key_for(target, day, seed, slot)
    return stages.get(key, stages["theory_review"])


def _topic_for(target: _Target, day: date, seed: int, slot: int) -> str | None:
    if not target.topics:
        return None
    return target.topics[(day.toordinal() + seed + slot) % len(target.topics)]


def _daily_budget_minutes(
    day_targets: list[_Target],
    day: date,
    seed: int,
    *,
    remaining_free_min: int | None = None,
    is_today: bool = False,
) -> int:
    """Light 1.5-3h, Moderate 3-5h, Heavy 5-7h, Very heavy 6-8h (study minutes)."""
    if not day_targets:
        return 0
    exams_today = [t for t in day_targets if t.kind == "exam" and t.due.date() == day]
    others = [t for t in day_targets if t not in exams_today]
    if exams_today and not others:
        budget = 45
    else:
        focus = others or day_targets
        nearest = min((max((t.due.date() - day).days, 0) for t in focus), default=99)
        exam_count = sum(1 for t in focus if t.kind == "exam")
        if nearest <= 1 or (exam_count >= 2 and nearest <= 3):
            budget = 420
        elif nearest <= 3:
            budget = 360
        elif nearest <= 7:
            budget = 270
        else:
            budget = 150
        budget += (seed % 3) * 30
        if exams_today:
            budget += 45

    if is_today and remaining_free_min is not None:
        capacity = max(0, int(remaining_free_min * 0.9))
        if capacity < 20:
            return 0
        if capacity < 45:
            return min(budget, capacity)
        budget = min(max(budget, min(capacity, 180)), capacity)
    elif remaining_free_min is not None and remaining_free_min > 0 and budget >= 270:
        # Heavy future days: use most of the free window until 21:30
        usable = max(270, remaining_free_min - 90)
        budget = min(max(budget, usable), remaining_free_min - 45)
    return max(0, int(budget))


def _build_demand(
    targets: list[_Target],
    *,
    day: date,
    moment: datetime,
    seed: int,
    day_index: int,
    hebrew: bool,
    remaining_free_min: int | None = None,
    is_today: bool = False,
) -> list[_Demand]:
    # Strict lifecycle filter for this calendar day
    live: list[_Target] = []
    for t in targets:
        if t.kind == "exam":
            if t.due.date() < day:
                continue  # exam was on a previous day
            if t.due.date() == day and t.due <= moment:
                continue  # exam already started today
            live.append(t)
        else:
            if t.due.date() < day and _already_ended(t.event, moment):
                continue
            live.append(t)

    exams_today = [t for t in live if t.kind == "exam" and t.due.date() == day]
    due_assignments = [
        t
        for t in live
        if t.kind in ("assignment", "project")
        and t.due.date() <= day
        and t.due > moment
    ]
    # Future exams/assignments ONLY if exam is still after this day (or later today)
    upcoming = [
        t
        for t in live
        if t not in exams_today
        and t not in due_assignments
        and (t.kind != "exam" or t.due.date() > day)
    ]
    upcoming.sort(key=lambda t: (-t.weight, t.due))

    demand: list[_Demand] = []
    slot = 0

    for exam in exams_today:
        mins = 25 + (seed % 4) * 5  # 25–40, capped to 45 in fill
        demand.append(
            _Demand(
                exam,
                mins,
                _stage_for(exam, day, hebrew, seed, slot),
                _topic_for(exam, day, seed, slot),
                hard_deadline=exam.due,
            )
        )
        slot += 1

    for asn in sorted(due_assignments, key=lambda t: t.due):
        demand.append(
            _Demand(
                asn,
                120 if asn.due.date() == day else 90,
                _stage_for(asn, day, hebrew, seed, slot),
                _topic_for(asn, day, seed, slot),
                hard_deadline=None,
            )
        )
        slot += 1

    budget = _daily_budget_minutes(
        live, day, seed, remaining_free_min=remaining_free_min, is_today=is_today
    )
    # Exam-day light review does not consume the post-exam / other-priority budget
    used = sum(d.minutes for d in demand if d.target not in exams_today)

    rotated = list(upcoming)
    if seed % 2 and len(rotated) >= 2:
        rotated[0], rotated[1] = rotated[1], rotated[0]

    for idx, tgt in enumerate(rotated):
        if used >= budget:
            break
        days_until = (tgt.due.date() - day).days
        # Never prep an exam on/after its date here (exams_today handled above)
        if tgt.kind == "exam" and days_until < 0:
            continue

        # Day before exam: prefer one long mock (150–180) when free (not when carving tonight)
        if tgt.kind == "exam" and days_until == 1 and not is_today:
            session_specs: list[tuple[int | None, str | None]] = [
                (180 if seed % 2 == 0 else 150, "timed_mock"),
                (90, "mistake_review"),
                (60, "weak_topic_revision"),
            ]
        elif tgt.kind == "exam" and days_until == 2 and not is_today:
            session_specs = [(120, "past_questions"), (90, "mistake_review"), (90, None)]
        elif idx == 0 and tgt.kind == "exam" and days_until <= 7:
            n = 4 if is_today else (3 if days_until <= 3 else 2)
            session_specs = [(None, None)] * n
        elif idx == 0:
            n = 4 if (is_today or days_until <= 3) else 3
            session_specs = [(None, None)] * n
        else:
            session_specs = [(None, None), (None, None)] if days_until <= 5 else [(None, None)]

        for s, (fixed_chunk, stage_key) in enumerate(session_specs):
            if used >= budget:
                break
            stages = _STAGE_HE if hebrew else _STAGE_EN
            if fixed_chunk is not None:
                chunk = fixed_chunk
                stage = (
                    stages[stage_key]
                    if stage_key and stage_key in stages
                    else _stage_for(tgt, day, hebrew, seed + s, slot)
                )
            else:
                options = [90, 75, 60] if is_today else [90, 120, 150]
                chunk = options[(seed + day_index + idx + s) % len(options)]
                if days_until >= 8 and idx > 0:
                    chunk = 90
                if is_today and remaining_free_min is not None and remaining_free_min < 180:
                    chunk = min(chunk, 75)
                if is_today and s == len(session_specs) - 1:
                    chunk = min(chunk, 45)
                    stage = stages.get(
                        "evening_preview",
                        _stage_for(tgt, day, hebrew, seed + idx + s, slot),
                    )
                else:
                    stage = _stage_for(tgt, day, hebrew, seed + idx + s, slot)

            chunk = min(int(chunk), budget - used)
            # Today may use shorter blocks to fill remaining evening gaps
            if chunk < 40:
                continue
            if chunk < 60 and not is_today and not (tgt.kind == "exam" and days_until <= 1):
                continue
            demand.append(
                _Demand(
                    tgt,
                    chunk,
                    stage,
                    _topic_for(tgt, day, seed, slot),
                    hard_deadline=tgt.due if tgt.kind == "exam" else None,
                )
            )
            used += chunk
            slot += 1

    return demand


# ---------------------------------------------------------------------------
# Fixed calendar events
# ---------------------------------------------------------------------------


def _exam_recovery_minutes(event: ClassifiedCalendarEvent) -> int:
    """Default 75m after a normal exam; up to 120m for long/demanding exams."""
    start = _aware(event.start)
    end = _aware(event.end) if event.end else start + timedelta(hours=1)
    duration_h = max((end - start).total_seconds() / 3600.0, 0.5)
    if duration_h > 2.5:
        return 120
    if duration_h > 2:
        return 105
    return 75


def _exam_recovery_blocks(
    events: list[ClassifiedCalendarEvent],
    day: date,
    tz,
    hebrew: bool,
    *,
    now: datetime | None = None,
) -> list[_Placed]:
    """Visible recovery after exams: travel home + mental break (lunch stays separate)."""
    placed: list[_Placed] = []
    lunch_start = datetime.combine(day, _LUNCH[0], tzinfo=tz)
    for event in events:
        if event.category != EventCategory.EXAM:
            continue
        start = _aware(event.start)
        end = _aware(event.end) if event.end else start + timedelta(hours=1)
        if start.date() != day and end.date() != day:
            continue
        rec_end = end + timedelta(minutes=_exam_recovery_minutes(event))
        # Prefer a coherent block that ends exactly at lunch when lunch follows soon.
        if end < lunch_start <= rec_end + timedelta(minutes=_GAP_MERGE_MIN):
            rec_end = max(rec_end, lunch_start)
            if lunch_start - end <= timedelta(minutes=120):
                rec_end = lunch_start
        if now is not None and rec_end <= now:
            continue
        block_start = end
        if now is not None and block_start < now:
            block_start = now
        if block_start >= rec_end:
            continue
        placed.append(
            _Placed(
                start=block_start,
                end=rec_end,
                kind="recovery",
                title="Recovery / travel home" if not hebrew else "התאוששות / חזרה הביתה",
                action=(
                    "Travel home and take a real mental break. No studying yet."
                    if not hebrew
                    else "התאוששות_ACTION"
                ),
                reason="",
                event_id=event.id,
                label="Recovery",
                category="Exam",
            )
        )
    return placed


def _fixed_events_for_day(
    events: list[ClassifiedCalendarEvent],
    day: date,
    tz,
    *,
    now: datetime | None = None,
) -> list[_Placed]:
    placed: list[_Placed] = []
    for event in events:
        start = _aware(event.start)
        end = _aware(event.end) if event.end else start + timedelta(hours=1)
        if event.is_all_day:
            if start.date() != day:
                continue
            start = datetime.combine(day, time(9, 0), tzinfo=tz)
            end = datetime.combine(day, time(10, 0), tzinfo=tz)
        else:
            if start.date() != day and end.date() != day:
                day_start = datetime.combine(day, time(0, 0), tzinfo=tz)
                day_end = datetime.combine(day, time(23, 59), tzinfo=tz)
                if end <= day_start or start >= day_end:
                    continue
                start = max(start, day_start)
                end = min(end, day_end)
            elif start.date() != day:
                continue

        if now is not None and day == now.date() and end <= now:
            continue

        cat = event.category.value if event.category else "Other"
        desc = (event.description or "").strip()
        action = desc.splitlines()[0] if desc else f"Fixed calendar event ({cat})"
        placed.append(
            _Placed(
                start=start,
                end=end,
                kind="calendar",
                title=event.title,
                action=action,
                reason="",
                event_id=event.id,
                category=cat,
                label="Calendar event",
            )
        )
    return placed


# ---------------------------------------------------------------------------
# Free time
# ---------------------------------------------------------------------------


def _event_buffer_min(event: ClassifiedCalendarEvent) -> int:
    if (event.location or "").strip():
        return 45
    if event.category == EventCategory.EXAM:
        return 30
    return 30


def _free_slots_for_day(
    day: date,
    now: datetime,
    blockers: list[ClassifiedCalendarEvent],
    *,
    today_start: datetime,
    seed: int = 0,
) -> list[_Interval]:
    tz = now.tzinfo
    day_start = datetime.combine(day, _DAY_START, tzinfo=tz)
    day_end = datetime.combine(day, _DAY_END, tzinfo=tz)

    busy = _busy_with_buffers(day, blockers, tz)
    lunch_start = datetime.combine(day, _LUNCH[0], tzinfo=tz)
    lunch_end = datetime.combine(day, _LUNCH[1], tzinfo=tz)
    # Skip lunch reservation when recovery/busy already overlaps the lunch window
    if not any(b.start < lunch_end and b.end > lunch_start for b in busy):
        busy.append(_Interval(lunch_start, lunch_end))
    dinner_start = datetime.combine(day, _DINNER[0], tzinfo=tz)
    dinner_end = datetime.combine(day, _DINNER[1], tzinfo=tz)
    if not any(b.start < dinner_end and b.end > dinner_start for b in busy):
        busy.append(_Interval(dinner_start, dinner_end))

    merged = _merge(busy)
    window = _Interval(day_start, day_end)
    if day == now.date():
        earliest = _aware(today_start)
        if earliest.tzinfo != tz and tz is not None:
            earliest = earliest.astimezone(tz)
        if earliest >= window.end:
            return []
        if earliest > window.start:
            window = _Interval(earliest, window.end)

    return [g for g in _subtract(window, merged) if g.duration_min() >= 30]


def _busy_with_buffers(
    day: date, events: list[ClassifiedCalendarEvent], tz
) -> list[_Interval]:
    busy: list[_Interval] = []
    for event in events:
        start = _aware(event.start)
        end = _aware(event.end) if event.end else start + timedelta(hours=1)
        if event.is_all_day:
            if start.date() == day:
                busy.append(
                    _Interval(
                        datetime.combine(day, time(8, 0), tzinfo=tz),
                        datetime.combine(day, time(9, 0), tzinfo=tz),
                    )
                )
            continue
        buf = timedelta(minutes=_event_buffer_min(event))
        buffered_start = start - buf
        day_start = datetime.combine(day, time(0, 0), tzinfo=tz)
        day_end = datetime.combine(day, time(23, 59), tzinfo=tz)
        clamped_start = max(buffered_start, day_start)
        clamped_end = min(end, day_end)
        if clamped_start < clamped_end and not (
            end <= day_start or start >= day_end + timedelta(minutes=1)
        ):
            if start.date() == day or end.date() == day or (
                start < day_end and end > day_start
            ):
                busy.append(_Interval(clamped_start, clamped_end))
                # Post-exam recovery: no studying until travel/lunch/mental break ends
                if event.category == EventCategory.EXAM:
                    rec_min = _exam_recovery_minutes(event)
                    rec_end = end + timedelta(minutes=rec_min)
                    busy.append(_Interval(end, min(rec_end, day_end + timedelta(minutes=1))))
    return busy


def ceil_to_15_minutes(dt: datetime) -> datetime:
    dt = _aware(dt).replace(second=0, microsecond=0)
    rem = dt.minute % 15
    if rem == 0:
        return dt
    return dt + timedelta(minutes=(15 - rem))


def _merge(intervals: list[_Interval]) -> list[_Interval]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda i: i.start)
    out = [ordered[0]]
    for cur in ordered[1:]:
        last = out[-1]
        if cur.start <= last.end:
            out[-1] = _Interval(last.start, max(last.end, cur.end))
        else:
            out.append(cur)
    return out


def _subtract(window: _Interval, busy: list[_Interval]) -> list[_Interval]:
    gaps: list[_Interval] = []
    cursor = window.start
    for b in busy:
        if b.end <= cursor or b.start >= window.end:
            continue
        if b.start > cursor:
            gaps.append(_Interval(cursor, min(b.start, window.end)))
        cursor = max(cursor, b.end)
        if cursor >= window.end:
            break
    if cursor < window.end:
        gaps.append(_Interval(cursor, window.end))
    return [g for g in gaps if g.end > g.start]


# ---------------------------------------------------------------------------
# Pack study into free slots
# ---------------------------------------------------------------------------


def _break_for(study_min: int) -> int:
    if study_min >= 150:
        return 25
    if study_min >= 120:
        return 20
    if study_min >= 90:
        return 15
    return 10


def _gap_cursor(gap: _Interval, placed: list[_Placed]) -> datetime | None:
    cursor = gap.start
    for p in sorted(placed, key=lambda x: x.start):
        if p.end <= cursor or p.start >= gap.end:
            continue
        if p.start > cursor:
            break
        cursor = max(cursor, p.end)
    if cursor >= gap.end:
        return None
    if int((gap.end - cursor).total_seconds() // 60) < 20:
        return None
    return cursor


def _fill_day(
    free: list[_Interval],
    demand: list[_Demand],
    *,
    day: date,
    hebrew: bool,
    seed: int,
) -> list[_Placed]:
    """Pack study across the whole day — do not dump all demand into the first gap."""
    placed: list[_Placed] = []
    gaps = [g for g in free if g.duration_min() >= 20]
    q = list(demand)
    if not gaps or not q:
        return placed

    total_demand = sum(max(d.minutes, 0) for d in q)
    n_gaps = len(gaps)
    soft_cap = max(90, (total_demand + n_gaps - 1) // n_gaps + 30)
    di = 0
    used_actions: set[str] = set()

    def study_minutes_in_gap(gap: _Interval) -> int:
        total = 0
        for p in placed:
            if p.kind != "study":
                continue
            if p.end <= gap.start or p.start >= gap.end:
                continue
            total += int(
                (min(p.end, gap.end) - max(p.start, gap.start)).total_seconds() // 60
            )
        return total

    progress = True
    while q and progress:
        progress = False
        for gi, gap in enumerate(gaps):
            if not q:
                break
            if study_minutes_in_gap(gap) >= soft_cap and any(
                study_minutes_in_gap(g) < soft_cap for g in gaps
            ):
                continue
            cursor = _gap_cursor(gap, placed)
            if cursor is None:
                continue

            need = q[0]
            gap_end = gap.end
            if need.hard_deadline is not None:
                if cursor >= need.hard_deadline:
                    q.pop(0)
                    progress = True
                    continue
                gap_end = min(gap_end, need.hard_deadline)

            remaining_gap = int((gap_end - cursor).total_seconds() // 60)
            if remaining_gap < 20:
                continue

            want = need.minutes
            later_gaps = sum(
                1 for g in gaps[gi + 1 :] if _gap_cursor(g, placed) is not None
            )
            if later_gaps and want > 90 and remaining_gap > 120:
                want = min(want, max(90, remaining_gap // 2))

            duration = _pick_duration(remaining_gap, want, seed + di)
            if need.target.kind == "exam" and need.target.due.date() == day:
                duration = min(max(20, duration), 45)

            end = cursor + timedelta(minutes=duration)
            if end > gap_end:
                end = gap_end
                duration = int((end - cursor).total_seconds() // 60)
            if duration < 20:
                continue
            if need.hard_deadline is not None and end > need.hard_deadline:
                end = need.hard_deadline
                duration = int((end - cursor).total_seconds() // 60)
                if duration < 20:
                    q.pop(0)
                    progress = True
                    continue

            stage = need.stage
            if stage in used_actions:
                alt = _stage_for(need.target, day, hebrew, seed + di + 3, di)
                if alt not in used_actions:
                    stage = alt
            used_actions.add(stage)

            action, reason = _content_for(need.target, stage, need.topic, day, hebrew)
            placed.append(
                _Placed(
                    start=cursor,
                    end=end,
                    kind="study",
                    title=need.target.event.title,
                    action=action,
                    reason=reason,
                    event_id=need.target.event.id,
                    phase=stage,
                    label="Study session",
                )
            )
            need.minutes -= duration
            di += 1
            progress = True
            if need.minutes <= 20:
                q.pop(0)
            cursor = end

            br = _break_for(duration)
            # Avoid a short break that would sit next to lunch/dinner with a junk gap.
            meal_edges = (
                datetime.combine(day, _LUNCH[0], tzinfo=cursor.tzinfo),
                datetime.combine(day, _DINNER[0], tzinfo=cursor.tzinfo),
            )
            near_meal = any(
                0 <= (edge - cursor).total_seconds() / 60.0 < (br + _GAP_MERGE_MIN)
                for edge in meal_edges
            )
            if (
                q
                and not near_meal
                and cursor + timedelta(minutes=br + 45) <= gap_end
            ):
                br_end = cursor + timedelta(minutes=br)
                if need.hard_deadline is None or br_end <= need.hard_deadline:
                    placed.append(
                        _Placed(
                            start=cursor,
                            end=br_end,
                            kind="break",
                            title="Break" if not hebrew else "הפסקה",
                            action=(
                                "Short reset — water, stretch, no new material."
                                if not hebrew
                                else "הפסקה קצרה — מים, מתיחה, בלי חומר חדש."
                            ),
                            reason="",
                            label="Break",
                        )
                    )

    placed.sort(key=lambda p: p.start)
    return placed



def _insert_meal_markers(placed: list[_Placed], day: date, hebrew: bool, now: datetime | None = None) -> None:
    if not placed:
        return
    tz = placed[0].start.tzinfo
    studyish = [p for p in placed if p.kind in ("study", "calendar", "recovery")]
    if not studyish:
        return

    def has_meal(name_en: str, name_he: str) -> bool:
        return any(
            p.kind == "meal" and (name_en in p.title or name_he in p.title)
            for p in placed
        )

    before_lunch = any(p.end.time() <= _LUNCH[0] for p in studyish)
    after_lunch = any(p.start.time() >= _LUNCH[1] for p in studyish)
    if before_lunch and after_lunch and not has_meal("Lunch", "צהריים"):
        lunch_start = datetime.combine(day, _LUNCH[0], tzinfo=tz)
        lunch_end = datetime.combine(day, _LUNCH[1], tzinfo=tz)
        if now is not None and lunch_end <= now:
            pass
        elif not any(
            p.kind in ("calendar", "recovery") and p.start < lunch_end and p.end > lunch_start
            for p in placed
        ):
            placed.append(
                _Placed(
                    start=lunch_start,
                    end=lunch_end,
                    kind="meal",
                    title="Lunch" if not hebrew else "ארוחת צהריים",
                    action="45–60 minute lunch break." if not hebrew else "הפסקת צהריים.",
                    reason="",
                    label="Meal",
                )
            )

    before_dinner = any(p.end.time() <= _DINNER[0] for p in studyish)
    after_dinner = any(p.start.time() >= _DINNER[1] for p in studyish)
    if before_dinner and after_dinner and not has_meal("Dinner", "ערב"):
        dinner_start = datetime.combine(day, _DINNER[0], tzinfo=tz)
        dinner_end = datetime.combine(day, _DINNER[1], tzinfo=tz)
        if now is not None and dinner_end <= now:
            pass
        elif not any(
            p.kind in ("calendar", "recovery") and p.start < dinner_end and p.end > dinner_start
            for p in placed
        ):
            placed.append(
                _Placed(
                    start=dinner_start,
                    end=dinner_end,
                    kind="meal",
                    title="Dinner" if not hebrew else "ארוחת ערב",
                    action="30–45 minute dinner break." if not hebrew else "הפסקת ערב.",
                    reason="",
                    label="Meal",
                )
            )


def _pick_duration(available: int, want: int, seed: int) -> int:
    preferred = [150, 120, 90, 60]
    rot = seed % 3
    preferred = preferred[rot:] + preferred[:rot]
    for dur in preferred:
        if dur <= available and dur <= max(want, 90) + 30:
            return min(dur, available)
    for dur in preferred:
        if dur <= available:
            return dur
    return max(20, min(available, want))


# ---------------------------------------------------------------------------
# Timeline normalization + validation (engine-owned geometry)
# ---------------------------------------------------------------------------


def _is_rest_like(block: _Placed) -> bool:
    if block.kind in _REST_KINDS:
        return True
    title = (block.title or "").lower()
    return any(
        token in title
        for token in (
            "break",
            "recovery",
            "lunch",
            "dinner",
            "travel",
            "free time",
            "flexible",
            "personal time",
            "הפסקה",
            "התאוששות",
            "צהריים",
            "ערב",
        )
    )


def _gap_minutes(a: _Placed, b: _Placed) -> float:
    return (b.start - a.end).total_seconds() / 60.0


def _merge_rest_pair(a: _Placed, b: _Placed, *, hebrew: bool) -> _Placed:
    """Merge two rest-like blocks into one coherent recovery/meal/break."""
    start = min(a.start, b.start)
    end = max(a.end, b.end)
    kinds = {a.kind, b.kind}
    if "meal" in kinds and "recovery" in kinds:
        # Keep recovery up to meal start; caller should not merge meal+recovery.
        # Prefer the meal title if both are meals.
        pass
    if a.kind == "meal" and b.kind == "meal":
        title = a.title if "Lunch" in a.title or "צהריים" in a.title else b.title
        return _Placed(
            start=start,
            end=end,
            kind="meal",
            title=title,
            action=a.action or b.action,
            reason="",
            label="Meal",
        )
    if "recovery" in kinds or a.kind == "break" or b.kind == "break":
        return _Placed(
            start=start,
            end=end,
            kind="recovery",
            title=(
                "Recovery / travel home"
                if not hebrew
                else "התאוששות / חזרה הביתה"
            ),
            action=(
                "Travel home and take a real mental break. No studying yet."
                if not hebrew
                else "התאוששות_ACTION"
            ),
            reason="",
            event_id=a.event_id or b.event_id,
            label="Recovery",
            category=a.category or b.category or "Exam",
        )
    return _Placed(
        start=start,
        end=end,
        kind="break",
        title="Break" if not hebrew else "הפסקה",
        action=a.action or b.action,
        reason="",
        label="Break",
    )


def _snap_recovery_to_meals(blocks: list[_Placed], day: date, hebrew: bool) -> list[_Placed]:
    """Ensure recovery abuts lunch/dinner when a short gap would otherwise appear."""
    if not blocks:
        return blocks
    tz = blocks[0].start.tzinfo
    lunch_start = datetime.combine(day, _LUNCH[0], tzinfo=tz)
    out = sorted(blocks, key=lambda p: p.start)
    changed: list[_Placed] = []
    for p in out:
        if p.kind != "recovery":
            changed.append(p)
            continue
        # Extend recovery to lunch start when the silent gap would be < 30 min
        if p.end < lunch_start:
            gap = (lunch_start - p.end).total_seconds() / 60.0
            if 0 < gap < _GAP_MERGE_MIN:
                p = _Placed(
                    start=p.start,
                    end=lunch_start,
                    kind=p.kind,
                    title=p.title
                    if "travel" in (p.title or "").lower()
                    or "חזרה" in (p.title or "")
                    else (
                        "Recovery / travel home"
                        if not hebrew
                        else "התאוששות / חזרה הביתה"
                    ),
                    action=p.action,
                    reason=p.reason,
                    event_id=p.event_id,
                    phase=p.phase,
                    category=p.category,
                    label=p.label,
                )
        changed.append(p)
    return changed


def _merge_near_rest_blocks(blocks: list[_Placed], *, hebrew: bool) -> list[_Placed]:
    """Merge overlapping / touching / <30min-apart rest-like blocks (not meal+recovery)."""
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda p: (p.start, p.end))
    out: list[_Placed] = [ordered[0]]
    for cur in ordered[1:]:
        prev = out[-1]
        gap = _gap_minutes(prev, cur)
        both_rest = _is_rest_like(prev) and _is_rest_like(cur)
        meal_recovery = {prev.kind, cur.kind} == {"meal", "recovery"} or (
            prev.kind == "recovery" and cur.kind == "meal"
        ) or (prev.kind == "meal" and cur.kind == "recovery")
        if both_rest and meal_recovery and gap <= 0:
            # Overlap recovery into lunch — clip recovery to meal start
            if prev.kind == "recovery" and cur.kind == "meal":
                if prev.end > cur.start:
                    out[-1] = _Placed(
                        start=prev.start,
                        end=cur.start,
                        kind=prev.kind,
                        title=prev.title,
                        action=prev.action,
                        reason=prev.reason,
                        event_id=prev.event_id,
                        phase=prev.phase,
                        category=prev.category,
                        label=prev.label,
                    )
                    if out[-1].end <= out[-1].start:
                        out.pop()
                out.append(cur)
                continue
            if prev.kind == "meal" and cur.kind == "recovery":
                out.append(cur)
                continue
        if both_rest and meal_recovery and 0 < gap < _GAP_MERGE_MIN:
            # Extend recovery to touch meal — keep two labelled cards, no blank gap
            if prev.kind == "recovery" and cur.kind == "meal":
                out[-1] = _Placed(
                    start=prev.start,
                    end=cur.start,
                    kind="recovery",
                    title=(
                        "Recovery / travel home"
                        if not hebrew
                        else "התאוששות / חזרה הביתה"
                    ),
                    action=prev.action,
                    reason=prev.reason,
                    event_id=prev.event_id,
                    label="Recovery",
                    category=prev.category or "Exam",
                )
                out.append(cur)
                continue
            if prev.kind == "meal" and cur.kind == "recovery":
                out.append(cur)
                continue
        if both_rest and not meal_recovery and gap < _GAP_MERGE_MIN:
            out[-1] = _merge_rest_pair(prev, cur, hebrew=hebrew)
            continue
        if gap < 0 and prev.kind == "calendar":
            # Never shrink fixed calendar events — shift/drop overlapping soft blocks
            if cur.kind == "calendar":
                out.append(cur)
            elif cur.end > prev.end:
                out.append(
                    _Placed(
                        start=max(cur.start, prev.end),
                        end=cur.end,
                        kind=cur.kind,
                        title=cur.title,
                        action=cur.action,
                        reason=cur.reason,
                        event_id=cur.event_id,
                        phase=cur.phase,
                        category=cur.category,
                        label=cur.label,
                    )
                )
            continue
        if gap < 0 and cur.kind != "calendar" and prev.kind != "calendar":
            out[-1] = _Placed(
                start=prev.start,
                end=max(prev.end, cur.end),
                kind=prev.kind if prev.kind != "break" else cur.kind,
                title=prev.title,
                action=prev.action or cur.action,
                reason=prev.reason or cur.reason,
                event_id=prev.event_id or cur.event_id,
                phase=prev.phase or cur.phase,
                category=prev.category or cur.category,
                label=prev.label or cur.label,
            )
            continue
        out.append(cur)
    return [p for p in out if p.end > p.start]


def _drop_redundant_breaks_before_rest(
    blocks: list[_Placed], *, hebrew: bool = False
) -> list[_Placed]:
    """
    Remove/replace breaks that sit before meal/recovery.

    A short BREAK then a silent gap then MEAL is invalid — turn it into one
    recovery block that abuts the meal (or drop the break when gap < 30).
    """
    ordered = sorted(blocks, key=lambda p: p.start)
    out: list[_Placed] = []
    i = 0
    while i < len(ordered):
        block = ordered[i]
        if block.kind == "break" and i + 1 < len(ordered):
            nxt = ordered[i + 1]
            gap = _gap_minutes(block, nxt)
            if nxt.kind in ("meal", "recovery") and 0 <= gap < 90:
                # No study/calendar between — coalesce into recovery until meal
                out.append(
                    _Placed(
                        start=block.start,
                        end=nxt.start if nxt.kind == "meal" else max(block.end, nxt.end),
                        kind="recovery",
                        title=(
                            "Recovery / travel home"
                            if not hebrew
                            else "התאוששות / חזרה הביתה"
                        ),
                        action=(
                            "Travel home and take a real mental break. No studying yet."
                            if not hebrew
                            else "התאוששות_ACTION"
                        ),
                        reason="",
                        label="Recovery",
                        category="Exam",
                    )
                )
                if nxt.kind == "recovery":
                    i += 2
                    continue
                i += 1
                continue
            if gap < _GAP_MERGE_MIN and _is_rest_like(nxt):
                i += 1
                continue
        out.append(block)
        i += 1
    return out


def _active_window(day: date, now: datetime, blocks: list[_Placed]) -> _Interval:
    tz = now.tzinfo
    start = datetime.combine(day, _DAY_START, tzinfo=tz)
    end = datetime.combine(day, _DAY_END, tzinfo=tz)
    if day == now.date():
        start = max(start, ceil_to_15_minutes(now))
    if blocks:
        start = min(start, min(b.start for b in blocks))
        # Keep day start floor for future days
        if day != now.date():
            start = datetime.combine(day, _DAY_START, tzinfo=tz)
    return _Interval(start, end)


def _unexplained_gaps(blocks: list[_Placed], window: _Interval) -> list[_Interval]:
    ordered = sorted(blocks, key=lambda p: p.start)
    busy = _merge([_Interval(b.start, b.end) for b in ordered])
    return [
        g
        for g in _subtract(window, busy)
        if g.duration_min() >= _GAP_MERGE_MIN
    ]


def _fill_unexplained_gaps(
    blocks: list[_Placed],
    gaps: list[_Interval],
    *,
    day: date,
    hebrew: bool,
    remaining_workload_min: int,
    demand: list[_Demand],
    seed: int,
) -> list[_Placed]:
    """Fill useful free windows; label intentional free time when workload is done."""
    out = list(blocks)
    workload_left = remaining_workload_min
    di = 0
    for gap in gaps:
        minutes = gap.duration_min()
        if minutes < _LIGHT_TASK_MIN:
            continue
        if workload_left >= 20 and demand:
            need = next((d for d in demand if d.minutes > 0), None)
            if need is None:
                workload_left = 0
            else:
                if minutes >= _STUDY_FILL_MIN:
                    duration = min(
                        _MAX_FOCUS_MIN,
                        max(_STUDY_FILL_MIN, min(minutes, need.minutes, 90)),
                    )
                    stage = need.stage
                    if minutes < 60:
                        stage = "flashcards" if not hebrew else need.stage
                    action, reason = _content_for(
                        need.target, stage, need.topic, day, hebrew
                    )
                    if minutes < _STUDY_FILL_MIN:
                        action = (
                            "Light task — flashcards, organize notes, or plan tomorrow."
                            if not hebrew
                            else "משימה קלה — כרטיסיות, ארגון רשימות או תכנון מחר."
                        )
                    end = gap.start + timedelta(minutes=duration)
                    if need.hard_deadline and end > need.hard_deadline:
                        end = need.hard_deadline
                        duration = int((end - gap.start).total_seconds() // 60)
                    if duration >= _LIGHT_TASK_MIN and (
                        need.hard_deadline is None or gap.start < need.hard_deadline
                    ):
                        out.append(
                            _Placed(
                                start=gap.start,
                                end=end,
                                kind="study",
                                title=need.target.event.title,
                                action=action,
                                reason=reason,
                                event_id=need.target.event.id,
                                phase=stage,
                                label="Study session",
                            )
                        )
                        need.minutes -= duration
                        workload_left = max(0, workload_left - duration)
                        di += 1
                        continue
                elif minutes >= _LIGHT_TASK_MIN:
                    end = gap.start + timedelta(minutes=min(minutes, 40))
                    out.append(
                        _Placed(
                            start=gap.start,
                            end=end,
                            kind="study",
                            title=need.target.event.title,
                            action=(
                                "Light task — flashcards, organize notes, or review mistakes."
                                if not hebrew
                                else "משימה קלה — כרטיסיות, ארגון או חזרה על טעויות."
                            ),
                            reason="",
                            event_id=need.target.event.id,
                            phase="flashcards",
                            label="Study session",
                        )
                    )
                    used = int((end - gap.start).total_seconds() // 60)
                    need.minutes -= used
                    workload_left = max(0, workload_left - used)
                    continue
        # Do not invent filler cards when workload is complete — leave transition time blank.
    out.sort(key=lambda p: p.start)
    return out[:_MAX_BLOCKS_PER_DAY]


def _split_oversized_focus(blocks: list[_Placed], *, hebrew: bool) -> list[_Placed]:
    """Ensure focused study blocks do not exceed 150 minutes without a break."""
    out: list[_Placed] = []
    for b in blocks:
        if b.kind != "study":
            out.append(b)
            continue
        minutes = int((b.end - b.start).total_seconds() // 60)
        if minutes <= _MAX_FOCUS_MIN:
            out.append(b)
            continue
        cursor = b.start
        remaining = minutes
        part = 0
        while remaining > 0:
            chunk = min(_MAX_FOCUS_MIN, remaining)
            chunk_end = cursor + timedelta(minutes=chunk)
            out.append(
                _Placed(
                    start=cursor,
                    end=chunk_end,
                    kind="study",
                    title=b.title,
                    action=b.action,
                    reason=b.reason,
                    event_id=b.event_id,
                    phase=b.phase,
                    label=b.label,
                )
            )
            cursor = chunk_end
            remaining -= chunk
            part += 1
            if remaining >= 45:
                br = _break_for(chunk)
                out.append(
                    _Placed(
                        start=cursor,
                        end=cursor + timedelta(minutes=br),
                        kind="break",
                        title="Break" if not hebrew else "הפסקה",
                        action=(
                            "Short reset — water, stretch, no new material."
                            if not hebrew
                            else "הפסקה קצרה — מים, מתיחה, בלי חומר חדש."
                        ),
                        reason="",
                        label="Break",
                    )
                )
                cursor += timedelta(minutes=br)
                remaining -= br
    out.sort(key=lambda p: p.start)
    return out


def validate_day_timeline(
    blocks: list[_Placed],
    *,
    day: date,
    now: datetime,
    remaining_workload_min: int = 0,
) -> list[str]:
    """Return human-readable validation errors (empty means OK)."""
    errors: list[str] = []
    ordered = sorted(blocks, key=lambda p: p.start)
    if [p.start for p in blocks] != [p.start for p in ordered]:
        errors.append("blocks_not_sorted")
    for p in ordered:
        if p.end <= p.start:
            errors.append("negative_or_zero_duration")
        if p.kind == "study" and day == now.date() and p.start < now:
            errors.append("study_in_past")
        if p.kind == "study":
            mins = int((p.end - p.start).total_seconds() // 60)
            if mins > _MAX_FOCUS_MIN:
                errors.append("focus_block_exceeds_150")
    for a, b in zip(ordered, ordered[1:]):
        if a.end > b.start:
            errors.append("overlap")
        gap = _gap_minutes(a, b)
        if (
            remaining_workload_min >= 20
            and gap >= _GAP_MERGE_MIN
            and a.kind != "calendar"
            and b.kind != "calendar"
        ):
            # Unexplained gap inside active window when work remains
            window = _active_window(day, now, ordered)
            if a.end >= window.start and b.start <= window.end:
                errors.append("unexplained_gap")
        if _is_rest_like(a) and _is_rest_like(b):
            if {a.kind, b.kind} != {"meal", "recovery"} and gap < _GAP_MERGE_MIN:
                if not (
                    a.kind == "recovery"
                    and b.kind == "meal"
                    and abs(gap) < 0.01
                ):
                    errors.append("redundant_adjacent_rest")
            if a.kind == "recovery" and b.kind == "meal" and gap >= _GAP_MERGE_MIN:
                errors.append("recovery_meal_gap")
    return sorted(set(errors))


def _blocks_fingerprint(blocks: list[_Placed]) -> str:
    parts = [
        f"{b.start.isoformat()}|{b.end.isoformat()}|{b.kind}|{b.title}"
        for b in sorted(blocks, key=lambda p: p.start)
    ]
    return "\n".join(parts)


def _normalize_day_timeline(
    blocks: list[_Placed],
    *,
    day: date,
    now: datetime,
    hebrew: bool,
    remaining_workload_min: int,
    demand: list[_Demand],
    seed: int,
) -> list[_Placed]:
    """
    Bounded deterministic post-pass: sort, merge rest junk, fill useful gaps once.

    Validation is non-mutating. Repair is attempted at most twice.
    On repeated fingerprints or block-cap, keep the last valid schedule.
    """
    if not blocks:
        return []

    original = sorted(blocks, key=lambda p: p.start)
    out = list(original)
    seen: set[str] = set()
    t0 = pytime.perf_counter()

    for pass_i in range(_MAX_NORMALIZE_PASSES):
        fp = _blocks_fingerprint(out)
        if fp in seen:
            logger.info(
                "stage=normalization_stop reason=repeated_fingerprint day=%s pass=%s",
                day.isoformat(),
                pass_i,
            )
            break
        seen.add(fp)

        calendar = [p for p in out if p.kind == "calendar"]
        soft = [p for p in out if p.kind != "calendar"]
        soft = _snap_recovery_to_meals(soft, day, hebrew)
        soft = _drop_redundant_breaks_before_rest(soft, hebrew=hebrew)
        merged = _merge_near_rest_blocks(soft + calendar, hebrew=hebrew)
        calendar = [p for p in merged if p.kind == "calendar"]
        soft = [p for p in merged if p.kind != "calendar"]
        out = sorted(calendar + soft, key=lambda p: p.start)

        # Fill each free interval at most once per pass (no recursive sub-gap fill).
        if pass_i == 0 and remaining_workload_min >= 20:
            window = _active_window(day, now, out)
            gaps = _unexplained_gaps(out, window)
            if gaps:
                out = _fill_unexplained_gaps(
                    out,
                    gaps,
                    day=day,
                    hebrew=hebrew,
                    remaining_workload_min=remaining_workload_min,
                    demand=demand,
                    seed=seed,
                )
                out = _drop_redundant_breaks_before_rest(out, hebrew=hebrew)
                out = _merge_near_rest_blocks(out, hebrew=hebrew)

        out = _split_oversized_focus(out, hebrew=hebrew)
        out = _merge_near_rest_blocks(out, hebrew=hebrew)
        out = sorted(out, key=lambda p: p.start)[:_MAX_BLOCKS_PER_DAY]

        cleaned: list[_Placed] = []
        for p in out:
            if day == now.date() and p.end <= now:
                continue
            if p.kind == "study" and day == now.date() and p.start < now:
                p = _Placed(
                    start=ceil_to_15_minutes(now),
                    end=p.end,
                    kind=p.kind,
                    title=p.title,
                    action=p.action,
                    reason=p.reason,
                    event_id=p.event_id,
                    phase=p.phase,
                    category=p.category,
                    label=p.label,
                )
                if p.end <= p.start:
                    continue
            cleaned.append(p)
        out = cleaned

        if _blocks_fingerprint(out) == fp:
            break

    # Non-mutating validate + bounded repair
    workload_left = sum(max(d.minutes, 0) for d in demand)
    for repair_i in range(_MAX_REPAIR_PASSES + 1):
        errors = validate_day_timeline(
            out, day=day, now=now, remaining_workload_min=workload_left
        )
        hard = {
            e
            for e in errors
            if e
            in {
                "overlap",
                "negative_or_zero_duration",
                "recovery_meal_gap",
                "redundant_adjacent_rest",
            }
        }
        if not hard:
            break
        if repair_i >= _MAX_REPAIR_PASSES:
            logger.warning(
                "stage=normalization_repair_exhausted day=%s errors=%s "
                "reverting_to_pre_normalize",
                day.isoformat(),
                sorted(hard),
            )
            out = original
            break
        out = _merge_near_rest_blocks(out, hebrew=hebrew)
        out = _snap_recovery_to_meals(out, day, hebrew)
        out = _drop_redundant_breaks_before_rest(out, hebrew=hebrew)
        out = sorted(out, key=lambda p: p.start)[:_MAX_BLOCKS_PER_DAY]

    logger.info(
        "stage=normalization_completed duration_ms=%.0f day=%s block_count=%s",
        (pytime.perf_counter() - t0) * 1000,
        day.isoformat(),
        len(out),
    )
    return out


def _content_for(
    target: _Target,
    stage: str,
    topic: str | None,
    day: date,
    hebrew: bool,
) -> tuple[str, str]:
    days_until = (target.due.date() - day).days
    title = target.event.title

    rag_bundle = _topic_bundle(target.topics, topic)

    if hebrew:
        if target.kind == "exam" and days_until <= 0:
            focus = topic or title
            return (
                f"חזרה קצרה על {focus}: נוסחאות וסיכום. בלי חומר חדש. השאירי זמן הגעה.",
                "יום מבחן — חזרה קלה בלבד.",
            )
        if topic:
            return _action_with_topic(stage, topic, hebrew=True, bundle=rag_bundle), ""
        return f"{stage}.", ""

    if target.kind == "exam" and days_until <= 0:
        focus = topic or title
        return (
            f"Quick review of {focus}: formulas and summary notes. "
            "No new material. Leave travel buffer.",
            "Exam day — short final review only.",
        )
    if topic:
        return _action_with_topic(stage, topic, hebrew=False, bundle=rag_bundle), ""
    return f"{stage}.", ""


def _topic_bundle(topics: list[str], current: str | None) -> str:
    """Prefer a short multi-topic study line when RAG supplied several topics."""
    clean = [t.strip() for t in (topics or []) if (t or "").strip()]
    if len(clean) >= 2:
        return ", ".join(clean[:4])
    return (current or "").strip()


def _action_with_topic(
    stage: str,
    topic: str,
    *,
    hebrew: bool,
    bundle: str | None = None,
) -> str:
    """Turn a pedagogical stage + concrete topic into a specific study action.

    Timing/ordering stay in the engine; this only shapes WHAT to study.
    """
    focus = (bundle or topic or "").strip() or topic
    stage_l = (stage or "").lower()
    if hebrew:
        if any(k in stage_l for k in ("תרגיל", "שאלות", "מבחן לדוגמה", "פתרון")):
            return f"תרגול: {focus}"
        if "כרטיס" in stage_l:
            return f"כרטיסיות על {focus}"
        if "נוסח" in stage_l:
            return f"חזרה על נוסחאות: {focus}"
        if "סיכום" in stage_l:
            return f"סיכום: {focus}"
        if "שליפה" in stage_l or "בעל פה" in stage_l:
            return f"הסבר בעל פה: {focus}"
        if "טעויות" in stage_l or "חלש" in stage_l:
            return f"חיזוק נקודות חלשות: {focus}"
        return f"לימוד: {focus}"

    if any(k in stage_l for k in ("practice", "questions", "mock", "solve")):
        return f"Practice: {focus}"
    if "flashcard" in stage_l:
        return f"Drill flashcards: {focus}"
    if "formula" in stage_l:
        return f"Review formulas: {focus}"
    if "summary" in stage_l:
        return f"Summarize: {focus}"
    if "oral" in stage_l or "recall" in stage_l:
        return f"Explain out loud: {focus}"
    if "mistake" in stage_l or "weak" in stage_l:
        return f"Revise weak points: {focus}"
    if "final" in stage_l or "mental" in stage_l or "preview" in stage_l:
        return f"Light review: {focus}"
    return f"Study: {focus}"


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def _priority_item(
    targets: list[_Target], hebrew: bool, now: datetime
) -> PriorityItem | None:
    if not targets:
        return None
    top = targets[0]
    days = max((top.due.date() - now.date()).days, 0)
    if hebrew:
        reason = (
            f"המבחן הקרוב — בעוד {days} ימים."
            if top.kind == "exam" and days
            else "המבחן היום — חזרה קצרה בלבד."
            if top.kind == "exam"
            else "המשימה הדחופה ביותר."
        )
    else:
        if top.kind == "exam":
            reason = (
                f"Nearest upcoming exam — {days} day(s) left."
                if days
                else "Exam is today — short final review only."
            )
        else:
            reason = "Closest deadline among remaining tasks."
    return PriorityItem(title=top.event.title, reason=reason)


def _summary(
    targets: list[_Target], daily: list[DailyPlan], hebrew: bool
) -> str:
    if not daily:
        return (
            "אין מספיק זמן פנוי ליצירת לוח לימודים בטווח שנבחר."
            if hebrew
            else "Not enough free time in the selected range to build a study schedule."
        )
    exams = [t for t in targets if t.kind == "exam"]
    if hebrew:
        if exams:
            n = exams[0]
            d = (n.due.date() - datetime.now().astimezone().date()).days
            return (
                f"תוכנית לפי הזמן הפנוי שלך. מיקוד נוכחי: {n.event.title}"
                + (f" (בעוד {d} ימים)." if d > 0 else " (היום — חזרה קצרה).")
            )
        return "תוכנית לימודים לפי לוח השנה והזמן הפנוי שלך."
    if exams:
        n = exams[0]
        d = (n.due.date() - datetime.now().astimezone().date()).days
        return (
            f"Schedule built from your free time. Current focus: {n.event.title}"
            + (f" ({d} days left)." if d > 0 else " (today — final review only).")
        )
    return "Schedule built from your free calendar gaps and upcoming deadlines."


def _coach_tips(
    targets: list[_Target],
    daily: list[DailyPlan],
    hebrew: bool,
    *,
    now: datetime,
) -> list[str]:
    if not targets:
        return []
    top = targets[0]
    days = (top.due.date() - now.date()).days
    tips: list[str] = []
    if not hebrew:
        if top.kind == "exam" and days > 1:
            tips.append(
                f"Prioritize {top.event.title} — {days} days remain before the exam."
            )
        elif top.kind == "exam" and days == 1:
            tips.append(
                f"{top.event.title} is tomorrow — timed practice then mistake review."
            )
        elif top.kind == "exam":
            tips.append("Exam day — short review only; no new material.")
        else:
            tips.append(f"Start with {top.event.title} — closest remaining deadline.")
        if len([t for t in targets if t.kind == "exam"]) >= 2:
            tips.append(
                f"After that, keep gradual prep for {targets[1].event.title}."
            )
    else:
        tips.append(f"המיקוד הנוכחי: {top.event.title}.")
    return tips[:3]


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt


def _already_ended(event: ClassifiedCalendarEvent, now: datetime) -> bool:
    end = event.end or (event.start + timedelta(hours=1))
    return _aware(end) <= _aware(now)


def plan_fingerprint(plan: StructuredStudyPlan) -> str:
    parts: list[str] = []
    for day in plan.daily_plan:
        for item in day.items:
            if (item.kind or "study") == "calendar":
                continue
            parts.append(
                f"{day.date}|{item.start_time}|{item.end_time}|{item.title}|{item.kind}"
            )
    return "\n".join(parts)

