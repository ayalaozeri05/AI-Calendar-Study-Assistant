"""Study brief pipeline: unsynced / empty-range errors and Ollama skip."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services import calendar_service as calendar_module
from app.services.calendar_service import CalendarService, clear_synced_events_for_tests
from app.services.planning_errors import CalendarNotSyncedError, NoEventsInRangeError
from app.services.study_brief_service import StudyBriefService


@pytest.fixture(autouse=True)
def _clean_sync_cache():
    clear_synced_events_for_tests()
    yield
    clear_synced_events_for_tests()


def _event(days: int = 1) -> ClassifiedCalendarEvent:
    start = datetime.now().astimezone().replace(
        hour=10, minute=0, second=0, microsecond=0
    ) + timedelta(days=days)
    return ClassifiedCalendarEvent(
        id=f"e-{days}",
        title="Algorithms Exam",
        category=EventCategory.EXAM,
        start=start,
        end=start + timedelta(hours=2),
        description=None,
    )


def test_unsynced_calendar_raises_friendly_error():
    cal = CalendarService()
    cal._users = MagicMock()
    cal._users.get_user_profile.return_value = {"id": str(uuid4())}
    cal._calendar = MagicMock()
    cal._calendar.get_status.return_value = {
        "connected": False,
        "credentials_configured": True,
        "token_exists": False,
    }

    svc = StudyBriefService(calendar_service=cal, ai_service=MagicMock())
    user_id = uuid4()
    today = datetime.now().astimezone().date()
    with pytest.raises(CalendarNotSyncedError) as exc:
        svc.generate_range_brief(user_id, today.isoformat(), today.isoformat())
    assert "Calendar data is not available" in exc.value.message
    assert exc.value.code == "calendar_not_synced"
    assert exc.value.http_status == 409


def test_empty_range_skips_ollama_and_raises_422_style_error():
    user_id = uuid4()
    cal = CalendarService()
    cal._users = MagicMock()
    cal._users.get_user_profile.return_value = {"id": str(user_id)}
    calendar_module._synced_events[str(user_id)] = [_event(days=20)]

    ai = MagicMock()
    svc = StudyBriefService(calendar_service=cal, ai_service=ai)
    today = datetime.now().astimezone().date()
    with pytest.raises(NoEventsInRangeError) as exc:
        svc.generate_range_brief(user_id, today.isoformat(), today.isoformat())
    assert "No events were found" in exc.value.message
    assert exc.value.code == "no_events_in_range"
    assert exc.value.http_status == 422
    ai.generate_study_plan.assert_not_called()


def test_api_maps_calendar_not_synced_to_409():
    client = TestClient(app)
    err = CalendarNotSyncedError(
        "Calendar data is not available yet.\nPlease sync Google Calendar first.",
        diagnostics={"matching_event_count": 0},
    )
    with patch(
        "app.api.briefs.StudyBriefService.generate_range_brief",
        side_effect=err,
    ):
        response = client.post(
            "/briefs/range",
            json={
                "user_id": str(uuid4()),
                "start_date": "2026-08-06",
                "end_date": "2026-08-07",
            },
        )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "calendar_not_synced"
    assert "Calendar data is not available" in detail["message"]


def test_api_maps_no_events_to_422_not_404():
    client = TestClient(app)
    err = NoEventsInRangeError(
        "No events were found in the selected date range.\nChoose another range.",
        diagnostics={"matching_event_count": 0},
    )
    with patch(
        "app.api.briefs.StudyBriefService.generate_range_brief",
        side_effect=err,
    ):
        response = client.post(
            "/briefs/range",
            json={
                "user_id": str(uuid4()),
                "start_date": "2026-08-06",
                "end_date": "2026-08-07",
            },
        )
    assert response.status_code == 422
    assert response.status_code != 404
    detail = response.json()["detail"]
    assert detail["code"] == "no_events_in_range"


def test_event_local_date_filter_matches_host_timezone():
    user_id = uuid4()
    start = datetime(2026, 8, 7, 23, 30, tzinfo=timezone.utc)
    event = ClassifiedCalendarEvent(
        id="tz",
        title="Late exam",
        category=EventCategory.EXAM,
        start=start,
        end=start + timedelta(hours=1),
    )
    calendar_module._synced_events[str(user_id)] = [event]
    cal = CalendarService()
    cal._users = MagicMock()
    cal._users.get_user_profile.return_value = {"id": str(user_id)}
    local_day = start.astimezone().date()
    matched = cal.get_events_in_range(user_id, local_day, local_day)
    assert len(matched) == 1


def test_ai_mode_preserved_on_success_path():
    user_id = uuid4()
    cal = CalendarService()
    cal._users = MagicMock()
    cal._users.get_user_profile.return_value = {"id": str(user_id)}
    calendar_module._synced_events[str(user_id)] = [_event(days=1)]

    from app.schemas.brief_schema import PriorityItem, StructuredStudyPlan

    from app.schemas.brief_schema import DailyPlan, StudyPlanItem

    plan = StructuredStudyPlan(
        summary="Focus",
        priority_item=PriorityItem(title="Exam", reason="Soon"),
        daily_plan=[
            DailyPlan(
                date=datetime.now().astimezone().date().isoformat(),
                items=[
                    StudyPlanItem(
                        start_time="09:00",
                        end_time="10:00",
                        title="Exam prep",
                        action="Review",
                        kind="study",
                    )
                ],
            )
        ],
        tips=["Tip"],
    )
    ai = MagicMock()
    ai.generate_study_plan.return_value = (plan, "text", "ollama", [])
    ai.last_fallback_reason = None
    ai.last_ollama_called = True
    ai.last_ollama_answered = True
    ai.last_ollama_elapsed_sec = 0.1
    svc = StudyBriefService(
        calendar_service=cal,
        ai_service=ai,
        activity_repository=MagicMock(),
        supabase_gateway=MagicMock(),
    )
    today = datetime.now().astimezone().date()
    end = today + timedelta(days=2)
    result = svc.generate_range_brief(user_id, today.isoformat(), end.isoformat())
    assert result.ai_mode == "ollama"
    assert result.event_count == 1
    assert result.meta.get("fallback_reason") is None
    assert result.meta.get("ollama_called") is True
