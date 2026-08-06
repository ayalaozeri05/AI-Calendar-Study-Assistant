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
    QVBoxLayout,
    QWidget,
)

from widgets.brief_panel import BriefPanel
from widgets.event_card import EventCard
from widgets.range_selector import RangeSelector
from widgets.summary_card import SummaryCard
from widgets.workload_timeline import WorkloadTimeline


class PlannerPage(QWidget):
    range_changed = Signal(str, str, str)
    generate_brief_requested = Signal()
    regenerate_brief_requested = Signal()
    send_telegram_requested = Signal()
    sync_requested = Signal()
    back_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mode = "today"
        self._start = ""
        self._end = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(8)

        # Header: back link + title + subtle status + sync link
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
        root.addWidget(self.summary)

        body = QHBoxLayout()
        body.setSpacing(12)

        # Left — events
        left = QVBoxLayout()
        left.setSpacing(6)
        events_label = QLabel("EVENTS")
        events_label.setObjectName("eventsHeading")
        left.addWidget(events_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.events_host = QWidget()
        self.events_host.setObjectName("eventsCanvas")
        self.events_layout = QVBoxLayout(self.events_host)
        self.events_layout.setContentsMargins(0, 0, 2, 0)
        self.events_layout.setSpacing(8)
        self.scroll.setWidget(self.events_host)
        left.addWidget(self.scroll, 1)

        self.empty_card = QFrame()
        self.empty_card.setObjectName("emptyCard")
        empty_layout = QVBoxLayout(self.empty_card)
        empty_layout.setContentsMargins(22, 22, 22, 22)
        empty_layout.setSpacing(8)
        empty_title = QLabel("No events")
        empty_title.setObjectName("cardTitle")
        empty_title.setAlignment(Qt.AlignCenter)
        self.empty_message = QLabel("Everything looks clear.\nSync your calendar to start planning.")
        self.empty_message.setObjectName("pageSubtitle")
        self.empty_message.setAlignment(Qt.AlignCenter)
        self.empty_message.setWordWrap(True)
        empty_sync = QPushButton("Sync calendar")
        empty_sync.setObjectName("compactPrimary")
        empty_sync.clicked.connect(self.sync_requested.emit)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(self.empty_message)
        empty_layout.addWidget(empty_sync, alignment=Qt.AlignCenter)
        left.addWidget(self.empty_card)
        self.empty_card.hide()
        body.addLayout(left, 62)

        # Right — compact workload + dominant Study Plan (no trailing stretch)
        right = QVBoxLayout()
        right.setSpacing(8)
        self.timeline = WorkloadTimeline()
        self.timeline.hide()
        self.timeline.setMaximumHeight(128)
        self.timeline.setMinimumHeight(0)
        right.addWidget(self.timeline, 0)

        self.brief = BriefPanel()
        self.brief.generate_requested.connect(self.generate_brief_requested.emit)
        self.brief.regenerate_requested.connect(self.regenerate_brief_requested.emit)
        self.brief.send_telegram_requested.connect(self.send_telegram_requested.emit)
        right.addWidget(self.brief, 1)
        self.brief.hide()
        body.addLayout(right, 40)

        root.addLayout(body, 1)

        mode, start, end = self.range_selector.current_range()
        self._mode, self._start, self._end = mode, start, end

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

    def populate_events(self, events: list[dict]) -> None:
        self.brief.set_mode(self._mode)
        self.brief.set_events_context(events)
        while self.events_layout.count():
            item = self.events_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not events:
            self.scroll.hide()
            self.timeline.hide()
            self.summary.hide()
            self.brief.hide()
            self.empty_card.show()
            return

        self.empty_card.hide()
        self.scroll.show()
        self.summary.update_from_events(events, mode=self._mode)
        self.brief.show()
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
        # Group into weeks from range start
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

    def set_brief(self, text: str, plan: dict | None = None) -> None:
        if (text or "").strip() or plan:
            self.brief.show()
        self.brief.set_brief(text, plan=plan)

    def set_busy(self, busy: bool) -> None:
        self.btn_back.setEnabled(not busy)
        self.btn_sync.setEnabled(not busy)
        self.range_selector.setEnabled(not busy)
        self.brief.set_busy(busy)

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
