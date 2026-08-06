"""Calendar API routes — Google Calendar OAuth + sync."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.gateways.google_calendar_gateway import GoogleCalendarError
from app.schemas.calendar_schema import (
    CalendarConnectResponse,
    CalendarStatusResponse,
    CalendarSyncRequest,
    CalendarSyncResponse,
    CalendarUserRequest,
    RangeEventsResponse,
    TodayEventsResponse,
    WeekEventsResponse,
)
from app.services.calendar_service import CalendarService

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GoogleCalendarError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/status", response_model=CalendarStatusResponse)
def calendar_status(user_id: UUID):
    """Return Google Calendar connection status for a user."""
    try:
        return CalendarService().get_status(user_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/connect", response_model=CalendarConnectResponse)
def connect_calendar(body: CalendarUserRequest):
    """Start or validate OAuth for the user (opens browser on first connect)."""
    try:
        return CalendarService().connect(body.user_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/sync", response_model=CalendarSyncResponse)
def sync_calendar(body: CalendarSyncRequest):
    """Fetch real Google Calendar events, classify, and cache for the user."""
    try:
        return CalendarService().sync_calendar(body.user_id, body.days_ahead)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/events/today", response_model=TodayEventsResponse)
def get_today_events(user_id: UUID):
    """Return today's classified events (sync first via POST /calendar/sync)."""
    try:
        return CalendarService().get_today_events(user_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/events/week", response_model=WeekEventsResponse)
def get_week_events(user_id: UUID):
    """Return synced week events (from last successful sync)."""
    try:
        return CalendarService().get_week_events_response(user_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/events/range", response_model=RangeEventsResponse)
def get_events_range(user_id: UUID, start_date: str, end_date: str):
    """Return synced events in an inclusive date range (YYYY-MM-DD)."""
    try:
        return CalendarService().get_events_range(user_id, start_date, end_date)
    except Exception as exc:
        raise _map_error(exc) from exc
