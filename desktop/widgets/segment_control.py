"""Today / This Week segmented control."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton


class SegmentControl(QFrame):
    changed = Signal(str)  # "today" | "week"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("segmentBar")
        self._value = "today"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.btn_today = QPushButton("Today")
        self.btn_today.setObjectName("segmentButton")
        self.btn_today.setCheckable(True)
        self.btn_today.setChecked(True)

        self.btn_week = QPushButton("This Week")
        self.btn_week.setObjectName("segmentButton")
        self.btn_week.setCheckable(True)

        self.btn_today.clicked.connect(lambda: self.set_value("today"))
        self.btn_week.clicked.connect(lambda: self.set_value("week"))

        layout.addWidget(self.btn_today)
        layout.addWidget(self.btn_week)

    def value(self) -> str:
        return self._value

    def set_value(self, value: str, *, emit: bool = True) -> None:
        if value not in ("today", "week"):
            return
        self._value = value
        self.btn_today.setChecked(value == "today")
        self.btn_week.setChecked(value == "week")
        if emit:
            self.changed.emit(value)
