"""Calendar Study Assistant dashboard view (PySide6 MVP View)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from widgets.category_chart import CategoryChartWidget

STYLESHEET = """
QMainWindow { background-color: #f4f7fb; }
QWidget {
    color: #1e293b;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}
QLabel#title {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
}
QLabel#subtitle {
    color: #64748b;
    font-size: 13px;
}
QPushButton {
    background-color: #2563eb;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 9px 14px;
    font-weight: 600;
}
QPushButton:hover { background-color: #1d4ed8; }
QPushButton:disabled { background-color: #94a3b8; }
QPushButton#secondary {
    background-color: #0f766e;
}
QPushButton#secondary:hover { background-color: #0d9488; }
QPushButton#danger {
    background-color: #7c3aed;
}
QPushButton#danger:hover { background-color: #6d28d9; }
QFrame#panel {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
}
QTableWidget {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    gridline-color: #f1f5f9;
}
QHeaderView::section {
    background: #f8fafc;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #e2e8f0;
    font-weight: 600;
}
QPlainTextEdit {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px;
    background: #fafafa;
}
"""


class DashboardView(QMainWindow):
    load_demo_requested = Signal()
    sync_calendar_requested = Signal()
    show_today_requested = Signal()
    generate_brief_requested = Signal()
    send_telegram_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Calendar Study Assistant")
        self.resize(1100, 720)
        self.setStyleSheet(STYLESHEET)
        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = QVBoxLayout()
        self.title_label = QLabel("AI Calendar Study Assistant")
        self.title_label.setObjectName("title")
        self.subtitle_label = QLabel("Load a demo student, sync calendar, generate brief, send to Telegram.")
        self.subtitle_label.setObjectName("subtitle")
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        root.addLayout(header)

        actions = QHBoxLayout()
        self.btn_demo = QPushButton("Load Demo Student")
        self.btn_demo.setObjectName("danger")
        self.btn_sync = QPushButton("Sync Google Calendar")
        self.btn_today = QPushButton("Show Today Events")
        self.btn_today.setObjectName("secondary")
        self.btn_brief = QPushButton("Generate Today Brief")
        self.btn_telegram = QPushButton("Send Brief to Telegram")

        self.btn_demo.clicked.connect(self.load_demo_requested.emit)
        self.btn_sync.clicked.connect(self.sync_calendar_requested.emit)
        self.btn_today.clicked.connect(self.show_today_requested.emit)
        self.btn_brief.clicked.connect(self.generate_brief_requested.emit)
        self.btn_telegram.clicked.connect(self.send_telegram_requested.emit)

        for btn in (
            self.btn_demo,
            self.btn_sync,
            self.btn_today,
            self.btn_brief,
            self.btn_telegram,
        ):
            actions.addWidget(btn)
        actions.addStretch()
        root.addLayout(actions)

        self.status_label = QLabel("Ready. Start by loading the demo student.")
        self.status_label.setStyleSheet(
            "padding: 10px; border-radius: 6px; background: #f1f5f9; color: #475569;"
        )
        root.addWidget(self.status_label)

        body = QHBoxLayout()
        body.setSpacing(12)

        left = QFrame()
        left.setObjectName("panel")
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Today / synced events"))
        self.events_table = QTableWidget(0, 4)
        self.events_table.setHorizontalHeaderLabels(
            ["Time", "Category", "Title", "End"]
        )
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.events_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.events_table.setEditTriggers(QTableWidget.NoEditTriggers)
        left_layout.addWidget(self.events_table)
        body.addWidget(left, 3)

        right = QVBoxLayout()
        chart_panel = QFrame()
        chart_panel.setObjectName("panel")
        chart_layout = QVBoxLayout(chart_panel)
        self.category_chart = CategoryChartWidget()
        self.category_chart.setMinimumHeight(220)
        chart_layout.addWidget(self.category_chart)
        right.addWidget(chart_panel, 1)

        brief_panel = QFrame()
        brief_panel.setObjectName("panel")
        brief_layout = QVBoxLayout(brief_panel)
        brief_layout.addWidget(QLabel("Study brief"))
        self.brief_text = QPlainTextEdit()
        self.brief_text.setReadOnly(True)
        self.brief_text.setPlaceholderText("Generate a brief to see it here.")
        brief_layout.addWidget(self.brief_text)
        right.addWidget(brief_panel, 2)

        body.addLayout(right, 2)
        root.addLayout(body, 1)

    def set_student_header(self, name: str, email: str) -> None:
        self.title_label.setText(f"AI Calendar Study Assistant — {name}")
        self.subtitle_label.setText(f"Student: {email}")

    def show_status(self, message: str, is_error: bool = False) -> None:
        if is_error:
            self.status_label.setText(f"Error: {message}")
            self.status_label.setStyleSheet(
                "padding: 10px; border-radius: 6px; background: #fef2f2; "
                "color: #991b1b; font-weight: 600; border: 1px solid #fecaca;"
            )
        else:
            self.status_label.setText(message)
            self.status_label.setStyleSheet(
                "padding: 10px; border-radius: 6px; background: #ecfdf5; "
                "color: #166534; font-weight: 600; border: 1px solid #bbf7d0;"
            )

    def set_busy(self, busy: bool) -> None:
        for btn in (
            self.btn_demo,
            self.btn_sync,
            self.btn_today,
            self.btn_brief,
            self.btn_telegram,
        ):
            btn.setEnabled(not busy)

    def populate_events(self, events: list[dict]) -> None:
        self.events_table.setRowCount(0)
        for event in events:
            row = self.events_table.rowCount()
            self.events_table.insertRow(row)
            self.events_table.setItem(row, 0, QTableWidgetItem(self._fmt_time(event.get("start"))))
            self.events_table.setItem(row, 1, QTableWidgetItem(str(event.get("category", ""))))
            self.events_table.setItem(row, 2, QTableWidgetItem(str(event.get("title", ""))))
            self.events_table.setItem(row, 3, QTableWidgetItem(self._fmt_time(event.get("end"))))
        self.category_chart.update_from_events(events)

    def set_brief_text(self, text: str) -> None:
        self.brief_text.setPlainText(text)

    @staticmethod
    def _fmt_time(value: str | None) -> str:
        if not value:
            return "-"
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(value)
