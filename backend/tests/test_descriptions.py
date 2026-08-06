"""Description cleaning and Google Tasks-style extraction tests."""

from app.gateways.google_calendar_gateway import _extract_description, _normalize_event
from app.services.description_cleaner import clean_description


def test_normal_event_description():
    cleaned = clean_description("Operating Systems\nBring calculator")
    assert cleaned == "Operating Systems\nBring calculator"


def test_google_tasks_boilerplate_keeps_notes():
    raw = (
        "This event was created from a Google Task.\n"
        "View this task in Google Tasks:\n"
        "https://tasks.google.com/task/abc123\n"
        "Finish Reversing Section A"
    )
    cleaned = clean_description(raw)
    assert cleaned is not None
    assert "Finish Reversing Section A" in cleaned
    assert "tasks.google.com" not in cleaned
    assert "created from" not in cleaned.lower()


def test_hebrew_tasks_boilerplate_same_line():
    raw = "שינויים בשם, בתיאור או בקבצים המצורפים לא יישמרו. מערכות הפעלה"
    cleaned = clean_description(raw)
    assert cleaned is not None
    assert "מערכות הפעלה" in cleaned
    assert "שינויים" not in cleaned


def test_mixed_hebrew_english_description():
    raw = "Exam: Operating Systems\nחזרה על פרק 3"
    cleaned = clean_description(raw)
    assert cleaned is not None
    assert "Operating Systems" in cleaned
    assert "חזרה" in cleaned


def test_empty_description():
    assert clean_description(None) is None
    assert clean_description("") is None
    assert clean_description("https://tasks.google.com/task/x") is None


def test_extract_from_extended_properties():
    item = {
        "id": "evt1",
        "summary": "Test",
        "description": (
            "This event was created from a Google Task.\n"
            "https://tasks.google.com/task/x"
        ),
        "extendedProperties": {"private": {"notes": "Chapter 4 review"}},
        "start": {"dateTime": "2026-08-05T12:00:00+00:00"},
        "end": {"dateTime": "2026-08-05T13:00:00+00:00"},
        "htmlLink": "https://calendar.google.com/event?eid=1",
    }
    extracted = _extract_description(item)
    assert extracted is not None
    assert "Chapter 4 review" in extracted
    normalized = _normalize_event(item, "primary")
    cleaned = clean_description(normalized["description"])
    assert cleaned is not None
    assert "Chapter 4 review" in cleaned


def test_normalize_preserves_plain_description():
    item = {
        "id": "evt2",
        "summary": "מבחן",
        "description": "Exam: Operating Systems",
        "start": {"dateTime": "2026-08-13T15:00:00+00:00"},
        "end": {"dateTime": "2026-08-13T16:00:00+00:00"},
    }
    normalized = _normalize_event(item, "primary")
    assert normalized["description"] == "Exam: Operating Systems"
    assert clean_description(normalized["description"]) == "Exam: Operating Systems"
