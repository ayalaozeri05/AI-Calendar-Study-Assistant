"""Pydantic schemas for study briefs."""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class BriefType(str, Enum):
    TODAY = "today"
    WEEKLY = "weekly"


class BriefRequest(BaseModel):
    user_id: UUID


class BriefResponse(BaseModel):
    user_id: UUID
    brief_type: BriefType
    text: str
    event_count: int = Field(description="Number of events included in the brief")


class SendTelegramRequest(BaseModel):
    user_id: UUID
    brief_type: BriefType = BriefType.TODAY
    brief_text: str | None = None


class SendTelegramResponse(BaseModel):
    user_id: UUID
    brief_type: BriefType
    sent: bool
    message: str
