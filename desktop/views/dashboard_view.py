"""Three-state desktop shell: Start → Calendar → Planner."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from pages.calendar_page import CalendarPage
from pages.planner_page import PlannerPage
from pages.start_page import StartPage
from styles import load_app_stylesheet
from widgets.toast import ToastBar


class DashboardView(QMainWindow):
    load_demo_requested = Signal()
    connect_calendar_requested = Signal()
    sync_calendar_requested = Signal()
    range_events_requested = Signal(str, str, str)
    generate_brief_requested = Signal()
    regenerate_brief_requested = Signal()
    send_telegram_requested = Signal()
    rag_upload_requested = Signal(str, str)
    rag_remove_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Calendar Study Assistant")
        self.resize(1220, 800)
        self.setMinimumSize(980, 660)
        self.setStyleSheet(load_app_stylesheet())

        self._signed_in_email = ""
        self._google_email = ""
        self._calendar_connected = False
        self._last_synced: datetime | None = None
        self._build()
        self._wire()
        self.show_start()

    def _build(self) -> None:
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(4)

        self.toast = ToastBar()
        root.addWidget(self.toast)

        self.stack = QStackedWidget()
        self.start_page = StartPage()
        self.calendar_page = CalendarPage()
        self.planner_page = PlannerPage()
        self.stack.addWidget(self.start_page)
        self.stack.addWidget(self.calendar_page)
        self.stack.addWidget(self.planner_page)
        root.addWidget(self.stack, 1)

    def _wire(self) -> None:
        self.start_page.start_requested.connect(self.load_demo_requested.emit)
        self.calendar_page.connect_requested.connect(self.connect_calendar_requested.emit)
        self.calendar_page.sync_requested.connect(self.sync_calendar_requested.emit)
        self.calendar_page.back_requested.connect(self.show_start)

        self.planner_page.range_changed.connect(self.range_events_requested.emit)
        self.planner_page.generate_brief_requested.connect(self.generate_brief_requested.emit)
        self.planner_page.regenerate_brief_requested.connect(
            self.regenerate_brief_requested.emit
        )
        self.planner_page.send_telegram_requested.connect(self.send_telegram_requested.emit)
        self.planner_page.sync_requested.connect(self.sync_calendar_requested.emit)
        self.planner_page.back_requested.connect(self.show_calendar)
        self.planner_page.rag_upload_requested.connect(self.rag_upload_requested.emit)
        self.planner_page.rag_remove_requested.connect(self.rag_remove_requested.emit)

    def show_start(self) -> None:
        self.stack.setCurrentWidget(self.start_page)

    def show_calendar(self) -> None:
        self.stack.setCurrentWidget(self.calendar_page)

    def show_planner(self) -> None:
        self.stack.setCurrentWidget(self.planner_page)
        self.planner_page.set_back_visible(True)
        self._refresh_planner_header()

    def _refresh_planner_header(self) -> None:
        lines: list[str] = []
        # Never show the internal demo profile email in the main UI
        email = (self._google_email or "").strip()
        if email.lower() == "demo@student.local":
            email = ""
        if self._calendar_connected:
            lines.append("Connected to your Google Calendar")
            if email:
                lines.append(email)
        else:
            lines.append("Google Calendar not connected")
        if self._last_synced is not None:
            when = self._last_synced
            today = datetime.now().date()
            if when.date() == today:
                lines.append(f"Last synced: Today {when.strftime('%H:%M')}")
            else:
                lines.append(f"Last synced: {when.strftime('%d %b %H:%M')}")
        self.planner_page.set_header_status("\n".join(lines))
        self.planner_page.set_sync_context(
            connected=self._calendar_connected,
            has_synced=self._last_synced is not None,
        )

    def set_student_header(self, name: str, email: str) -> None:
        # Keep demo profile email internal; display Google account when available
        self._signed_in_email = email or name or ""
        self.start_page.set_profile_ready(True)
        self.calendar_page.set_profile_ready(True)
        self._refresh_planner_header()

    def set_calendar_connection_status(
        self, status: str, google_email: str | None = None
    ) -> None:
        self._calendar_connected = status == "Connected"
        if google_email:
            self._google_email = google_email.strip()
        elif status != "Connected":
            self._google_email = ""
        if status == "Connected":
            self.calendar_page.set_connected(True)
        elif status == "Credentials missing":
            self.calendar_page.set_credentials_missing()
        else:
            self.calendar_page.set_connected(False)
        self._refresh_planner_header()

    def show_status(self, message: str, is_error: bool = False) -> None:
        text = (message or "").strip()
        if not text:
            return
        # Avoid duplicating header info as toast noise
        lowered = text.lower()
        if "student profile ready" in lowered or "profile ready" in lowered:
            return
        if is_error:
            kind = "error"
        elif any(
            k in lowered
            for k in (
                "no events",
                "empty",
                "not connected",
                "not available yet",
                "choose another range",
                "rule-based",
                "timed out",
            )
        ):
            kind = "warning"
        else:
            kind = "success"
        self.toast.show_message(text.replace("\n", " "), kind=kind)

    def set_busy(self, busy: bool) -> None:
        self.start_page.set_busy(busy)
        self.calendar_page.set_busy(busy)
        self.planner_page.set_busy(busy)

    def set_syncing(self, syncing: bool) -> None:
        self.calendar_page.set_syncing(syncing)

    def populate_events(self, events: list[dict]) -> None:
        self.planner_page.set_sync_context(
            connected=self._calendar_connected,
            has_synced=self._last_synced is not None or self._calendar_connected,
        )
        self.planner_page.populate_events(events)

    def set_brief_text(
        self,
        text: str,
        brief_type: str | None = None,
        plan: dict | None = None,
        ai_mode: str | None = None,
        *,
        rag_enhanced: bool = False,
        rag_message: str | None = None,
    ) -> None:
        _ = brief_type
        self.planner_page.set_brief(
            text,
            plan=plan,
            ai_mode=ai_mode,
            rag_enhanced=rag_enhanced,
            rag_message=rag_message,
        )

    def current_brief_plan(self) -> dict | None:
        return self.planner_page.brief.current_plan()

    def set_plan_loading(self, loading: bool, *, regenerating: bool = False) -> None:
        self.planner_page.brief.set_loading(loading, regenerating=regenerating)

    def set_ai_source(self, ai_mode: str) -> None:
        self.planner_page.brief.set_ai_source(ai_mode)

    def set_telegram_sending(self, sending: bool) -> None:
        self.planner_page.brief.set_telegram_sending(sending)

    def clear_brief(self) -> None:
        self.planner_page.clear_brief()

    def current_range(self) -> tuple[str, str, str]:
        return self.planner_page.current_range()

    def on_sync_finished(self, events: list[dict], count: int) -> None:
        _ = events
        self._last_synced = datetime.now()
        self.calendar_page.set_syncing(False)
        self.calendar_page.show_sync_count(count)
        self.show_planner()
        self.toast.show_message("Calendar synced", kind="success")
        mode, start, end = self.planner_page.current_range()
        self.range_events_requested.emit(mode, start, end)

    def go_to_calendar_after_start(self) -> None:
        self.show_calendar()
