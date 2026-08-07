"""Academic journal planner — polished hierarchy and stationery layout."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from widgets.brief_panel import BriefPanel
from widgets.event_card import EventCard
from widgets.range_selector import RangeSelector
from widgets.study_materials_panel import StudyMaterialsPanel
from widgets.summary_card import SummaryCard
from widgets.workload_timeline import WorkloadTimeline


class PlannerPage(QWidget):
    range_changed = Signal(str, str, str)
    generate_brief_requested = Signal()
    regenerate_brief_requested = Signal()
    send_telegram_requested = Signal()
    sync_requested = Signal()
    back_requested = Signal()
    rag_upload_requested = Signal(str, str)
    rag_remove_requested = Signal(str)  # document_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mode = "today"
        self._start = ""
        self._end = ""
        self._calendar_connected = False
        self._has_synced = False

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.btn_back = QPushButton("← Calendar")
        self.btn_back.setObjectName("textBack")
        self.btn_back.clicked.connect(self.back_requested.emit)
        title_row.addWidget(self.btn_back, 0, Qt.AlignVCenter)

        title = QLabel("Your study planner")
        title.setObjectName("pageTitle")
        title_row.addWidget(title, 0, Qt.AlignVCenter)
        title_row.addStretch()

        self.btn_sync = QPushButton("Sync")
        self.btn_sync.setObjectName("textBack")
        self.btn_sync.setToolTip("Refresh Google Calendar")
        self.btn_sync.clicked.connect(self.sync_requested.emit)
        title_row.addWidget(self.btn_sync, 0, Qt.AlignVCenter)
        root.addLayout(title_row)

        self.status_line = QLabel("")
        self.status_line.setObjectName("headerStatus")
        self.status_line.setWordWrap(True)
        root.addWidget(self.status_line)

        doodle = QLabel("∼ ∼ ∼")
        doodle.setObjectName("doodleLine")
        root.addWidget(doodle)

        self.range_selector = RangeSelector()
        self.range_selector.range_changed.connect(self._on_range)
        root.addWidget(self.range_selector)

        self.summary = SummaryCard()
        self.summary.hide()
        root.addWidget(self.summary, 0)

        # Body: left events column + optional right plan column
        body = QHBoxLayout()
        body.setSpacing(12)
        body.setAlignment(Qt.AlignTop)

        # Left column as a real widget so HBox cannot vertically center a bare layout
        self.left_host = QWidget()
        self.left_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.left_host.setLayoutDirection(Qt.LeftToRight)
        left = QVBoxLayout(self.left_host)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)
        left.setAlignment(Qt.AlignTop)
        self._left = left

        self.events_label = QLabel("EVENTS")
        self.events_label.setObjectName("eventsHeading")
        self.events_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        left.addWidget(self.events_label, 0)

        # Empty-state card — stretch factor ALWAYS 0; never below a stretch item
        self.empty_card = QFrame()
        self.empty_card.setObjectName("emptyCard")
        self.empty_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.empty_card.setMaximumWidth(900)
        self.empty_card.setMinimumWidth(240)
        empty_layout = QVBoxLayout(self.empty_card)
        empty_layout.setContentsMargins(16, 14, 16, 14)
        empty_layout.setSpacing(6)
        empty_layout.setAlignment(Qt.AlignTop)

        self.empty_title = QLabel("No events today")
        self.empty_title.setObjectName("cardTitle")
        self.empty_title.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.empty_title.setWordWrap(True)

        self.empty_message = QLabel("Your calendar is clear for the rest of today.")
        self.empty_message.setObjectName("pageSubtitle")
        self.empty_message.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.empty_message.setWordWrap(True)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.setContentsMargins(0, 6, 0, 0)
        self.btn_empty_primary = QPushButton("View next 7 days")
        self.btn_empty_primary.setObjectName("compactPrimary")
        self.btn_empty_primary.clicked.connect(self._on_empty_primary)
        self.btn_empty_sync = QPushButton("Sync again")
        self.btn_empty_sync.setObjectName("textBack")
        self.btn_empty_sync.clicked.connect(self.sync_requested.emit)
        actions.addWidget(self.btn_empty_primary, 0, Qt.AlignLeft)
        actions.addWidget(self.btn_empty_sync, 0, Qt.AlignLeft)
        actions.addStretch(1)

        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_message)
        empty_layout.addLayout(actions)

        left.addWidget(self.empty_card, 0)
        self.empty_card.hide()

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.events_host = QWidget()
        self.events_host.setObjectName("eventsCanvas")
        self.events_layout = QVBoxLayout(self.events_host)
        self.events_layout.setContentsMargins(0, 0, 2, 0)
        self.events_layout.setSpacing(8)
        self.scroll.setWidget(self.events_host)
        left.addWidget(self.scroll, 1)

        # Trailing stretch used only in empty mode (scroll stretch set to 0).
        # Must come AFTER the empty card so leftover height sits below it.
        left.addStretch(0)

        body.addWidget(self.left_host, 62)

        self.right_host = QWidget()
        self.right_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right = QVBoxLayout(self.right_host)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        self.timeline = WorkloadTimeline()
        self.timeline.hide()
        self.timeline.setMaximumHeight(140)
        self.timeline.setMinimumHeight(0)
        self.timeline.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        right.addWidget(self.timeline, 0)

        self.brief = BriefPanel()
        self.brief.generate_requested.connect(self.generate_brief_requested.emit)
        self.brief.regenerate_requested.connect(self.regenerate_brief_requested.emit)
        self.brief.send_telegram_requested.connect(self.send_telegram_requested.emit)
        # Workload (compact) → Study Plan (stretch) → Study Materials (compact).
        self.brief.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.brief.setMinimumHeight(400)
        right.addWidget(self.brief, 1)

        self.study_materials = StudyMaterialsPanel()
        self.study_materials.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.study_materials.upload_requested.connect(self.rag_upload_requested.emit)
        self.study_materials.remove_requested.connect(self.rag_remove_requested.emit)
        right.addWidget(self.study_materials, 0)

        self.brief.hide()
        self.right_host.hide()
        body.addWidget(self.right_host, 40)

        root.addLayout(body, 1)

        mode, start, end = self.range_selector.current_range()
        self._mode, self._start, self._end = mode, start, end

    def set_sync_context(self, *, connected: bool, has_synced: bool) -> None:
        self._calendar_connected = bool(connected)
        self._has_synced = bool(has_synced)
        if self.empty_card.isVisible():
            self._apply_empty_copy()

    def _on_empty_primary(self) -> None:
        mode = self._mode or "today"
        if mode == "today":
            self.range_selector.set_mode("7days", emit=True)
        elif mode == "7days":
            self.range_selector.set_mode("14days", emit=True)
        elif mode == "14days":
            self.range_selector.set_mode("month", emit=True)
        elif mode == "month":
            self.range_selector.set_mode("custom", emit=True)
        else:
            self.range_selector.set_mode("custom", emit=True)

    def _on_range(self, mode: str, start: str, end: str) -> None:
        self._mode = mode
        self._start = start
        self._end = end
        self.brief.clear()
        self.brief.set_mode(mode)
        self.range_changed.emit(mode, start, end)

    def current_range(self) -> tuple[str, str, str]:
        return self._mode, self._start, self._end

    def set_header_status(self, text: str) -> None:
        self.status_line.setText(text)
        self.status_line.setVisible(bool(text.strip()))

    def set_back_visible(self, visible: bool) -> None:
        self.btn_back.setVisible(visible)

    def _set_empty_layout_active(self, empty: bool) -> None:
        """Empty: card under EVENTS + stretch after. Events: scroll fills; no gap."""
        if empty:
            self.scroll.hide()
            self._left.setStretchFactor(self.scroll, 0)
            self.empty_card.show()
            # Stretch AFTER the empty card absorbs leftover window height
            self._left.setStretch(self._left.indexOf(self.empty_card), 0)
            # Last item is the stretch spacer — give it factor 1
            stretch_index = self._left.count() - 1
            self._left.setStretch(stretch_index, 1)
        else:
            self.empty_card.hide()
            stretch_index = self._left.count() - 1
            self._left.setStretch(stretch_index, 0)
            self.scroll.show()
            self._left.setStretchFactor(self.scroll, 1)

    def _apply_empty_copy(self) -> None:
        never_synced = not self._has_synced and not self._calendar_connected
        mode = self._mode or "today"

        if mode == "today":
            title = "No events today"
            message = "Your calendar is clear for the rest of today."
            primary = "View next 7 days"
        elif mode == "7days":
            title = "No events in the next 7 days"
            message = "Try a longer range or sync your calendar again."
            primary = "View 14 days"
        elif mode == "14days":
            title = "No events in the next 14 days"
            message = "Your calendar has no upcoming items in this range."
            primary = "View this month"
        elif mode == "month":
            title = "No events this month"
            message = "Choose a custom range or sync your calendar again."
            primary = "Choose dates"
        else:
            title = "No events in this date range"
            message = "Try different dates or sync your calendar again."
            primary = "Change dates"

        sync_label = "Sync calendar" if never_synced else "Sync again"

        self.empty_title.setText(title)
        self.empty_message.setText(message)
        self.empty_message.setVisible(True)
        self.btn_empty_primary.setText(primary)
        self.btn_empty_primary.setVisible(True)
        self.btn_empty_sync.setText(sync_label)

    def populate_events(self, events: list[dict]) -> None:
        self.brief.set_mode(self._mode)
        self.brief.set_events_context(events)
        while self.events_layout.count():
            item = self.events_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not events:
            self.timeline.hide()
            self.summary.hide()
            self.brief.hide()
            self.right_host.hide()
            self._apply_empty_copy()
            self._set_empty_layout_active(True)
            return

        self._set_empty_layout_active(False)
        self.right_host.show()
        self.summary.update_from_events(events, mode=self._mode)
        self.brief.show()
        self.study_materials.show()
        self.brief.clear()
        self.brief.set_mode(self._mode)
        self.brief.set_events_context(events)

        if self._mode == "today":
            self.timeline.hide()
            for event in events:
                self.events_layout.addWidget(EventCard(event))
        elif self._mode == "month":
            self.timeline.update_from_events(events, self._start, self._end, self._mode)
            self._populate_by_week(events)
        else:
            self.timeline.update_from_events(events, self._start, self._end, self._mode)
            self._populate_by_day(events)

        self.events_layout.addStretch()

    def _populate_by_day(self, events: list[dict]) -> None:
        by_day: dict[str, list[dict]] = defaultdict(list)
        for event in events:
            by_day[self._day_key(event.get("start"))].append(event)
        for day in sorted(by_day.keys()):
            header = QLabel(self._day_label(day, by_day[day][0].get("start")))
            header.setObjectName("dayHeader")
            self.events_layout.addWidget(header)
            for event in by_day[day]:
                self.events_layout.addWidget(EventCard(event))

    def _populate_by_week(self, events: list[dict]) -> None:
        by_day: dict[str, list[dict]] = defaultdict(list)
        for event in events:
            by_day[self._day_key(event.get("start"))].append(event)
        if not by_day:
            return
        sorted_days = sorted(by_day.keys())
        first = datetime.fromisoformat(sorted_days[0]).date()
        try:
            range_start = datetime.fromisoformat(self._start).date()
        except Exception:
            range_start = first

        week_buckets: dict[int, list[str]] = defaultdict(list)
        for day_s in sorted_days:
            d = datetime.fromisoformat(day_s).date()
            week_index = (d - range_start).days // 7
            week_buckets[week_index].append(day_s)

        for week_i in sorted(week_buckets.keys()):
            week_header = QLabel(f"Week {week_i + 1}")
            week_header.setObjectName("weekHeader")
            self.events_layout.addWidget(week_header)
            for day_s in week_buckets[week_i]:
                header = QLabel(self._day_label(day_s, by_day[day_s][0].get("start")))
                header.setObjectName("dayHeader")
                self.events_layout.addWidget(header)
                for event in by_day[day_s]:
                    self.events_layout.addWidget(EventCard(event))

    def clear_brief(self) -> None:
        self.brief.clear()

    def set_brief(
        self,
        text: str,
        plan: dict | None = None,
        *,
        ai_mode: str | None = None,
        rag_enhanced: bool = False,
        rag_message: str | None = None,
    ) -> None:
        if (text or "").strip() or plan:
            # Parent host must be visible — showing only BriefPanel is a no-op when hidden.
            self.right_host.show()
            self.brief.show()
            self.study_materials.show()
        self.brief.set_brief(
            text,
            plan=plan,
            ai_mode=ai_mode,
            rag_enhanced=rag_enhanced,
            rag_message=rag_message,
        )

    def set_busy(self, busy: bool) -> None:
        self.btn_back.setEnabled(not busy)
        self.btn_sync.setEnabled(not busy)
        self.range_selector.setEnabled(not busy)
        self.brief.set_busy(busy)
        self.btn_empty_primary.setEnabled(not busy)
        self.btn_empty_sync.setEnabled(not busy)
        self.study_materials.set_busy(busy)

    @staticmethod
    def _day_key(value: str | None) -> str:
        if not value:
            return "unknown"
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
        except Exception:
            return str(value)[:10]

    @staticmethod
    def _day_label(key: str, sample_start: str | None) -> str:
        try:
            dt = datetime.fromisoformat(str(sample_start).replace("Z", "+00:00"))
            return dt.strftime("%A, %b %d")
        except Exception:
            return key
