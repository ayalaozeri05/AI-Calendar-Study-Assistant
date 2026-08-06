"""Build today/weekly/range study briefs from classified calendar events."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
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
from app.services.telegram_message_splitter import split_telegram_message
from app.services.telegram_plan_formatter import format_plan_for_telegram
from app.services.user_service import UserService

_CATEGORY_ORDER = (
    EventCategory.EXAM,
    EventCategory.ASSIGNMENT,
    EventCategory.PROJECT,
    EventCategory.STUDY,
    EventCategory.CLASS,
    EventCategory.MEETING,
    EventCategory.OTHER,
)

_CATEGORY_HEADERS = {
    EventCategory.EXAM: "Exam",
    EventCategory.ASSIGNMENT: "Assignment",
    EventCategory.PROJECT: "Project",
    EventCategory.STUDY: "Study",
    EventCategory.CLASS: "Class",
    EventCategory.MEETING: "Meeting",
    EventCategory.OTHER: "Other",
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
        today = datetime.now(timezone.utc).date()
        return self.generate_range_brief(
            user_id,
            today.isoformat(),
            today.isoformat(),
            label=f"Study Plan — {today.isoformat()}",
            brief_type=BriefType.TODAY,
        )

    def generate_weekly_brief(self, user_id: UUID) -> BriefResponse:
        today = datetime.now(timezone.utc).date()
        end = date.fromordinal(today.toordinal() + 6)
        return self.generate_range_brief(
            user_id,
            today.isoformat(),
            end.isoformat(),
            label=f"Study Plan — next 7 days from {today.isoformat()}",
            brief_type=BriefType.WEEKLY,
        )

    def generate_range_brief(
        self,
        user_id: UUID,
        start_date: str,
        end_date: str,
        label: str | None = None,
        brief_type: BriefType = BriefType.RANGE,
        regenerate: bool = False,
        previous_plan: dict | None = None,
        variation_seed: int | None = None,
        planning_anchor: str | None = None,
    ) -> BriefResponse:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start > end:
            raise ValueError("start_date must be on or before end_date.")

        events = self._calendar.get_events_in_range(user_id, start, end)
        if not events:
            raise ValueError(
                "No events are scheduled for the selected dates.\n"
                "Sync Google Calendar first, then try again."
            )

        # Use local timezone for "today" / future-day decisions
        local_now = datetime.now().astimezone()
        plan, plan_text, ai_mode = self._ai.generate_study_plan(
            events,
            start=start,
            end=end,
            now=local_now,
            regenerate=regenerate,
            previous_plan=previous_plan,
            variation_seed=variation_seed,
            planning_anchor=planning_anchor,
        )

        title = label or f"Study Plan — {start.isoformat()} to {end.isoformat()}"
        text = f"{title}\n\n{plan_text}"
        anchor = plan.planning_anchor

        self._persist_brief(user_id, title, text)
        self._activity.log_event(
            user_id=user_id,
            event_type="brief_generated",
            entity_type="brief",
            description=f"{brief_type.value} brief with {len(events)} events ({ai_mode})",
        )

        return BriefResponse(
            user_id=user_id,
            brief_type=brief_type,
            text=text,
            event_count=len(events),
            ai_mode=ai_mode,
            plan=plan,
            planning_anchor=anchor,
            meta={"ai_mode": ai_mode, "planning_anchor": anchor},
        )

    def send_brief_to_telegram(
        self,
        user_id: UUID,
        brief_type: BriefType,
        brief_text: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        plan: dict | None = None,
    ) -> SendTelegramResponse:
        if not settings.telegram_bot_token.strip():
            raise ValueError("Telegram bot token is missing.")

        user = self._user_service.sync_telegram_chat_id_from_env_by_id(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")

        chat_id = (user.telegram_chat_id or "").strip()
        if not chat_id:
            raise ValueError(
                "Telegram chat ID is missing. Open the bot, press Start, "
                "and configure DEMO_TELEGRAM_CHAT_ID."
            )

        range_label = None
        if start_date and end_date:
            range_label = f"STUDY PLAN — {start_date} to {end_date}"

        if plan:
            text = format_plan_for_telegram(plan, range_label=range_label)
        elif brief_text and brief_text.strip():
            text = brief_text.strip()
        elif brief_type == BriefType.TODAY:
            generated = self.generate_today_brief(user_id)
            text = (
                format_plan_for_telegram(generated.plan, range_label=range_label)
                if generated.plan
                else generated.text
            )
        elif brief_type == BriefType.WEEKLY:
            generated = self.generate_weekly_brief(user_id)
            text = (
                format_plan_for_telegram(generated.plan, range_label=range_label)
                if generated.plan
                else generated.text
            )
        elif start_date and end_date:
            generated = self.generate_range_brief(user_id, start_date, end_date)
            text = (
                format_plan_for_telegram(generated.plan, range_label=range_label)
                if generated.plan
                else generated.text
            )
        else:
            generated = self.generate_weekly_brief(user_id)
            text = (
                format_plan_for_telegram(generated.plan, range_label=range_label)
                if generated.plan
                else generated.text
            )

        chunks = split_telegram_message(text)
        if not chunks:
            raise ValueError("Study plan is empty — nothing to send.")

        parts_sent = 0
        total = len(chunks)
        try:
            for chunk in chunks:
                self._telegram.send_message(chat_id, chunk)
                parts_sent += 1
        except Exception as exc:
            if parts_sent == 0:
                raise
            raise RuntimeError(
                f"Parts 1–{parts_sent} were sent, but part {parts_sent + 1} failed: {exc}"
            ) from exc

        if total == 1:
            message = "Study plan sent to Telegram."
        else:
            message = f"Study plan sent to Telegram in {total} messages."

        self._activity.log_event(
            user_id=user_id,
            event_type="telegram_sent",
            entity_type="brief",
            description=f"Sent {brief_type.value} brief to Telegram ({total} parts)",
        )

        return SendTelegramResponse(
            user_id=user_id,
            brief_type=brief_type,
            sent=True,
            success=True,
            message=message,
            parts_sent=parts_sent,
            total_parts=total,
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
            pass


def _format_event_block(item: ClassifiedCalendarEvent) -> list[str]:
    time_str = item.start.strftime("%H:%M")
    lines = [f"  • {time_str} — {item.title}"]
    description = (item.description or "").strip()
    if description:
        for desc_line in description.splitlines():
            lines.append(f"    {desc_line}")
    return lines


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
            lines.extend(_format_event_block(item))
        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else "No events."

