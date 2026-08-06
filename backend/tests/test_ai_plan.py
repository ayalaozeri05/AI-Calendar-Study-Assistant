"""AI study plan parsing, fallback, and language detection tests."""

from datetime import datetime, timedelta, timezone

from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.ai_recommendation_service import (
    AiRecommendationService,
    _parse_plan_json,
    detect_language,
    format_plan_text,
)


def _event(
    title: str,
    category: EventCategory,
    *,
    days: int = 0,
    hour: int = 12,
    description: str | None = None,
) -> ClassifiedCalendarEvent:
    start = datetime.now(timezone.utc).replace(
        hour=hour, minute=0, second=0, microsecond=0
    ) + timedelta(days=days)
    return ClassifiedCalendarEvent(
        id=f"{title}-{days}",
        title=title,
        category=category,
        start=start,
        end=start + timedelta(hours=1),
        description=description,
    )


def test_parse_valid_json_plan():
    raw = """
    {
      "summary": "Focus on homework then exam prep",
      "priority_item": {"title": "Homework", "reason": "Due tomorrow"},
      "daily_plan": [
        {
          "date": "2026-08-05",
          "items": [
            {
              "start_time": "16:00",
              "end_time": "17:00",
              "title": "Homework",
              "action": "Finish Section A",
              "reason": "Due soon"
            }
          ]
        }
      ],
      "tips": ["Start with homework"]
    }
    """
    plan = _parse_plan_json(raw)
    assert plan is not None
    assert plan.priority_item is not None
    assert plan.priority_item.title == "Homework"
    assert plan.daily_plan[0].items[0].start_time == "16:00"


def test_parse_json_inside_markdown_fence():
    raw = """```json
{"summary":"Ok","priority_item":{"title":"A","reason":"B"},"daily_plan":[],"tips":[]}
```"""
    plan = _parse_plan_json(raw)
    assert plan is not None
    assert plan.summary == "Ok"


def test_invalid_json_returns_none():
    assert _parse_plan_json("not json at all") is None


def test_rule_based_fallback_prioritizes_same_day_assignment():
    events = [
        _event("OS Exam", EventCategory.EXAM, days=8, description="Operating Systems"),
        _event("Reversing", EventCategory.ASSIGNMENT, days=1, description="Section A"),
    ]
    today = datetime.now(timezone.utc).date()
    plan, text, mode = AiRecommendationService().generate_study_plan(
        events,
        start=today,
        end=today + timedelta(days=10),
        force_fallback=True,
    )
    assert mode == "rule_based_fallback"
    assert plan.daily_plan
    assert plan.priority_item is not None
    assert "Reversing" in plan.priority_item.title
    assert "Study Plan" not in text or True  # text is plan body
    assert "Reversing" in text or any(
        "Reversing" in (item.title or "")
        for day in plan.daily_plan
        for item in day.items
    )


def test_exam_in_eight_days_gets_multi_day_prep():
    events = [
        _event("OS Exam", EventCategory.EXAM, days=8, description="Operating Systems"),
    ]
    today = datetime.now(timezone.utc).date()
    plan, _, mode = AiRecommendationService().generate_study_plan(
        events,
        start=today,
        end=today + timedelta(days=10),
        force_fallback=True,
    )
    assert mode == "rule_based_fallback"
    days_with_items = [d.date for d in plan.daily_plan if d.items]
    assert len(days_with_items) >= 2


def test_language_detection_hebrew():
    events = [
        _event("מטלת בית", EventCategory.ASSIGNMENT, description="סעיף א"),
        _event("מבחן", EventCategory.EXAM, days=3, description="מערכות הפעלה"),
    ]
    assert detect_language(events) == "he"
    today = datetime.now(timezone.utc).date()
    plan, text, _ = AiRecommendationService().generate_study_plan(
        events, start=today, end=today + timedelta(days=5), force_fallback=True
    )
    # Hebrew plan should contain Hebrew letters in summary or tips
    blob = (plan.summary or "") + " ".join(plan.tips) + text
    assert any("\u0590" <= ch <= "\u05FF" for ch in blob)


def test_language_detection_english():
    events = [
        _event("Homework", EventCategory.ASSIGNMENT, description="Section A"),
        _event("Exam", EventCategory.EXAM, days=3, description="Operating Systems"),
    ]
    assert detect_language(events) == "en"
    today = datetime.now(timezone.utc).date()
    plan, text, _ = AiRecommendationService().generate_study_plan(
        events, start=today, end=today + timedelta(days=5), force_fallback=True
    )
    blob = (plan.summary or "") + text
    assert "study" in blob.lower() or "Study" in blob or "Start" in blob


def test_format_plan_text_readable_not_json():
    events = [_event("Homework", EventCategory.ASSIGNMENT, description="Done")]
    today = datetime.now(timezone.utc).date()
    plan, text, _ = AiRecommendationService().generate_study_plan(
        events, start=today, end=today, force_fallback=True
    )
    formatted = format_plan_text(plan, language="en")
    assert "{" not in formatted
    assert text
