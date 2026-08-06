"""Presenter for Start → Calendar → Planner with range planning."""

from __future__ import annotations

import time

from PySide6.QtWidgets import QApplication

from api_client.backend_client import BackendClient
from models.dashboard_models import DashboardState, StudentInfo
from views.dashboard_view import DashboardView

_BRIEF_LABELS = {
    "today": "Today Study Plan",
    "7days": "7-Day Study Plan",
    "14days": "14-Day Study Plan",
    "month": "Monthly Study Plan",
    "custom": "Custom Study Plan",
}


class DashboardPresenter:
    def __init__(self, view: DashboardView, client: BackendClient) -> None:
        self.view = view
        self.client = client
        self.state = DashboardState()

        self.view.load_demo_requested.connect(self.start_planner)
        self.view.connect_calendar_requested.connect(self.connect_google_calendar)
        self.view.sync_calendar_requested.connect(self.sync_calendar)
        self.view.range_events_requested.connect(self.load_range_events)
        self.view.generate_brief_requested.connect(
            lambda: self.generate_range_brief(regenerate=False)
        )
        self.view.regenerate_brief_requested.connect(
            lambda: self.generate_range_brief(regenerate=True)
        )
        self.view.send_telegram_requested.connect(self.send_current_brief)

    def _require_student(self) -> str | None:
        if not self.state.student:
            self.view.show_status("Start the planner first.", is_error=True)
            return None
        return self.state.student.id

    def _refresh_calendar_status(self, user_id: str) -> None:
        try:
            status = self.client.get_calendar_status(user_id)
            connected = bool(status.get("connected"))
            self.state.calendar_connected = connected
            google_email = status.get("google_email")
            if not status.get("credentials_configured"):
                self.view.set_calendar_connection_status(
                    "Credentials missing", google_email=google_email
                )
            elif connected:
                self.view.set_calendar_connection_status(
                    "Connected", google_email=google_email
                )
            else:
                self.view.set_calendar_connection_status(
                    "Not connected", google_email=google_email
                )
        except Exception:
            self.state.calendar_connected = False
            self.view.set_calendar_connection_status("Not connected")

    def start_planner(self) -> None:
        if self.state.student:
            self._refresh_calendar_status(self.state.student.id)
            self.view.go_to_calendar_after_start()
            return

        self.view.set_busy(True)
        QApplication.processEvents()
        try:
            user = self.client.create_demo_user()
            self.state.student = StudentInfo(
                id=str(user["id"]),
                email=user.get("email", ""),
                full_name=user.get("full_name"),
                telegram_chat_id=user.get("telegram_chat_id"),
            )
            self.view.set_student_header(
                self.state.student.full_name or "Student",
                self.state.student.email,
            )
            self._refresh_calendar_status(self.state.student.id)
            self.view.go_to_calendar_after_start()
        except Exception as err:
            self.view.show_status(self._friendly_error(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def connect_google_calendar(self) -> None:
        user_id = self._require_student()
        if not user_id:
            return
        self.view.set_busy(True)
        self.view.show_status("Opening Google sign-in…")
        QApplication.processEvents()
        try:
            self.client.connect_google_calendar(user_id)
            self._refresh_calendar_status(user_id)
            self.view.show_status("Calendar connected")
        except Exception as err:
            self._refresh_calendar_status(user_id)
            self.view.show_status(self._friendly_error(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def sync_calendar(self) -> None:
        user_id = self._require_student()
        if not user_id:
            return
        self.view.set_busy(True)
        self.view.set_syncing(True)
        QApplication.processEvents()
        try:
            result = self.client.sync_google_calendar(user_id, days_ahead=62)
            events = result.get("events", [])
            self.state.last_sync_count = result.get("synced_count", len(events))
            self.state.events = events
            self.state.brief_text = ""
            self._refresh_calendar_status(user_id)
            self.view.on_sync_finished(events, self.state.last_sync_count)
        except Exception as err:
            self.view.set_syncing(False)
            self._refresh_calendar_status(user_id)
            self.view.show_status(self._friendly_error(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def load_range_events(self, mode: str, start_date: str, end_date: str) -> None:
        user_id = self._require_student()
        if not user_id:
            return
        self.view.set_busy(True)
        QApplication.processEvents()
        try:
            result = self.client.get_events_range(user_id, start_date, end_date)
            events = result.get("events", [])
            self.state.events = events
            self.state.brief_text = ""
            self.view.clear_brief()
            self.state.brief_text = ""
            self.state.brief_plan = None
            self.state.planning_anchor = None
            self.view.populate_events(events)
        except Exception as err:
            self.view.show_status(self._friendly_error(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def generate_range_brief(self, regenerate: bool = False) -> None:
        user_id = self._require_student()
        if not user_id:
            return
        if self.state.plan_request_in_flight:
            return

        mode, start, end = self.view.current_range()
        label = _BRIEF_LABELS.get(mode, "Study Plan")
        if mode != "today":
            label = f"{label} — {start} to {end}"
        else:
            label = f"{label} — {start}"

        previous_plan = None
        planning_anchor = None
        if regenerate:
            previous_plan = self.state.brief_plan or self.view.current_brief_plan()
            planning_anchor = self.state.planning_anchor
            if not planning_anchor and isinstance(previous_plan, dict):
                planning_anchor = previous_plan.get("planning_anchor")
        else:
            # Fresh Create — clear previous anchor so the engine captures a new one
            self.state.planning_anchor = None

        self.state.plan_request_in_flight = True
        self.view.set_plan_loading(True, regenerating=regenerate)
        self.view.set_busy(True)
        QApplication.processEvents()
        try:
            variation_seed = int(time.time() * 1000) % 10_000_000
            result = self.client.generate_range_brief(
                user_id,
                start,
                end,
                label=label,
                regenerate=regenerate,
                previous_plan=previous_plan,
                variation_seed=variation_seed,
                planning_anchor=planning_anchor,
            )
            text = result.get("text", "")
            plan = result.get("plan")
            if not text and not plan:
                raise RuntimeError("The planner returned an empty study plan.")
            self.state.brief_text = text
            self.state.brief_plan = plan if isinstance(plan, dict) else None
            anchor = result.get("planning_anchor")
            if not anchor and isinstance(plan, dict):
                anchor = plan.get("planning_anchor")
            if anchor:
                self.state.planning_anchor = str(anchor)
            self.state.last_brief_type = "range" if mode not in ("today", "7days") else (
                "today" if mode == "today" else "weekly"
            )
            self.view.set_brief_text(text, self.state.last_brief_type, plan=plan)
            if regenerate:
                self.view.show_status("Study plan updated")
            else:
                self.view.show_status("Study plan created")
        except Exception as err:
            message = self._friendly_error(err)
            self.view.show_status(
                message,
                is_error="no events" not in message.lower(),
            )
        finally:
            self.state.plan_request_in_flight = False
            self.view.set_plan_loading(False, regenerating=regenerate)
            self.view.set_busy(False)

    def send_current_brief(self) -> None:
        user_id = self._require_student()
        if not user_id:
            return
        if self.state.telegram_send_in_flight:
            return
        mode, start, end = self.view.current_range()
        brief_type = (
            "today"
            if mode == "today"
            else "weekly"
            if mode == "7days"
            else "range"
        )
        self.state.telegram_send_in_flight = True
        self.view.set_telegram_sending(True)
        self.view.set_busy(True)
        QApplication.processEvents()
        try:
            brief_text = self.state.brief_text.strip() or None
            plan = self.state.brief_plan or self.view.current_brief_plan()
            if not brief_text and not plan:
                label = _BRIEF_LABELS.get(mode, "Study Plan")
                result = self.client.generate_range_brief(
                    user_id, start, end, label=label
                )
                brief_text = result.get("text", "")
                plan = result.get("plan")
                self.state.brief_text = brief_text
                self.state.brief_plan = plan if isinstance(plan, dict) else None
                self.view.set_brief_text(
                    brief_text, brief_type, plan=plan
                )

            result = self.client.send_brief_to_telegram(
                user_id,
                brief_type=brief_type,
                brief_text=brief_text,
                start_date=start,
                end_date=end,
                plan=plan if isinstance(plan, dict) else None,
            )
            message = result.get("message") or "Study plan sent to Telegram."
            self.view.show_status(message)
        except Exception as err:
            self.view.show_status(self._friendly_error(err), is_error=True)
        finally:
            self.state.telegram_send_in_flight = False
            self.view.set_telegram_sending(False)
            self.view.set_busy(False)

    @staticmethod
    def _friendly_error(err: Exception) -> str:
        message = str(err)
        for prefix in (
            "API Error (404): ",
            "API Error (400): ",
            "API Error (502): ",
            "API Error (500): ",
            "Connection Error: ",
        ):
            if message.startswith(prefix):
                message = message[len(prefix) :]
        lowered = message.lower()
        if "not connected" in lowered:
            return "Google Calendar is not connected yet."
        if "no events" in lowered:
            return "No events scheduled for the selected dates."
        if "telegram bot token is missing" in lowered:
            return "Telegram is not configured yet."
        if "telegram chat id is missing" in lowered:
            return "Telegram chat is not set up yet."
        if "failed to establish" in lowered or "connection refused" in lowered:
            return "Cannot reach the server. Start the backend first."
        return message.split("\n")[0][:160]
