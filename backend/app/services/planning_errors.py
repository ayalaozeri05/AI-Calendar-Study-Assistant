"""Typed planning-pipeline errors (HTTP mapping lives in the API layer)."""

from __future__ import annotations

from typing import Any


class PlanningPipelineError(Exception):
    """Base error with a stable machine code and safe diagnostics."""

    code: str = "planning_error"
    http_status: int = 400

    def __init__(
        self,
        message: str,
        *,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or {}

    def as_detail(self) -> dict[str, Any]:
        payload = {
            "message": self.message,
            "code": self.code,
            "plan_generation_skipped_reason": self.code,
            **self.diagnostics,
        }
        return payload


class CalendarNotSyncedError(PlanningPipelineError):
    code = "calendar_not_synced"
    http_status = 409


class NoEventsInRangeError(PlanningPipelineError):
    code = "no_events_in_range"
    http_status = 422


class UserNotFoundError(PlanningPipelineError):
    code = "user_not_found"
    http_status = 404
