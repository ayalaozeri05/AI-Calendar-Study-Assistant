"""Pydantic schemas for user profiles."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class UserProfileCreate(BaseModel):
    email: str = Field(..., min_length=3)
    full_name: str | None = None
    telegram_chat_id: str | None = None


class UserProfileResponse(BaseModel):
    id: UUID
    email: str
    full_name: str | None = None
    telegram_chat_id: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True
