"""Classify Google Calendar event titles by prefix."""

from app.schemas.calendar_schema import EventCategory

RECOGNIZED_PREFIXES = {c.value for c in EventCategory if c != EventCategory.OTHER}


class CalendarEventClassifier:
    """Maps event titles like 'Exam: OS' to EventCategory.EXAM."""

    @staticmethod
    def classify(title: str) -> EventCategory:
        if ":" not in title:
            return EventCategory.OTHER

        prefix = title.split(":", 1)[0].strip()
        if prefix in RECOGNIZED_PREFIXES:
            return EventCategory(prefix)
        return EventCategory.OTHER
