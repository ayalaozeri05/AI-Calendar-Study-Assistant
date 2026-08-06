"""Connect guide panel — informational; primary action lives in the shell."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class ConnectStep(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        card = QFrame()
        card.setObjectName("paperCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(124, 131, 253, 28))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        icon = QLabel("📅")
        icon.setStyleSheet("font-size: 28px;")
        layout.addWidget(icon)

        title = QLabel("Connect Google Calendar")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        self.helper = QLabel(
            "First load a demo student, then connect your calendar. "
            "Use the big button on the right when you are ready."
        )
        self.helper.setObjectName("helperText")
        self.helper.setWordWrap(True)
        layout.addWidget(self.helper)

        badge_row = QHBoxLayout()
        self.badge = QLabel("Not connected")
        self.badge.setObjectName("badgeWarning")
        self.badge.setAlignment(Qt.AlignCenter)
        badge_row.addWidget(self.badge)
        badge_row.addStretch()
        layout.addLayout(badge_row)

        sticky = QFrame()
        sticky.setObjectName("stickyNote")
        sticky_layout = QVBoxLayout(sticky)
        sticky_layout.setContentsMargins(10, 8, 10, 8)
        tip = QLabel("After the first connection, Sync works immediately next time.")
        tip.setWordWrap(True)
        tip.setObjectName("helperText")
        tip.setStyleSheet("color: #8A6D1B;")
        sticky_layout.addWidget(tip)
        layout.addWidget(sticky)
        layout.addStretch()

        root.addWidget(card)

        self._student_loaded = False
        self._connected = False

    @property
    def student_loaded(self) -> bool:
        return self._student_loaded

    @property
    def connected(self) -> bool:
        return self._connected

    def set_student_loaded(self, name: str, email: str) -> None:
        self._student_loaded = True
        self.helper.setText(f"Signed in as {name} · {email}")

    def set_status_label(self, status: str) -> None:
        if status == "Connected":
            self._connected = True
            self.badge.setText("Connected ✓")
            self.badge.setObjectName("badgeConnected")
            self.helper.setText(
                (self.helper.text().split("·")[0] + "· calendar ready.")
                if self._student_loaded
                else "Google Calendar is connected. Continue to Sync."
            )
        elif status == "Credentials missing":
            self._connected = False
            self.badge.setText("Setup needed")
            self.badge.setObjectName("badgeWarning")
            self.helper.setText(
                "Google credentials file is missing. Check GOOGLE_CALENDAR_CREDENTIALS_PATH."
            )
        else:
            self._connected = False
            self.badge.setText("Not connected")
            self.badge.setObjectName("badgeWarning")
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)
