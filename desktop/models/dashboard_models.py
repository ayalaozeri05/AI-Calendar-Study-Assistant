"""Desktop-side DTOs for the calendar dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StudentInfo:
    id: str
    email: str
    full_name: str | None = None
    telegram_chat_id: str | None = None


@dataclass
class CalendarEventItem:
    id: str
    title: str
    category: str
    start: str
    end: str | None = None
    description: str | None = None


@dataclass
class DashboardState:
    student: StudentInfo | None = None
    events: list[CalendarEventItem] = field(default_factory=list)
    brief_text: str = ""
    last_sync_source: str = ""
    last_sync_count: int = 0
