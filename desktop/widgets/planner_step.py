"""Persistent planner: events, stats, chart, brief, Telegram."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from styles import category_style
from widgets.brief_panel import BriefPanel
from widgets.category_chart import CategoryChartWidget
from widgets.empty_state import EmptyState
from widgets.event_card import EventCard
from widgets.segment_control import SegmentControl


class PlannerStep(QWidget):
    range_changed = Signal(str)
    generate_today_requested = Signal()
    generate_weekly_requested = Signal()
    send_telegram_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        self.page_title = QLabel("Your study planner")
        self.page_title.setObjectName("pageTitle")
        self.page_title.setStyleSheet("font-size: 22px;")
        self.page_subtitle = QLabel(
            "Always available — switch Today / Week, generate briefs, send to Telegram."
        )
        self.page_subtitle.setObjectName("pageSubtitle")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        header.addLayout(titles, 1)

        self.segment = SegmentControl()
        self.segment.changed.connect(self.range_changed.emit)
        header.addWidget(self.segment, 0, Qt.AlignTop)
        root.addLayout(header)

        self.stats_row = QHBoxLayout()
        self.stats_row.setSpacing(10)
        root.addLayout(self.stats_row)

        body = QHBoxLayout()
        body.setSpacing(12)

        events_panel = QFrame()
        events_panel.setObjectName("paperCard")
        shadow = QGraphicsDropShadowEffect(events_panel)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(124, 131, 253, 22))
        events_panel.setGraphicsEffect(shadow)

        events_layout = QVBoxLayout(events_panel)
        events_layout.setContentsMargins(12, 12, 12, 12)
        events_header = QHBoxLayout()
        events_header.addWidget(QLabel("Events"))
        events_header.addStretch()
        doodle = QLabel("— · — · —")
        doodle.setObjectName("doodleLine")
        events_header.addWidget(doodle)
        events_layout.addLayout(events_header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.events_host = QWidget()
        self.events_layout = QVBoxLayout(self.events_host)
        self.events_layout.setContentsMargins(4, 4, 4, 4)
        self.events_layout.setSpacing(10)
        self.events_layout.addStretch()
        self.scroll.setWidget(self.events_host)
        events_layout.addWidget(self.scroll, 1)

        self.empty = EmptyState(
            "📚",
            "No study events yet.",
            "Use Sync in the guide, then your events will appear here.",
        )
        events_layout.addWidget(self.empty)

        body.addWidget(events_panel, 3)

        right = QVBoxLayout()
        right.setSpacing(10)

        chart_panel = QFrame()
        chart_panel.setObjectName("paperCard")
        chart_shadow = QGraphicsDropShadowEffect(chart_panel)
        chart_shadow.setBlurRadius(16)
        chart_shadow.setOffset(0, 3)
        chart_shadow.setColor(QColor(124, 131, 253, 20))
        chart_panel.setGraphicsEffect(chart_shadow)
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(10, 10, 10, 10)
        self.chart = CategoryChartWidget()
        self.chart.setMinimumHeight(170)
        chart_layout.addWidget(self.chart)
        right.addWidget(chart_panel, 1)

        self.brief = BriefPanel()
        self.brief.generate_today_requested.connect(self.generate_today_requested.emit)
        self.brief.generate_weekly_requested.connect(self.generate_weekly_requested.emit)
        self.brief.send_telegram_requested.connect(self.send_telegram_requested.emit)
        right.addWidget(self.brief, 2)

        body.addLayout(right, 2)
        root.addLayout(body, 1)

    def set_range_label(self, mode: str) -> None:
        if mode == "today":
            self.page_title.setText("Today’s plan")
            self.page_subtitle.setText(
                "Events, chart, and brief stay here — switch to Week anytime."
            )
        else:
            self.page_title.setText("Your study week")
            self.page_subtitle.setText(
                "Events, chart, and brief stay here — switch to Today anytime."
            )

    def populate_events(self, events: list[dict], mode: str) -> None:
        self.set_range_label(mode)
        while self.events_layout.count():
            item = self.events_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not events:
            self.scroll.hide()
            self.empty.show()
            if mode == "today":
                self.empty.set_content(
                    "🌤️",
                    "No events scheduled for today.",
                    "Try Week, or press Sync / Refresh Events.",
                )
            else:
                self.empty.set_content(
                    "📭",
                    "Your calendar is empty this week.",
                    "Press Sync to import Google Calendar events.",
                )
            self.chart.update_from_events([])
            self._render_stats({})
            return

        self.empty.hide()
        self.scroll.show()
        for index, event in enumerate(events):
            card = EventCard(event)
            self.events_layout.addWidget(card)
            card.animate_in(delay_ms=index * 35)
        self.events_layout.addStretch()
        self.chart.update_from_events(events)
        self._render_stats(Counter(e.get("category", "Other") for e in events))

    def set_brief(self, text: str, brief_type: str) -> None:
        self.brief.set_brief(text, brief_type)

    def set_busy(self, busy: bool) -> None:
        self.segment.setEnabled(not busy)
        self.brief.set_busy(busy)

    def _render_stats(self, counts: Counter) -> None:
        while self.stats_row.count():
            item = self.stats_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        order = ["Exam", "Assignment", "Project", "Study", "Class", "Meeting", "Other"]
        shown = 0
        for category in order:
            value = counts.get(category, 0)
            if value <= 0:
                continue
            style = category_style(category)
            card = QFrame()
            card.setObjectName("statCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(2)
            label = QLabel(f"{style['icon']} {category}")
            label.setStyleSheet(
                f"color: {style['fg']}; font-weight: 700; font-size: 12px;"
            )
            value_label = QLabel(str(value))
            value_label.setStyleSheet("font-size: 18px; font-weight: 700;")
            layout.addWidget(label)
            layout.addWidget(value_label)
            self.stats_row.addWidget(card)
            shown += 1
            if shown >= 5:
                break
        if shown == 0:
            placeholder = QLabel("Stats appear after Sync.")
            placeholder.setObjectName("helperText")
            self.stats_row.addWidget(placeholder)
        self.stats_row.addStretch()
