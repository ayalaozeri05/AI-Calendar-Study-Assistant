"""Build today/weekly study briefs from classified calendar events."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from app.config import settings
from app.gateways.supabase_gateway import SupabaseGateway
from app.gateways.telegram_gateway import TelegramGateway
from app.repositories.activity_repository import ActivityRepository
from app.repositories.user_repository import UserRepository
from app.schemas.brief_schema import BriefResponse, BriefType, SendTelegramResponse
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.ai_recommendation_service import AiRecommendationService
from app.services.calendar_service import CalendarService
from app.services.user_service import UserService

_CATEGORY_ORDER = (
    EventCategory.EXAM,
    EventCategory.ASSIGNMENT,
    EventCategory.PROJECT,
    EventCategory.STUDY,
    EventCategory.CLASS,
    EventCategory.OTHER,
)

_CATEGORY_HEADERS = {
    EventCategory.EXAM: "EXAMS",
    EventCategory.ASSIGNMENT: "ASSIGNMENTS",
    EventCategory.PROJECT: "PROJECTS",
    EventCategory.STUDY: "STUDY SESSIONS",
    EventCategory.CLASS: "CLASSES",
    EventCategory.OTHER: "OTHER",
}


class StudyBriefService:
    def __init__(
        self,
        calendar_service: CalendarService | None = None,
        user_repository: UserRepository | None = None,
        activity_repository: ActivityRepository | None = None,
        telegram_gateway: TelegramGateway | None = None,
        ai_service: AiRecommendationService | None = None,
        supabase_gateway: SupabaseGateway | None = None,
        user_service: UserService | None = None,
    ) -> None:
        self._calendar = calendar_service or CalendarService()
        self._users = user_repository or UserRepository()
        self._user_service = user_service or UserService()
        self._activity = activity_repository or ActivityRepository()
        self._telegram = telegram_gateway or TelegramGateway()
        self._ai = ai_service or AiRecommendationService()
        self._supabase = supabase_gateway or SupabaseGateway()

    def generate_today_brief(self, user_id: UUID) -> BriefResponse:
        today = self._calendar.get_today_events(user_id)
        if not today.events:
            raise ValueError(
                "No events for today. Run POST /calendar/sync first."
            )

        title = f"Today Study Brief — {today.date}"
        body = _format_events_by_category(today.events)
        tip = self._ai.suggest_focus(today.events)
        text = f"{title}\n\n{body}\n---\nTip: {tip}"

        self._persist_brief(user_id, "Today Study Brief", text)
        self._activity.log_event(
            user_id=user_id,
            event_type="brief_generated",
            entity_type="brief",
            description=f"Today brief with {len(today.events)} events",
        )

        return BriefResponse(
            user_id=user_id,
            brief_type=BriefType.TODAY,
            text=text,
            event_count=len(today.events),
        )

    def generate_weekly_brief(self, user_id: UUID) -> BriefResponse:
        events = self._calendar.get_week_events(user_id)
        if not events:
            raise ValueError(
                "No synced events. Run POST /calendar/sync first."
            )

        week_start = datetime.now(timezone.utc).date().isoformat()
        title = f"Weekly Study Brief — week of {week_start}"
        body = _format_weekly(events)
        tip = self._ai.suggest_focus(events)
        text = f"{title}\n\n{body}\n---\nTip: {tip}"

        self._persist_brief(user_id, "Weekly Study Brief", text)
        self._activity.log_event(
            user_id=user_id,
            event_type="brief_generated",
            entity_type="brief",
            description=f"Weekly brief with {len(events)} events",
        )

        return BriefResponse(
            user_id=user_id,
            brief_type=BriefType.WEEKLY,
            text=text,
            event_count=len(events),
        )

    def send_brief_to_telegram(
        self,
        user_id: UUID,
        brief_type: BriefType,
        brief_text: str | None = None,
    ) -> SendTelegramResponse:
        if not settings.telegram_bot_token.strip():
            raise ValueError("Telegram bot token is missing.")

        user = self._user_service.sync_telegram_chat_id_from_env_by_id(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")

        # Use telegram_chat_id stored on the user profile (synced from .env on demo load).
        chat_id = (user.telegram_chat_id or "").strip()
        if not chat_id:
            raise ValueError(
                "Telegram chat ID is missing. Open the bot, press Start, "
                "and configure DEMO_TELEGRAM_CHAT_ID."
            )

        if brief_text and brief_text.strip():
            text = brief_text.strip()
        elif brief_type == BriefType.TODAY:
            text = self.generate_today_brief(user_id).text
        else:
            text = self.generate_weekly_brief(user_id).text

        self._telegram.send_message(chat_id, text)

        self._activity.log_event(
            user_id=user_id,
            event_type="telegram_sent",
            entity_type="brief",
            description=f"Sent {brief_type.value} brief to Telegram",
        )

        return SendTelegramResponse(
            user_id=user_id,
            brief_type=brief_type,
            sent=True,
            message="Brief sent to Telegram successfully.",
        )

    def _persist_brief(self, user_id: UUID, question: str, answer: str) -> None:
        try:
            self._supabase.table("ai_chat_history").insert(
                {
                    "user_id": str(user_id),
                    "question": question,
                    "answer": answer,
                }
            ).execute()
        except Exception:
            # Non-fatal for MVP if Supabase write fails
            pass


def _format_events_by_category(events: list[ClassifiedCalendarEvent]) -> str:
    grouped: dict[EventCategory, list[ClassifiedCalendarEvent]] = defaultdict(list)
    for event in sorted(events, key=lambda e: e.start):
        grouped[event.category].append(event)

    sections: list[str] = []
    for category in _CATEGORY_ORDER:
        items = grouped.get(category, [])
        if not items:
            continue
        header = _CATEGORY_HEADERS[category]
        lines = [f"{header} ({len(items)})"]
        for item in items:
            time_str = item.start.strftime("%H:%M")
            lines.append(f"  • {time_str} — {item.title}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else "No events."


def _format_weekly(events: list[ClassifiedCalendarEvent]) -> str:
    by_day: dict[str, list[ClassifiedCalendarEvent]] = defaultdict(list)
    for event in sorted(events, key=lambda e: e.start):
        day_key = event.start.date().isoformat()
        by_day[day_key].append(event)

    sections: list[str] = []
    for day in sorted(by_day.keys()):
        day_events = by_day[day]
        sections.append(f"📅 {day} ({len(day_events)} events)")
        sections.append(_format_events_by_category(day_events))

    return "\n\n".join(sections)
