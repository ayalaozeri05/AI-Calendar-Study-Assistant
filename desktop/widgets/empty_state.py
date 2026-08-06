"""Unused legacy empty-state helper (planner uses inline empty card)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class EmptyState(QWidget):
    def __init__(
        self,
        icon: str = "",
        title: str = "Nothing here yet",
        hint: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("mutedLabel")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.hint_label)

    def set_content(self, icon: str, title: str, hint: str = "") -> None:
        _ = icon
        self.title_label.setText(title)
        self.hint_label.setText(hint)
