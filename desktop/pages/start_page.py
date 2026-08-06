"""Start page — single clear entry action."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget


class StartPage(QWidget):
    start_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 48, 48, 48)
        root.setSpacing(14)
        root.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setObjectName("paperCard")
        card.setMaximumWidth(520)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignCenter)

        brand = QLabel("AI Calendar Study Assistant")
        brand.setObjectName("mutedLabel")
        brand.setAlignment(Qt.AlignCenter)
        brand.setStyleSheet("color: #8985F7; font-weight: 700; letter-spacing: 0.4px;")
        layout.addWidget(brand)

        title = QLabel("Plan your study week")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)

        marker = QFrame()
        marker.setObjectName("markerLine")
        marker.setFixedWidth(96)
        layout.addWidget(marker, alignment=Qt.AlignCenter)

        subtitle = QLabel(
            "Connect your calendar, organize your events, and create a clear study brief."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self._ready = False
        self.btn_start = QPushButton("Start Planner")
        self.btn_start.setObjectName("primaryWide")
        self.btn_start.clicked.connect(self.start_requested.emit)
        layout.addWidget(self.btn_start, alignment=Qt.AlignCenter)

        root.addWidget(card)

    def set_profile_ready(self, ready: bool) -> None:
        self._ready = ready
        if ready:
            self.btn_start.setText("Continue to Calendar")
        else:
            self.btn_start.setText("Start Planner")

    def set_busy(self, busy: bool) -> None:
        self.btn_start.setEnabled(not busy)
        if busy:
            self.btn_start.setText("Starting…")
        elif self._ready:
            self.btn_start.setText("Continue to Calendar")
        else:
            self.btn_start.setText("Start Planner")
