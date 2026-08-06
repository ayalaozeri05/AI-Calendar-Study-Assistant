"""Pydantic schemas for study briefs."""

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class BriefType(str, Enum):
    TODAY = "today"
    WEEKLY = "weekly"
    RANGE = "range"


class BriefRequest(BaseModel):
    user_id: UUID


class RangeBriefRequest(BaseModel):
    user_id: UUID
    start_date: str = Field(description="YYYY-MM-DD")
    end_date: str = Field(description="YYYY-MM-DD")
    label: str | None = None
    regenerate: bool = False
    previous_plan: dict[str, Any] | None = None
    variation_seed: int | None = None
    planning_anchor: str | None = None


class StudyPlanItem(BaseModel):
    start_time: str | None = None
    end_time: str | None = None
    title: str
    action: str = ""
    reason: str = ""
    kind: str = "study"  # study | break | meal | calendar | recovery
    phase: str | None = None
    category: str | None = None
    label: str | None = None


class DailyPlan(BaseModel):
    date: str
    items: list[StudyPlanItem] = Field(default_factory=list)


class PriorityItem(BaseModel):
    title: str
    reason: str = ""


class StructuredStudyPlan(BaseModel):
    summary: str = ""
    priority_item: PriorityItem | None = None
    daily_plan: list[DailyPlan] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    planning_anchor: str | None = None  # ISO local datetime for Today earliest start


class BriefResponse(BaseModel):
    user_id: UUID
    brief_type: BriefType
    text: str
    event_count: int = Field(description="Number of events included in the brief")
    ai_mode: str = "rule_based_fallback"
    plan: StructuredStudyPlan | None = None
    planning_anchor: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class SendTelegramRequest(BaseModel):
    user_id: UUID
    brief_type: BriefType = BriefType.TODAY
    brief_text: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    plan: dict[str, Any] | None = None


class SendTelegramResponse(BaseModel):
    user_id: UUID
    brief_type: BriefType
    sent: bool
    message: str
    success: bool = True
    parts_sent: int = 0
    total_parts: int = 0
