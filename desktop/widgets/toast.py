"""Compact toast notification (not a full-width banner)."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class ToastBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        self.label = QLabel("")
        self.label.setObjectName("toast")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.hide()
        layout.addWidget(self.label)
        layout.addStretch()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.label.hide)

    def show_message(self, message: str, kind: str = "success", ms: int = 3200) -> None:
        text = (message or "").strip()
        if not text:
            self.label.hide()
            return
        self.label.setText(text)
        self.label.setProperty("kind", kind)
        self.label.style().unpolish(self.label)
        self.label.style().polish(self.label)
        self.label.show()
        self._timer.start(ms)

    def clear(self) -> None:
        self._timer.stop()
        self.label.hide()
