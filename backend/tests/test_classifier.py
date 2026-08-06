"""Classifier correctness tests (Sprint 7)."""

from app.services.calendar_event_classifier import CalendarEventClassifier
from app.services.description_cleaner import clean_description


def test_exam_keywords():
    c = CalendarEventClassifier.classify
    assert c("Test").value == "Exam"
    assert c("Exam: Operating Systems").value == "Exam"
    assert c("מבחן במערכות הפעלה").value == "Exam"
    assert c("בחינה").value == "Exam"
    assert c("בוחן").value == "Exam"
    assert c("quiz").value == "Exam"
    assert c("midterm").value == "Exam"


def test_assignment_keywords():
    c = CalendarEventClassifier.classify
    assert c("מטלת בית").value == "Assignment"
    assert c("שיעורי בית").value == "Assignment"
    assert c("תרגיל בית").value == "Assignment"
    assert c("Homework 3").value == "Assignment"
    assert c("assignment").value == "Assignment"


def test_study_for_exam():
    c = CalendarEventClassifier.classify
    assert c("ללמוד למבחן").value == "Study"
    assert c("Study for exam").value == "Study"


def test_project_meeting_disambiguation():
    c = CalendarEventClassifier.classify
    assert c("Project Meeting").value == "Project"
    assert c("Meeting about schedule").value == "Meeting"


def test_description_cleaner_keeps_user_text():
    raw = (
        "שינויים בשם, בתיאור או בקבצים המצורפים לא יישמרו.\n"
        "כדי לערוך, צריך לעבור אל:\n"
        "https://tasks.google.com/task/abc123\n"
        "Reversing — סעיף א׳"
    )
    cleaned = clean_description(raw)
    assert cleaned is not None
    assert "tasks.google.com" not in cleaned
    assert "Reversing" in cleaned
    assert "סעיף" in cleaned


def test_description_cleaner_keeps_text_on_same_line_as_boilerplate():
    raw = (
        "שינויים בשם, בתיאור או בקבצים המצורפים לא יישמרו. "
        "Operating Systems"
    )
    cleaned = clean_description(raw)
    assert cleaned is not None
    assert "Operating Systems" in cleaned
    assert "שינויים" not in cleaned
