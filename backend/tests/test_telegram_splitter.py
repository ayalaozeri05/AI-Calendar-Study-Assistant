"""Telegram message splitter and concise formatter tests."""

from app.schemas.brief_schema import (
    DailyPlan,
    PriorityItem,
    StructuredStudyPlan,
    StudyPlanItem,
)
from app.services.telegram_message_splitter import (
    TELEGRAM_HARD_LIMIT,
    TELEGRAM_SAFE_CHUNK,
    split_telegram_message,
)
from app.services.telegram_plan_formatter import format_plan_for_telegram


def test_short_message_one_part():
    parts = split_telegram_message("Hello study plan")
    assert parts == ["Hello study plan"]


def test_long_message_splits_under_hard_limit():
    days = []
    for i in range(1, 20):
        days.append(
            f"WEDNESDAY, {i} AUG\n"
            + "\n".join(
                [
                    f"09:00–10:30 | Operating Systems\nReview theory block {i}-{j}."
                    for j in range(8)
                ]
            )
        )
    text = "STUDY PLAN\n\n" + "\n\n".join(days)
    assert len(text) > 8000
    parts = split_telegram_message(text)
    assert len(parts) >= 2
    for part in parts:
        assert len(part) <= TELEGRAM_HARD_LIMIT
        assert len(part) <= TELEGRAM_SAFE_CHUNK + 80  # header slack
    joined = "\n".join(p.split("\n\n", 1)[-1] for p in parts)
    assert "Operating Systems" in joined
    assert "Review theory block 1-0" in joined
    assert "Review theory block 19-7" in joined


def test_split_prefers_blank_line_boundaries():
    block = "DAY A\n" + ("x" * 100) + "\n\nDAY B\n" + ("y" * 100)
    # Force split with small max
    parts = split_telegram_message(block * 30, max_len=500)
    assert len(parts) >= 2
    assert all(len(p) <= 500 for p in parts)


def test_hebrew_and_english_preserved():
    text = "STUDY PLAN\n\nיום רביעי\n09:00–10:30 | מבחן\nOperating Systems\n" + ("א" * 4000)
    parts = split_telegram_message(text)
    blob = "\n".join(parts)
    assert "מבחן" in blob
    assert "Operating Systems" in blob


def test_formatter_is_compact():
    plan = StructuredStudyPlan(
        summary="Focus week",
        priority_item=PriorityItem(title="OS Exam", reason="4 days left"),
        tips=["Spend today on OS"],
        daily_plan=[
            DailyPlan(
                date="2026-08-05",
                items=[
                    StudyPlanItem(
                        start_time="09:00",
                        end_time="10:30",
                        title="Operating Systems",
                        action="Review theory",
                        reason="4 days until OS Exam — prioritize this topic today.",
                        kind="study",
                    ),
                    StudyPlanItem(
                        start_time="10:30",
                        end_time="10:45",
                        title="Break",
                        action="Rest",
                        kind="break",
                    ),
                ],
            )
        ],
    )
    text = format_plan_for_telegram(plan, range_label="STUDY PLAN — 5–18 AUG")
    assert "STUDY PLAN — 5–18 AUG" in text
    assert "09:00–10:30 | STUDY" in text
    assert "Operating Systems" in text
    assert "Review theory" in text
    assert "10:30–10:45 | BREAK" in text
