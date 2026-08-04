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
    OTHER = "Other"


class ClassifiedCalendarEvent(BaseModel):
    id: str
    title: str
    category: EventCategory
    start: datetime
    end: datetime | None = None
    description: str | None = None


class CalendarSyncRequest(BaseModel):
    user_id: UUID


class CalendarSyncResponse(BaseModel):
    user_id: UUID
    synced_count: int
    source: str = Field(description="google or demo")
    events: list[ClassifiedCalendarEvent]


class TodayEventsResponse(BaseModel):
    user_id: UUID
    date: str
    events: list[ClassifiedCalendarEvent]
