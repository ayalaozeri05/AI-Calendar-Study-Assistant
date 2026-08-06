"""Pydantic schemas for calendar events."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class EventCategory(str, Enum):
    STUDY = "Study"
    ASSIGNMENT = "Assignment"
    EXAM = "Exam"
    CLASS = "Class"
    PROJECT = "Project"
    MEETING = "Meeting"
    OTHER = "Other"


class ClassifiedCalendarEvent(BaseModel):
    id: str
    title: str
    category: EventCategory
    start: datetime
    end: datetime | None = None
    description: str | None = None
    location: str | None = None
    is_all_day: bool = False
    calendar_id: str | None = None
    html_link: str | None = None
    source: str = "google_calendar"
    external_event_id: str | None = None


class CalendarUserRequest(BaseModel):
    user_id: UUID


class CalendarSyncRequest(BaseModel):
    user_id: UUID
    days_ahead: int = Field(default=7, ge=1, le=90)


class CalendarSyncResponse(BaseModel):
    user_id: UUID
    synced_count: int
    source: str = Field(description="google_calendar")
    events: list[ClassifiedCalendarEvent]


class CalendarStatusResponse(BaseModel):
    user_id: UUID
    connected: bool
    credentials_configured: bool
    token_exists: bool
    message: str | None = None
    google_email: str | None = None


class CalendarConnectResponse(BaseModel):
    user_id: UUID
    connected: bool
    credentials_configured: bool
    token_exists: bool
    message: str
    google_email: str | None = None


class TodayEventsResponse(BaseModel):
    user_id: UUID
    date: str
    events: list[ClassifiedCalendarEvent]


class WeekEventsResponse(BaseModel):
    user_id: UUID
    events: list[ClassifiedCalendarEvent]


class RangeEventsResponse(BaseModel):
    user_id: UUID
    start_date: str
    end_date: str
    events: list[ClassifiedCalendarEvent]
