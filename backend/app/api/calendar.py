"""Calendar API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.schemas.calendar_schema import CalendarSyncRequest, CalendarSyncResponse, TodayEventsResponse
from app.services.calendar_service import CalendarService

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.post("/sync", response_model=CalendarSyncResponse)
def sync_calendar(body: CalendarSyncRequest):
    """Fetch calendar events, classify by title prefix, and cache for the user."""
    try:
        return CalendarService().sync_calendar(body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/events/today", response_model=TodayEventsResponse)
def get_today_events(user_id: UUID):
    """Return today's classified events (sync first via POST /calendar/sync)."""
    try:
        return CalendarService().get_today_events(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
