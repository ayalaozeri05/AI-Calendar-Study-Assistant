"""Google Calendar Gateway — per-user OAuth (read-only)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

from app.config import Settings, settings

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CREDENTIALS = _PROJECT_ROOT / "secrets" / "google_calendar_credentials.json"
_DEFAULT_TOKEN_DIR = _PROJECT_ROOT / "local_tokens" / "google_calendar"


class GoogleCalendarError(Exception):
    """Readable Google Calendar / OAuth error for API responses."""


class GoogleCalendarGateway:
    """Centralizes Google Calendar OAuth and event fetching. No UI / Supabase."""

    def __init__(self, app_settings: Settings | None = None) -> None:
        self._settings = app_settings or settings

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def credentials_path(self) -> Path:
        configured = (
            self._settings.google_calendar_credentials_path
            or self._settings.google_calendar_credentials_file
        ).strip()
        if configured:
            path = Path(configured)
            if not path.is_absolute():
                path = _PROJECT_ROOT / path
            return path
        return _DEFAULT_CREDENTIALS

    def token_dir(self) -> Path:
        configured = self._settings.google_calendar_token_dir.strip()
        if configured:
            path = Path(configured)
            if not path.is_absolute():
                path = _PROJECT_ROOT / path
            return path
        return _DEFAULT_TOKEN_DIR

    def token_path(self, user_id: UUID | str) -> Path:
        return self.token_dir() / f"{user_id}.json"

    def credentials_configured(self) -> bool:
        return self.credentials_path().is_file()

    def token_exists(self, user_id: UUID | str) -> bool:
        return self.token_path(user_id).is_file()

    def is_connected(self, user_id: UUID | str) -> bool:
        if not self.token_exists(user_id):
            return False
        try:
            creds = self._load_user_credentials(user_id, start_oauth=False)
            return creds is not None and creds.valid
        except GoogleCalendarError:
            return False

    # ------------------------------------------------------------------
    # Status / connect
    # ------------------------------------------------------------------

    def get_status(self, user_id: UUID | str) -> dict[str, Any]:
        configured = self.credentials_configured()
        token = self.token_exists(user_id)
        connected = False
        google_email: str | None = None
        if configured and token:
            connected = self.is_connected(user_id)
            if connected:
                google_email = self.get_account_email(user_id)
        return {
            "connected": connected,
            "credentials_configured": configured,
            "token_exists": token,
            "google_email": google_email,
        }

    def get_account_email(self, user_id: UUID | str) -> str | None:
        """Best-effort Google account email from the primary calendar id."""
        try:
            from googleapiclient.discovery import build

            creds = self._load_user_credentials(user_id, start_oauth=False)
            if creds is None or not creds.valid:
                return None
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            primary = service.calendars().get(calendarId="primary").execute()
            email = (primary.get("id") or "").strip()
            if email and "@" in email:
                return email
        except Exception:
            return None
        return None

    def connect(self, user_id: UUID | str) -> dict[str, Any]:
        """Ensure OAuth token exists (starts browser flow if needed)."""
        if not self.credentials_configured():
            raise GoogleCalendarError(
                "Google credentials file missing. Place the Desktop OAuth client "
                "JSON at the path set in GOOGLE_CALENDAR_CREDENTIALS_PATH "
                "(default: secrets/google_calendar_credentials.json)."
            )
        creds = self._load_user_credentials(user_id, start_oauth=True)
        if creds is None or not creds.valid:
            raise GoogleCalendarError(
                "Google Calendar connection failed or was canceled."
            )
        email = self.get_account_email(user_id)
        return {
            "connected": True,
            "credentials_configured": True,
            "token_exists": True,
            "message": "Google Calendar connected successfully.",
            "google_email": email,
        }

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def list_events(
        self,
        user_id: UUID | str,
        time_min: datetime,
        time_max: datetime,
        calendar_id: str = "primary",
    ) -> list[dict[str, Any]]:
        """Fetch and normalize events from the user's primary calendar."""
        if not self.credentials_configured():
            raise GoogleCalendarError(
                "Google credentials file missing. Configure "
                "GOOGLE_CALENDAR_CREDENTIALS_PATH before syncing."
            )
        if not self.token_exists(user_id):
            raise GoogleCalendarError(
                "Google Calendar is not connected yet.\n"
                "Please connect your Google Calendar first."
            )

        creds = self._load_user_credentials(user_id, start_oauth=False)
        if creds is None or not creds.valid:
            raise GoogleCalendarError(
                "Google token is invalid or revoked. Connect Google Calendar again."
            )

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
        except ImportError as exc:
            raise GoogleCalendarError(
                "Google API client libraries are not installed."
            ) from exc

        try:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            result = (
                service.events()
                .list(
                    calendarId=calendar_id or "primary",
                    timeMin=_to_rfc3339(time_min),
                    timeMax=_to_rfc3339(time_max),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
        except HttpError as exc:
            status = getattr(exc, "status_code", None) or getattr(
                exc.resp, "status", None
            )
            if status == 403:
                raise GoogleCalendarError(
                    "Google Calendar API request denied. Enable the Google Calendar "
                    "API in your Google Cloud project and ensure the OAuth consent "
                    "screen allows this user."
                ) from exc
            if status == 401:
                raise GoogleCalendarError(
                    "Google token is invalid or revoked. Connect Google Calendar again."
                ) from exc
            raise GoogleCalendarError(
                "Google API request failed. Check Calendar API enablement and try again."
            ) from exc
        except GoogleCalendarError:
            raise
        except Exception as exc:
            raise GoogleCalendarError(
                "Google API request failed. Check network and Calendar API settings."
            ) from exc

        items = result.get("items", []) or []
        normalized = []
        for item in items:
            meta = description_field_diagnostics(item)
            logger.info(
                "calendar_event_desc_meta id=%s summary=%s desc_exists=%s desc_len=%s "
                "tasks=%s ext=%s attachments=%s",
                meta.get("event_id"),
                meta.get("summary_exists"),
                meta.get("description_exists"),
                meta.get("description_length"),
                meta.get("from_google_tasks"),
                meta.get("extended_properties_exist"),
                meta.get("attachments_count"),
            )
            normalized.append(_normalize_event(item, calendar_id or "primary"))
        return normalized

    # ------------------------------------------------------------------
    # Credentials / token helpers
    # ------------------------------------------------------------------

    def _load_user_credentials(self, user_id: UUID | str, *, start_oauth: bool):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        token_file = self.token_path(user_id)
        creds = None

        if token_file.is_file():
            try:
                creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
            except Exception as exc:
                if not start_oauth:
                    raise GoogleCalendarError(
                        "Google token file is corrupted. Connect Google Calendar again."
                    ) from exc
                creds = None

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_token(user_id, creds)
            except Exception as exc:
                if not start_oauth:
                    raise GoogleCalendarError(
                        "Google token refresh failed. Connect Google Calendar again."
                    ) from exc
                creds = None

        if creds and creds.valid:
            return creds

        if not start_oauth:
            return None

        creds_path = self.credentials_path()
        if not creds_path.is_file():
            raise GoogleCalendarError(
                "Google credentials file missing. Place the Desktop OAuth client "
                f"JSON at: {creds_path}"
            )

        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        except Exception as exc:
            message = str(exc).lower()
            if "access_denied" in message or "denied" in message:
                raise GoogleCalendarError(
                    "Google OAuth was canceled or access was denied."
                ) from exc
            raise GoogleCalendarError(
                "Google OAuth failed. Check the credentials file and consent screen."
            ) from exc

        self._save_token(user_id, creds)
        return creds

    def _save_token(self, user_id: UUID | str, creds) -> None:
        token_file = self.token_path(user_id)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")


def _to_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def description_field_diagnostics(item: dict) -> dict[str, Any]:
    """Safe metadata for diagnosing missing descriptions (no secrets / no body text)."""
    desc = item.get("description")
    extended = item.get("extendedProperties") or {}
    shared = extended.get("shared") if isinstance(extended, dict) else None
    private = extended.get("private") if isinstance(extended, dict) else None
    attachments = item.get("attachments") or []
    source = item.get("source") or {}
    raw_desc = str(desc or "")
    from_tasks = (
        "tasks.google.com" in raw_desc.lower()
        or "created from a google task" in raw_desc.lower()
        or (isinstance(source, dict) and "tasks.google.com" in str(source.get("url") or "").lower())
    )
    notes_keys = []
    for bucket_name, bucket in (("shared", shared), ("private", private)):
        if isinstance(bucket, dict):
            for key, value in bucket.items():
                if value and str(value).strip():
                    notes_keys.append(f"{bucket_name}.{key}:{len(str(value))}")
    return {
        "event_id": item.get("id") or "",
        "summary_exists": bool(item.get("summary")),
        "description_exists": bool(desc and str(desc).strip()),
        "description_length": len(str(desc)) if desc else 0,
        "extended_properties_exist": bool(shared or private),
        "extended_notes_keys": notes_keys,
        "attachments_count": len(attachments) if isinstance(attachments, list) else 0,
        "attachment_titles": [
            str(a.get("title") or "")[:80]
            for a in (attachments if isinstance(attachments, list) else [])
            if isinstance(a, dict) and a.get("title")
        ][:5],
        "source_title": (source.get("title") if isinstance(source, dict) else None),
        "html_link_exists": bool(item.get("htmlLink")),
        "from_google_tasks": from_tasks,
    }


def _extract_description(item: dict) -> str | None:
    """Collect description text from Calendar + Google Tasks-style fields."""
    chunks: list[str] = []

    primary = item.get("description")
    if primary:
        chunks.append(str(primary))

    # Google Tasks / Calendar occasionally stash notes in extended properties
    extended = item.get("extendedProperties") or {}
    for bucket_name in ("shared", "private"):
        bucket = extended.get(bucket_name) or {}
        if not isinstance(bucket, dict):
            continue
        for key, value in bucket.items():
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            # Skip pure ids / booleans
            if text.lower() in {"true", "false"} or re.fullmatch(r"[\w-]{8,}", text):
                if "note" not in key.lower() and "desc" not in key.lower() and "detail" not in key.lower():
                    continue
            chunks.append(text)

    # Attachment titles sometimes carry the human note for Task-backed events
    for attachment in item.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        title = (attachment.get("title") or "").strip()
        if title and "google.com" not in title.lower():
            chunks.append(title)

    # Source title is usually the same as summary for Tasks — only keep if distinct
    source = item.get("source") or {}
    summary = str(item.get("summary") or "").strip().lower()
    if isinstance(source, dict):
        value = str(source.get("title") or "").strip()
        if (
            value
            and "google.com" not in value.lower()
            and value.lower() != summary
        ):
            chunks.append(value)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for chunk in chunks:
        normalized = chunk.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)

    if not unique:
        return None
    return "\n".join(unique)


def _normalize_event(item: dict, calendar_id: str) -> dict[str, Any]:
    start_part = item.get("start") or {}
    end_part = item.get("end") or {}
    is_all_day = "date" in start_part and "dateTime" not in start_part
    start_dt = _parse_google_datetime(start_part)
    end_dt = _parse_google_datetime(end_part)
    description = _extract_description(item)

    # Detect Google Tasks-backed calendar events without changing OAuth behavior
    source_label = "google_calendar"
    raw_desc = str(item.get("description") or "")
    html_link = item.get("htmlLink")
    if "tasks.google.com" in raw_desc.lower() or "created from a google task" in raw_desc.lower():
        source_label = "google_tasks"

    return {
        "external_event_id": item.get("id") or "",
        "title": item.get("summary") or "(No title)",
        "description": description,
        "start_datetime": start_dt,
        "end_datetime": end_dt,
        "is_all_day": is_all_day,
        "location": item.get("location"),
        "calendar_id": calendar_id,
        "html_link": html_link,
        "source": source_label,
        # Compatibility aliases used by existing classifiers/services
        "id": item.get("id") or "",
        "summary": item.get("summary") or "(No title)",
        "start": start_dt,
        "end": end_dt,
    }


def _parse_google_datetime(part: dict) -> datetime | None:
    if "dateTime" in part:
        value = part["dateTime"]
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    if "date" in part:
        # All-day events: treat as midnight UTC of that date
        return datetime.fromisoformat(part["date"]).replace(tzinfo=timezone.utc)
    return None
