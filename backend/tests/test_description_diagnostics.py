"""Diagnostic tests for Exam vs Test-style Google event description shapes."""

from app.gateways.google_calendar_gateway import (
    _extract_description,
    _normalize_event,
    description_field_diagnostics,
)
from app.services.description_cleaner import clean_description


def _exam_like_event() -> dict:
    """Normal Calendar event — description is plain user text."""
    return {
        "id": "exam-os-1",
        "summary": "מבחן",
        "description": "Exam: Operating Systems",
        "start": {"dateTime": "2026-08-13T15:00:00+03:00"},
        "end": {"dateTime": "2026-08-13T16:00:00+03:00"},
        "htmlLink": "https://www.google.com/calendar/event?eid=exam",
    }


def _test_tasks_boilerplate_only() -> dict:
    """
    Google Tasks-backed Calendar event where Calendar API exposes only
    Tasks boilerplate + URL and NO user notes (common Calendar API limitation).
    """
    return {
        "id": "test-task-1",
        "summary": "Test",
        "description": (
            "This event was created from a Google Task.\n"
            "View this task in Google Tasks:\n"
            "https://tasks.google.com/task/abc123"
        ),
        "start": {"dateTime": "2026-08-05T12:00:00+03:00"},
        "end": {"dateTime": "2026-08-05T13:00:00+03:00"},
        "htmlLink": "https://www.google.com/calendar/event?eid=test",
        "source": {
            "title": "Test",
            "url": "https://tasks.google.com/task/abc123",
        },
    }


def _test_tasks_with_notes_in_description() -> dict:
    """Tasks event where user notes are present in Calendar description."""
    return {
        "id": "test-task-2",
        "summary": "Test",
        "description": (
            "שינויים בשם, בתיאור או בקבצים המצורפים לא יישמרו.\n"
            "כדי לערוך, צריך לעבור אל:\n"
            "https://tasks.google.com/task/xyz\n"
            "Operating Systems — Virtual Memory"
        ),
        "start": {"dateTime": "2026-08-05T12:00:00+03:00"},
        "end": {"dateTime": "2026-08-05T13:00:00+03:00"},
        "htmlLink": "https://www.google.com/calendar/event?eid=test2",
    }


def _test_notes_in_extended_properties() -> dict:
    return {
        "id": "test-task-3",
        "summary": "Test",
        "description": (
            "This event was created from a Google Task.\n"
            "https://tasks.google.com/task/zzz"
        ),
        "extendedProperties": {
            "private": {"notes": "Threads and Synchronization"},
        },
        "start": {"dateTime": "2026-08-05T12:00:00+03:00"},
        "end": {"dateTime": "2026-08-05T13:00:00+03:00"},
    }


def test_exam_description_preserved():
    item = _exam_like_event()
    meta = description_field_diagnostics(item)
    assert meta["description_exists"] is True
    assert meta["from_google_tasks"] is False
    cleaned = clean_description(_extract_description(item))
    assert cleaned == "Exam: Operating Systems"
    assert _normalize_event(item, "primary")["description"]
    assert clean_description(_normalize_event(item, "primary")["description"]) == (
        "Exam: Operating Systems"
    )


def test_tasks_boilerplate_only_cannot_invent_notes():
    """Honest limitation: if Calendar API has no user notes, cleaned is empty."""
    item = _test_tasks_boilerplate_only()
    meta = description_field_diagnostics(item)
    assert meta["from_google_tasks"] is True
    assert meta["description_exists"] is True
    cleaned = clean_description(_extract_description(item))
    assert cleaned is None


def test_tasks_notes_in_description_kept():
    item = _test_tasks_with_notes_in_description()
    cleaned = clean_description(_extract_description(item))
    assert cleaned is not None
    assert "Operating Systems" in cleaned
    assert "Virtual Memory" in cleaned
    assert "tasks.google.com" not in cleaned


def test_tasks_notes_in_extended_properties_kept():
    item = _test_notes_in_extended_properties()
    meta = description_field_diagnostics(item)
    assert meta["extended_properties_exist"] is True
    cleaned = clean_description(_extract_description(item))
    assert cleaned is not None
    assert "Threads and Synchronization" in cleaned
