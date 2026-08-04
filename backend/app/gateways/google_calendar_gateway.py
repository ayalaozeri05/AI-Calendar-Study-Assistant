"""Google Calendar external-service gateway."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings, settings


class GoogleCalendarGateway:
    """Fetches calendar events from Google Calendar API or demo data."""

    def __init__(self, app_settings: Settings | None = None) -> None:
        self._settings = app_settings or settings

    def _credentials_configured(self) -> bool:
        path = self._settings.google_calendar_credentials_file.strip()
        return bool(path and Path(path).is_file())

    def fetch_events(
        self,
        time_min: datetime,
        time_max: datetime,
    ) -> tuple[list[dict], str]:
        """
        Return raw Google-style event dicts and source label ('google' or 'demo').
        Each dict has: id, summary, description, start, end (ISO strings or datetime).
        """
        if self._credentials_configured():
            events = self._fetch_from_google(time_min, time_max)
            return events, "google"
        return self._demo_events(time_min, time_max), "demo"

    def _fetch_from_google(
        self,
        time_min: datetime,
        time_max: datetime,
    ) -> list[dict]:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_path = self._settings.google_calendar_credentials_file
        creds = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        calendar_id = self._settings.google_calendar_id or "primary"

        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=_to_rfc3339(time_min),
                timeMax=_to_rfc3339(time_max),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        raw_events = result.get("items", [])
        parsed: list[dict] = []
        for item in raw_events:
            start = _parse_google_datetime(item.get("start", {}))
            end = _parse_google_datetime(item.get("end", {}))
            if start is None:
                continue
            parsed.append(
                {
                    "id": item.get("id", ""),
                    "summary": item.get("summary", "(No title)"),
                    "description": item.get("description"),
                    "start": start,
                    "end": end,
                }
            )
        return parsed

    def _demo_events(
        self,
        time_min: datetime,
        time_max: datetime,
    ) -> list[dict]:
        """Sample academic events for demo when Google credentials are not set."""
        day = time_min.date()
        samples = [
            (
                "demo-1",
                "Class: Software Engineering",
                9,
                0,
                10,
                30,
            ),
            (
                "demo-2",
                "Study: Database Systems project",
                11,
                0,
                12,
                0,
            ),
            (
                "demo-3",
                "Assignment: Algorithms exercise",
                14,
                0,
                15,
                0,
            ),
            (
                "demo-4",
                "Exam: Operating Systems",
                16,
                0,
                17,
                30,
            ),
            (
                "demo-5",
                "Project: AI Study Planner",
                18,
                0,
                19,
                0,
            ),
            (
                "demo-6",
                "Team standup",
                19,
                30,
                20,
                0,
            ),
        ]

        tz = time_min.tzinfo or timezone.utc
        events: list[dict] = []
        for event_id, title, sh, sm, eh, em in samples:
            start = datetime(day.year, day.month, day.day, sh, sm, tzinfo=tz)
            end = datetime(day.year, day.month, day.day, eh, em, tzinfo=tz)
            if start < time_min or start >= time_max:
                continue
            events.append(
                {
                    "id": event_id,
                    "summary": title,
                    "description": "Demo calendar event",
                    "start": start,
                    "end": end,
                }
            )
        return events


def _to_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _parse_google_datetime(part: dict) -> datetime | None:
    if "dateTime" in part:
        value = part["dateTime"]
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    if "date" in part:
        return datetime.fromisoformat(part["date"]).replace(tzinfo=timezone.utc)
    return None
