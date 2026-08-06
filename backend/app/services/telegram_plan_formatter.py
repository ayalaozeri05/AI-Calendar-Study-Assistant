"""Concise Telegram formatting for study plans (complete but compact)."""

from __future__ import annotations

from datetime import date

from app.schemas.brief_schema import StructuredStudyPlan


def format_plan_for_telegram(
    plan: StructuredStudyPlan | dict,
    *,
    range_label: str | None = None,
) -> str:
    if isinstance(plan, dict):
        plan = StructuredStudyPlan.model_validate(plan)

    lines: list[str] = []
    title = (range_label or "STUDY PLAN").strip().upper()
    lines.append(title)
    lines.append("")

    # One-line priority once
    if plan.priority_item:
        lines.append(
            f"Priority: {plan.priority_item.title}"
            + (f" — {plan.priority_item.reason}" if plan.priority_item.reason else "")
        )
        lines.append("")

    for day in plan.daily_plan:
        try:
            label = date.fromisoformat(day.date).strftime("%A, %d %b").upper()
        except Exception:
            label = day.date.upper()
        lines.append(label)

        for item in day.items:
            kind = (item.kind or "study").strip().lower()
            time_s = ""
            if item.start_time and item.end_time:
                time_s = f"{item.start_time}–{item.end_time}"
            elif item.start_time:
                time_s = item.start_time

            if kind == "calendar":
                cat = (item.category or "").strip()
                head = f"{time_s} | CALENDAR EVENT" if time_s else "CALENDAR EVENT"
                if cat:
                    head = f"{head} — {cat}"
                lines.append(head)
                lines.append(item.title)
            elif kind == "recovery":
                head = f"{time_s} | RECOVERY" if time_s else "RECOVERY"
                lines.append(head)
                action = (item.action or "").strip()
                if action:
                    lines.append(action)
            elif kind == "meal":
                head = f"{time_s} | {(item.label or 'MEAL').upper()}" if time_s else (item.label or "MEAL").upper()
                lines.append(head)
                if item.title:
                    lines.append(item.title)
            elif kind == "break":
                head = f"{time_s} | BREAK" if time_s else "BREAK"
                lines.append(head)
            else:
                head = f"{time_s} | STUDY" if time_s else "STUDY"
                lines.append(head)
                lines.append(item.title)
                action = (item.action or "").strip()
                if action:
                    lines.append(action)
            lines.append("")

        lines.append("")

    if plan.tips:
        lines.append("AI suggestion")
        lines.append(plan.tips[0])

    # Collapse excessive blank lines
    out: list[str] = []
    blank = 0
    for line in lines:
        if line.strip() == "":
            blank += 1
            if blank <= 1:
                out.append("")
        else:
            blank = 0
            out.append(line)
    return "\n".join(out).strip()
