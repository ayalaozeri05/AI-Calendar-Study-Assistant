"""AI study planning — deterministic schedule + optional LLM content polish."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from app.gateways.ollama_gateway import OllamaError, OllamaGateway
from app.schemas.brief_schema import PriorityItem, StructuredStudyPlan
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.study_scheduling_engine import StudySchedulingEngine, plan_fingerprint

logger = logging.getLogger(__name__)

_PRIORITY = (
    EventCategory.EXAM,
    EventCategory.ASSIGNMENT,
    EventCategory.PROJECT,
    EventCategory.STUDY,
    EventCategory.CLASS,
    EventCategory.MEETING,
    EventCategory.OTHER,
)


class AiRecommendationService:
    def __init__(
        self,
        ollama: OllamaGateway | None = None,
        engine: StudySchedulingEngine | None = None,
    ) -> None:
        self._ollama = ollama or OllamaGateway()
        self._engine = engine or StudySchedulingEngine()

    def suggest_focus(self, events: list[ClassifiedCalendarEvent]) -> str:
        plan, _, _ = self.generate_study_plan(
            events,
            start=datetime.now(timezone.utc).date(),
            end=datetime.now(timezone.utc).date(),
            force_fallback=True,
        )
        if plan.priority_item:
            return f"{plan.priority_item.title}: {plan.priority_item.reason}".strip(": ")
        if plan.tips:
            return plan.tips[0]
        return plan.summary or "Review your schedule and start with the earliest item."

    def generate_study_plan(
        self,
        events: list[ClassifiedCalendarEvent],
        *,
        start: date,
        end: date,
        force_fallback: bool = False,
        now: datetime | None = None,
        regenerate: bool = False,
        previous_plan: dict[str, Any] | None = None,
        variation_seed: int | None = None,
        planning_anchor: datetime | str | None = None,
    ) -> tuple[StructuredStudyPlan, str, str]:
        language = detect_language(events)
        now = now or datetime.now().astimezone()
        seed = int(variation_seed or 0)
        if regenerate and seed == 0:
            seed = int(now.timestamp()) % 10_000_000

        anchor_dt = _parse_anchor(planning_anchor)
        if regenerate and anchor_dt is None and previous_plan:
            anchor_dt = _parse_anchor(
                (previous_plan or {}).get("planning_anchor")
            )

        plan = self._engine.build(
            events,
            range_start=start,
            range_end=end,
            now=now,
            language=language,
            variation_seed=seed,
            planning_anchor=anchor_dt,
        )

        # If regenerate produced an identical skeleton, retry once with stronger seed
        # (same anchor / day boundaries — only content/order/duration varies)
        if regenerate and previous_plan:
            try:
                prev = StructuredStudyPlan.model_validate(previous_plan)
                if plan_fingerprint(plan) == plan_fingerprint(prev):
                    plan = self._engine.build(
                        events,
                        range_start=start,
                        range_end=end,
                        now=now,
                        language=language,
                        variation_seed=seed + 7919,
                        planning_anchor=anchor_dt or _parse_anchor(plan.planning_anchor),
                    )
            except Exception:
                pass

        ai_mode = "rule_based_fallback"
        if not force_fallback:
            try:
                if self._ollama.is_available():
                    plan = self._polish_with_ollama(
                        plan,
                        events,
                        language=language,
                        regenerate=regenerate,
                        previous_plan=previous_plan,
                    )
                    ai_mode = "ollama"
            except Exception as exc:
                logger.warning("ollama_content_polish_failed keeping_engine_plan err=%s", exc)

        return plan, format_plan_text(plan, language=language), ai_mode

    def _polish_with_ollama(
        self,
        plan: StructuredStudyPlan,
        events: list[ClassifiedCalendarEvent],
        *,
        language: str,
        regenerate: bool,
        previous_plan: dict[str, Any] | None,
    ) -> StructuredStudyPlan:
        skeleton = plan.model_dump()
        lang_rule = (
            "Write EVERY string in Hebrew. Do not mix English mid-sentence "
            "(course titles may stay as-is)."
            if language == "he"
            else "Write EVERY string in English. Do not mix Hebrew mid-sentence "
            "(course titles may stay as-is)."
        )
        regen_rule = ""
        if regenerate:
            regen_rule = (
                "\nCreate a meaningfully different study arrangement while preserving "
                "all fixed time constraints, calendar events, planning anchor, and daily "
                "boundaries. Do not change start_time/end_time/date/kind. "
                "You may vary action wording and tips only.\n"
                f"Previous plan (context only):\n{json.dumps(previous_plan or {}, ensure_ascii=False)[:3500]}\n"
            )
        prompt = f"""
You are a personal academic coach.

{lang_rule}
{regen_rule}

SCHEDULE TIMES are fixed by the engine.
Do NOT change start_time, end_time, date, kind, title, or item order.
Only improve: summary, priority_item.reason, tips, and study items' action + reason.

Make recommendations specific and stage-aware. Avoid repeating the same generic sentence every day.
Use description topics when present. Exam-day items stay short final-review (no new material).

Fixed schedule JSON:
{json.dumps(skeleton, ensure_ascii=False, indent=2)}

Event context:
{json.dumps(build_event_metadata(events, today=datetime.now().date()), ensure_ascii=False, indent=2)}

Return ONLY valid JSON with the same structure (no markdown).
""".strip()

        raw = self._ollama.invoke(prompt, temperature=0.35 if regenerate else 0.25)
        parsed = _parse_plan_json(raw)
        if parsed is None:
            raw2 = self._ollama.invoke(
                "Return ONLY valid JSON for the study plan. No markdown.\n\n"
                f"Previous reply:\n{raw[:2500]}",
                temperature=0.0,
            )
            parsed = _parse_plan_json(raw2)
        if parsed is None:
            raise OllamaError("Model did not return valid polished plan JSON.")
        return _merge_content(plan, parsed)


def _merge_content(
    engine_plan: StructuredStudyPlan, llm_plan: StructuredStudyPlan
) -> StructuredStudyPlan:
    if llm_plan.summary:
        engine_plan.summary = llm_plan.summary.strip()
    if llm_plan.priority_item and engine_plan.priority_item:
        engine_plan.priority_item = PriorityItem(
            title=engine_plan.priority_item.title,
            reason=llm_plan.priority_item.reason or engine_plan.priority_item.reason,
        )
    if llm_plan.tips:
        engine_plan.tips = [t for t in llm_plan.tips if t and t.strip()][:4]

    llm_days = {d.date: d for d in llm_plan.daily_plan}
    for day in engine_plan.daily_plan:
        other = llm_days.get(day.date)
        if not other:
            continue
        for idx, item in enumerate(day.items):
            if idx >= len(other.items):
                break
            cand = other.items[idx]
            if (item.kind or "study") == "study":
                if cand.action:
                    item.action = cand.action.strip()
                if cand.reason:
                    item.reason = cand.reason.strip()
            elif cand.action:
                item.action = cand.action.strip()
    return engine_plan


def detect_language(events: list[ClassifiedCalendarEvent]) -> str:
    hebrew = 0
    latin = 0
    for event in events:
        for chunk in (event.title or "", event.description or ""):
            for ch in chunk:
                if "\u0590" <= ch <= "\u05FF":
                    hebrew += 1
                elif ch.isalpha() and ch.isascii():
                    latin += 1
    return "he" if hebrew > latin else "en"


def build_event_metadata(
    events: list[ClassifiedCalendarEvent], *, today: date
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda e: e.start):
        rows.append(
            {
                "id": event.id,
                "title": event.title,
                "category": event.category.value,
                "description": event.description or "",
                "location": event.location or "",
                "start": event.start.isoformat(),
                "end": event.end.isoformat() if event.end else None,
                "priority": _PRIORITY.index(event.category) + 1,
                "days_until": (event.start.date() - today).days,
            }
        )
    return rows


def format_plan_text(plan: StructuredStudyPlan, *, language: str = "en") -> str:
    lines: list[str] = []
    if plan.summary:
        lines.append(plan.summary)
        lines.append("")
    for day in plan.daily_plan:
        try:
            label = date.fromisoformat(day.date).strftime("%A, %d %b")
        except Exception:
            label = day.date
        lines.append(label)
        for item in day.items:
            time_s = ""
            if item.start_time and item.end_time:
                time_s = f"{item.start_time}–{item.end_time} "
            lines.append(f"• {time_s}{item.title}".rstrip())
            if item.action:
                lines.append(f"  {item.action}")
            if item.reason and (item.kind or "study") == "study":
                lines.append(f"  ({item.reason})")
        lines.append("")
    if plan.tips:
        header = "הצעת AI" if language == "he" else "AI suggestion"
        lines.append(f"{header}: {plan.tips[0]}")
        for tip in plan.tips[1:]:
            lines.append(f"• {tip}")
    elif plan.priority_item:
        header = "הצעת AI" if language == "he" else "AI suggestion"
        lines.append(
            f"{header}: {plan.priority_item.title} — {plan.priority_item.reason}"
        )
    return "\n".join(lines).strip()


def _parse_anchor(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_plan_json(raw: str) -> StructuredStudyPlan | None:
    text = (raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    try:
        return StructuredStudyPlan.model_validate(data)
    except Exception:
        return None

