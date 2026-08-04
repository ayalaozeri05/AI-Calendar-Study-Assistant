"""Dashboard Presenter — orchestrates view and FastAPI client."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from api_client.backend_client import BackendClient
from models.dashboard_models import DashboardState, StudentInfo
from views.dashboard_view import DashboardView


class DashboardPresenter:
    def __init__(self, view: DashboardView, client: BackendClient) -> None:
        self.view = view
        self.client = client
        self.state = DashboardState()

        self.view.load_demo_requested.connect(self.load_demo_student)
        self.view.sync_calendar_requested.connect(self.sync_calendar)
        self.view.show_today_requested.connect(self.show_today_events)
        self.view.generate_brief_requested.connect(self.generate_today_brief)
        self.view.send_telegram_requested.connect(self.send_brief_to_telegram)

    def _require_student(self) -> str | None:
        if not self.state.student:
            self.view.show_status("Load a demo student first.", is_error=True)
            return None
        return self.state.student.id

    def load_demo_student(self) -> None:
        self.view.set_busy(True)
        self.view.show_status("Loading demo student...")
        QApplication.processEvents()
        try:
            user = self.client.create_demo_user()
            self.state.student = StudentInfo(
                id=str(user["id"]),
                email=user.get("email", ""),
                full_name=user.get("full_name"),
                telegram_chat_id=user.get("telegram_chat_id"),
            )
            name = self.state.student.full_name or "Demo Student"
            self.view.set_student_header(name, self.state.student.email)
            chat = self.state.student.telegram_chat_id or "(not set)"
            self.view.show_status(
                f"Demo student loaded. Telegram chat id: {chat}"
            )
        except Exception as err:
            self.view.show_status(str(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def sync_calendar(self) -> None:
        user_id = self._require_student()
        if not user_id:
            return

        self.view.set_busy(True)
        self.view.show_status("Syncing calendar...")
        QApplication.processEvents()
        try:
            result = self.client.sync_calendar(user_id)
            events = result.get("events", [])
            self.state.last_sync_source = result.get("source", "")
            self.state.last_sync_count = result.get("synced_count", len(events))
            self.state.events = events
            self.view.populate_events(events)
            self.view.show_status(
                f"Synced {self.state.last_sync_count} events "
                f"(source: {self.state.last_sync_source})."
            )
        except Exception as err:
            self.view.show_status(str(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def show_today_events(self) -> None:
        user_id = self._require_student()
        if not user_id:
            return

        self.view.set_busy(True)
        self.view.show_status("Loading today's events...")
        QApplication.processEvents()
        try:
            result = self.client.get_today_events(user_id)
            events = result.get("events", [])
            self.state.events = events
            self.view.populate_events(events)
            day = result.get("date", "today")
            self.view.show_status(f"Showing {len(events)} events for {day}.")
        except Exception as err:
            self.view.show_status(str(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def generate_today_brief(self) -> None:
        user_id = self._require_student()
        if not user_id:
            return

        self.view.set_busy(True)
        self.view.show_status("Generating today brief...")
        QApplication.processEvents()
        try:
            result = self.client.generate_today_brief(user_id)
            text = result.get("text", "")
            self.state.brief_text = text
            self.view.set_brief_text(text)
            count = result.get("event_count", 0)
            self.view.show_status(f"Today brief generated ({count} events).")
        except Exception as err:
            self.view.show_status(str(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def send_brief_to_telegram(self) -> None:
        user_id = self._require_student()
        if not user_id:
            return

        self.view.set_busy(True)
        self.view.show_status("Sending brief to Telegram...")
        QApplication.processEvents()
        try:
            brief_text = self.state.brief_text.strip() if self.state.brief_text else None
            if not brief_text:
                brief = self.client.generate_today_brief(user_id)
                brief_text = brief.get("text", "")
                self.state.brief_text = brief_text
                self.view.set_brief_text(brief_text)

            result = self.client.send_brief_to_telegram(
                user_id, "today", brief_text=brief_text
            )
            self.view.show_status(
                result.get("message", "Brief sent to Telegram successfully.")
            )
        except Exception as err:
            self.view.show_status(self._format_telegram_error(err), is_error=True)
        finally:
            self.view.set_busy(False)

    @staticmethod
    def _format_telegram_error(err: Exception) -> str:
        message = str(err)
        for prefix in ("API Error (404): ", "API Error (400): ", "API Error (502): "):
            if message.startswith(prefix):
                message = message[len(prefix) :]
        if message == "Telegram bot token is missing.":
            return message
        if "Telegram chat ID is missing" in message:
            return (
                "Telegram chat ID is missing. Open the bot, press Start, "
                "and configure DEMO_TELEGRAM_CHAT_ID."
            )
        # Pass through exact Telegram API errors (e.g. "Bad Request: chat not found").
        return message
