"""Placeholder AI recommendations until Ollama is connected."""

from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory


class AiRecommendationService:
    """Rule-based stub; replace with OllamaGateway + LangChain later."""

    def suggest_focus(self, events: list[ClassifiedCalendarEvent]) -> str:
        if not events:
            return "No events loaded — sync your calendar first."

        priority = (
            EventCategory.EXAM,
            EventCategory.ASSIGNMENT,
            EventCategory.PROJECT,
            EventCategory.STUDY,
            EventCategory.CLASS,
            EventCategory.OTHER,
        )
        by_category = {c: [] for c in priority}
        for event in events:
            by_category[event.category].append(event)

        for category in priority:
            items = by_category[category]
            if items:
                first = sorted(items, key=lambda e: e.start)[0]
                return f"Focus first on [{category.value}]: {first.title}"

        return "Review your schedule and start with the earliest item."
