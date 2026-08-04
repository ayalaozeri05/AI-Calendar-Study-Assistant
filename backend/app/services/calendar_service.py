"""Calendar sync and today-events business logic."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from app.gateways.google_calendar_gateway import GoogleCalendarGateway
from app.repositories.activity_repository import ActivityRepository
from app.repositories.user_repository import UserRepository
from app.schemas.calendar_schema import (
    CalendarSyncResponse,
    ClassifiedCalendarEvent,
    TodayEventsResponse,
)
from app.services.calendar_event_classifier import CalendarEventClassifier

# In-memory store until schema adds a calendar_events table (MVP).
_synced_events: dict[str, list[ClassifiedCalendarEvent]] = {}


class CalendarService:
    def __init__(
        self,
        calendar_gateway: GoogleCalendarGateway | None = None,
        classifier: CalendarEventClassifier | None = None,
        user_repository: UserRepository | None = None,
        activity_repository: ActivityRepository | None = None,
    ) -> None:
        self._calendar = calendar_gateway or GoogleCalendarGateway()
        self._classifier = classifier or CalendarEventClassifier()
        self._users = user_repository or UserRepository()
        self._activity = activity_repository or ActivityRepository()

    def sync_calendar(self, user_id: UUID) -> CalendarSyncResponse:
        user = self._users.get_user_profile(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")

        time_min, time_max = _week_range_utc()
        raw_events, source = self._calendar.fetch_events(time_min, time_max)
        classified = [_to_classified(e, self._classifier) for e in raw_events]

        _synced_events[str(user_id)] = classified

        self._activity.log_event(
            user_id=user_id,
            event_type="calendar_synced",
            entity_type="calendar",
            description=f"Synced {len(classified)} events from {source}",
        )

        return CalendarSyncResponse(
            user_id=user_id,
            synced_count=len(classified),
            source=source,
            events=classified,
        )

    def get_today_events(self, user_id: UUID) -> TodayEventsResponse:
        user = self._users.get_user_profile(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")

        today = datetime.now(timezone.utc).date()
        all_events = get_synced_events(user_id)
        today_events = [e for e in all_events if e.start.date() == today]

        return TodayEventsResponse(
            user_id=user_id,
            date=today.isoformat(),
            events=today_events,
        )

    def get_week_events(self, user_id: UUID) -> list[ClassifiedCalendarEvent]:
        user = self._users.get_user_profile(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")
        return get_synced_events(user_id)


def get_synced_events(user_id: UUID) -> list[ClassifiedCalendarEvent]:
    """Return cached events for a user (empty until POST /calendar/sync)."""
    return _synced_events.get(str(user_id), [])


def _week_range_utc() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    return start, end


def _to_classified(
    raw: dict,
    classifier: CalendarEventClassifier,
) -> ClassifiedCalendarEvent:
    title = raw.get("summary", "(No title)")
    start = raw["start"]
    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end = raw.get("end")
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))

    return ClassifiedCalendarEvent(
        id=str(raw.get("id", "")),
        title=title,
        category=classifier.classify(title),
        start=start,
        end=end,
        description=raw.get("description"),
    )
