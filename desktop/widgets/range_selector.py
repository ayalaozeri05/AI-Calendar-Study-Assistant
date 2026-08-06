"""Compact range selector: Today / 7 / 14 / Month / Custom."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RangeSelector(QWidget):
    """Emits (mode, start_iso, end_iso) when the active range changes."""

    range_changed = Signal(str, str, str)

    MODES = ("today", "7days", "14days", "month", "custom")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mode = "today"
        self._custom_start = date.today()
        self._custom_end = date.today() + timedelta(days=6)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        bar = QFrame()
        bar.setObjectName("segmentBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(2)

        labels = {
            "today": "Today",
            "7days": "7 Days",
            "14days": "14 Days",
            "month": "This Month",
            "custom": "Custom",
        }
        self._buttons: dict[str, QPushButton] = {}
        for key in self.MODES:
            btn = QPushButton(labels[key])
            btn.setObjectName("segmentButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, m=key: self.set_mode(m))
            self._buttons[key] = btn
            row.addWidget(btn)
        root.addWidget(bar)

        self.custom_row = QWidget()
        custom_layout = QHBoxLayout(self.custom_row)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(8)
        custom_layout.addWidget(QLabel("From"))
        self.start_edit = QDateEdit()
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_edit.setDate(QDate(self._custom_start.year, self._custom_start.month, self._custom_start.day))
        custom_layout.addWidget(self.start_edit)
        custom_layout.addWidget(QLabel("To"))
        self.end_edit = QDateEdit()
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_edit.setDate(QDate(self._custom_end.year, self._custom_end.month, self._custom_end.day))
        custom_layout.addWidget(self.end_edit)
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setObjectName("secondaryButton")
        self.btn_apply.clicked.connect(self._apply_custom)
        custom_layout.addWidget(self.btn_apply)
        custom_layout.addStretch()
        self.custom_row.hide()
        root.addWidget(self.custom_row)

        self._buttons["today"].setChecked(True)

    @property
    def mode(self) -> str:
        return self._mode

    def current_range(self) -> tuple[str, str, str]:
        start, end = self._dates_for_mode(self._mode)
        return self._mode, start.isoformat(), end.isoformat()

    def set_mode(self, mode: str, *, emit: bool = True) -> None:
        if mode not in self.MODES:
            return
        self._mode = mode
        for key, btn in self._buttons.items():
            btn.setChecked(key == mode)
        self.custom_row.setVisible(mode == "custom")
        if mode == "custom":
            if emit:
                # Wait for Apply
                return
        if emit:
            _, start, end = self.current_range()
            self.range_changed.emit(mode, start, end)

    def _apply_custom(self) -> None:
        start = self._qdate_to_date(self.start_edit.date())
        end = self._qdate_to_date(self.end_edit.date())
        if start > end:
            start, end = end, start
            self.start_edit.setDate(QDate(start.year, start.month, start.day))
            self.end_edit.setDate(QDate(end.year, end.month, end.day))
        self._custom_start = start
        self._custom_end = end
        self._mode = "custom"
        self.range_changed.emit("custom", start.isoformat(), end.isoformat())

    @staticmethod
    def _qdate_to_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    def _dates_for_mode(self, mode: str) -> tuple[date, date]:
        today = date.today()
        if mode == "today":
            return today, today
        if mode == "7days":
            return today, today + timedelta(days=6)
        if mode == "14days":
            return today, today + timedelta(days=13)
        if mode == "month":
            if today.month == 12:
                last = date(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                last = date(today.year, today.month + 1, 1) - timedelta(days=1)
            return today, last
        return self._custom_start, self._custom_end
