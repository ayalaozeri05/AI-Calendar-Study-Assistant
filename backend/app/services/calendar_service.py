"""Calendar sync and query business logic (real Google Calendar OAuth)."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

logger = logging.getLogger(__name__)

from app.gateways.google_calendar_gateway import (
    GoogleCalendarError,
    GoogleCalendarGateway,
)
from app.repositories.activity_repository import ActivityRepository
from app.repositories.user_repository import UserRepository
from app.schemas.calendar_schema import (
    CalendarConnectResponse,
    CalendarStatusResponse,
    CalendarSyncResponse,
    ClassifiedCalendarEvent,
    RangeEventsResponse,
    TodayEventsResponse,
    WeekEventsResponse,
)
from app.services.calendar_event_classifier import CalendarEventClassifier
from app.services.description_cleaner import clean_description

# In-memory store keyed by user_id; dedupe by external_event_id (MVP, no schema change).
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

    def get_status(self, user_id: UUID) -> CalendarStatusResponse:
        self._require_user(user_id)
        status = self._calendar.get_status(user_id)
        if not status["credentials_configured"]:
            message = "Credentials missing"
        elif status["connected"]:
            message = "Connected"
        else:
            message = "Not connected"
        return CalendarStatusResponse(
            user_id=user_id,
            connected=status["connected"],
            credentials_configured=status["credentials_configured"],
            token_exists=status["token_exists"],
            message=message,
            google_email=status.get("google_email"),
        )

    def connect(self, user_id: UUID) -> CalendarConnectResponse:
        self._require_user(user_id)
        result = self._calendar.connect(user_id)
        self._activity.log_event(
            user_id=user_id,
            event_type="calendar_connected",
            entity_type="calendar",
            description="Google Calendar OAuth connected",
        )
        return CalendarConnectResponse(
            user_id=user_id,
            connected=result["connected"],
            credentials_configured=result["credentials_configured"],
            token_exists=result["token_exists"],
            message=result["message"],
            google_email=result.get("google_email"),
        )

    def sync_calendar(
        self, user_id: UUID, days_ahead: int = 7
    ) -> CalendarSyncResponse:
        self._require_user(user_id)

        status = self._calendar.get_status(user_id)
        if not status["credentials_configured"]:
            raise GoogleCalendarError(
                "Google Calendar credentials are missing. "
                "Ask your instructor or check GOOGLE_CALENDAR_CREDENTIALS_PATH."
            )
        if not status["connected"]:
            raise GoogleCalendarError(
                "Google Calendar is not connected yet.\n"
                "Please connect your Google Calendar first."
            )

        now = datetime.now(timezone.utc)
        time_min = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        time_max = time_min + timedelta(days=max(1, days_ahead))

        raw_events = self._calendar.list_events(user_id, time_min, time_max)
        classified = [
            _to_classified(event, self._classifier)
            for event in raw_events
            if event.get("start_datetime") or event.get("start")
        ]

        # Deduplicate by external_event_id while preserving order
        by_id: dict[str, ClassifiedCalendarEvent] = {}
        for event in classified:
            key = event.external_event_id or event.id
            by_id[key] = event
        unique = list(by_id.values())
        unique.sort(key=lambda e: e.start)

        _synced_events[str(user_id)] = unique

        self._activity.log_event(
            user_id=user_id,
            event_type="calendar_synced",
            entity_type="calendar",
            description=f"Synced {len(unique)} events from google_calendar",
        )

        return CalendarSyncResponse(
            user_id=user_id,
            synced_count=len(unique),
            source="google_calendar",
            events=unique,
        )

    def get_today_events(self, user_id: UUID) -> TodayEventsResponse:
        self._require_user(user_id)
        today = datetime.now().astimezone().date()
        all_events = get_synced_events(user_id)
        today_events = [e for e in all_events if _event_local_date(e) == today]
        return TodayEventsResponse(
            user_id=user_id,
            date=today.isoformat(),
            events=today_events,
        )

    def get_week_events_response(self, user_id: UUID) -> WeekEventsResponse:
        self._require_user(user_id)
        return WeekEventsResponse(
            user_id=user_id,
            events=self.get_week_events(user_id),
        )

    def get_week_events(self, user_id: UUID) -> list[ClassifiedCalendarEvent]:
        self._require_user(user_id)
        today = datetime.now().astimezone().date()
        end = today + timedelta(days=6)
        return self.get_events_in_range(user_id, today, end)

    def get_events_range(
        self, user_id: UUID, start_date: str, end_date: str
    ) -> RangeEventsResponse:
        self._require_user(user_id)
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start > end:
            raise ValueError("start_date must be on or before end_date.")
        events = self.get_events_in_range(user_id, start, end)
        return RangeEventsResponse(
            user_id=user_id,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            events=events,
        )

    def get_events_in_range(
        self, user_id: UUID, start: date, end: date
    ) -> list[ClassifiedCalendarEvent]:
        all_events = get_synced_events(user_id)
        return [
            e
            for e in all_events
            if start <= _event_local_date(e) <= end
        ]

    def has_session_sync(self, user_id: UUID) -> bool:
        """True when this process has run sync for the user (even if zero events)."""
        return str(user_id) in _synced_events

    def stored_event_count(self, user_id: UUID) -> int:
        return len(get_synced_events(user_id))

    def ensure_session_events(
        self, user_id: UUID, *, days_ahead: int = 62
    ) -> list[ClassifiedCalendarEvent]:
        """
        Return in-memory synced events.

        Synced events are process-memory only (not persisted). After a backend
        restart the cache is empty even if Google OAuth tokens remain on disk.
        When the user is still connected, rehydrate once via Google sync.
        """
        self._require_user(user_id)
        key = str(user_id)
        if key in _synced_events:
            return get_synced_events(user_id)

        status = self._calendar.get_status(user_id)
        if status.get("connected"):
            logger.info(
                "calendar_rehydrate user_id=%s reason=memory_empty_connected "
                "days_ahead=%s",
                key,
                days_ahead,
            )
            self.sync_calendar(user_id, days_ahead=days_ahead)
            return get_synced_events(user_id)

        return []

    def _require_user(self, user_id: UUID) -> dict:
        user = self._users.get_user_profile(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")
        return user


def get_synced_events(user_id: UUID) -> list[ClassifiedCalendarEvent]:
    """Return cached events for a user (empty until POST /calendar/sync)."""
    return _synced_events.get(str(user_id), [])


def clear_synced_events_for_tests() -> None:
    """Test helper — wipe in-memory sync cache."""
    _synced_events.clear()


def _event_local_date(event: ClassifiedCalendarEvent) -> date:
    """Compare ranges in the host local timezone (matches desktop date pickers)."""
    start = event.start
    if start.tzinfo is not None:
        start = start.astimezone()
    return start.date()


def _to_classified(
    raw: dict,
    classifier: CalendarEventClassifier,
) -> ClassifiedCalendarEvent:
    title = raw.get("title") or raw.get("summary") or "(No title)"
    start = raw.get("start_datetime") or raw.get("start")
    end = raw.get("end_datetime") or raw.get("end")
    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    if start is None:
        raise ValueError("Event missing start datetime")

    external_id = str(raw.get("external_event_id") or raw.get("id") or "")
    raw_description = raw.get("description")
    raw_len = len(str(raw_description)) if raw_description else 0
    cleaned = clean_description(raw_description)
    cleaned_len = len(cleaned) if cleaned else 0
    # Safe metadata only — never log description content or tokens
    logger.info(
        "event_description meta id=%s has_raw=%s raw_len=%s has_cleaned=%s cleaned_len=%s",
        external_id or "(none)",
        bool(raw_description),
        raw_len,
        bool(cleaned),
        cleaned_len,
    )
    return ClassifiedCalendarEvent(
        id=external_id,
        external_event_id=external_id,
        title=title,
        description=cleaned,
        category=classifier.classify(title, raw_description),
        start=start,
        end=end,
        location=raw.get("location"),
        is_all_day=bool(raw.get("is_all_day", False)),
        calendar_id=raw.get("calendar_id"),
        html_link=raw.get("html_link"),
        source=raw.get("source") or "google_calendar",
    )
