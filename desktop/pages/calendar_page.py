"""Calendar page — connect + sync with one obvious primary action."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CalendarPage(QWidget):
    connect_requested = Signal()
    sync_requested = Signal()
    back_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._connected = False
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(12)

        top = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.setObjectName("ghostButton")
        self.btn_back.clicked.connect(self.back_requested.emit)
        top.addWidget(self.btn_back)
        top.addStretch()
        self.profile_badge = QLabel("")
        self.profile_badge.setObjectName("headerStatus")
        self.profile_badge.hide()
        top.addWidget(self.profile_badge)
        root.addLayout(top)

        root.addStretch()

        card = QFrame()
        card.setObjectName("paperCard")
        card.setMaximumWidth(480)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(12)

        title = QLabel("Calendar")
        title.setObjectName("pageTitle")
        title.setStyleSheet("font-size: 26px;")
        card_layout.addWidget(title)

        subtitle = QLabel(
            "Connect Google Calendar once, then sync your upcoming study events."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        card_layout.addWidget(subtitle)

        marker = QFrame()
        marker.setObjectName("markerLine")
        marker.setFixedWidth(72)
        card_layout.addWidget(marker)

        self.status_badge = QLabel("Not connected")
        self.status_badge.setObjectName("warningBadge")
        card_layout.addWidget(self.status_badge, alignment=Qt.AlignLeft)

        self.helper = QLabel("Connect your calendar to continue.")
        self.helper.setObjectName("mutedLabel")
        self.helper.setWordWrap(True)
        card_layout.addWidget(self.helper)

        self.btn_connect = QPushButton("Connect Google Calendar")
        self.btn_connect.clicked.connect(self.connect_requested.emit)
        card_layout.addWidget(self.btn_connect, alignment=Qt.AlignLeft)

        self.btn_sync = QPushButton("Sync Calendar")
        self.btn_sync.setObjectName("primaryWide")
        self.btn_sync.clicked.connect(self.sync_requested.emit)
        card_layout.addWidget(self.btn_sync, alignment=Qt.AlignLeft)

        self.sync_result = QLabel("")
        self.sync_result.setObjectName("mutedLabel")
        self.sync_result.hide()
        card_layout.addWidget(self.sync_result)

        wrap = QHBoxLayout()
        wrap.addStretch()
        wrap.addWidget(card)
        wrap.addStretch()
        root.addLayout(wrap)
        root.addStretch()

        self.set_connected(False)

    def set_profile_ready(self, ready: bool = True) -> None:
        # Keep calendar header quiet — identity lives on the planner status line
        self.profile_badge.hide()
        _ = ready

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        if connected:
            self.status_badge.setText("Google Calendar connected")
            self.status_badge.setObjectName("connectedBadge")
            self.btn_connect.hide()
            self.helper.setText("Ready to sync. This imports the next 7 days of events.")
            self.btn_sync.show()
        else:
            self.status_badge.setText("Not connected")
            self.status_badge.setObjectName("warningBadge")
            self.btn_connect.show()
            self.helper.setText("Connect your calendar to continue.")
            self.btn_sync.hide()
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

    def set_credentials_missing(self) -> None:
        self._connected = False
        self.status_badge.setText("Setup needed")
        self.status_badge.setObjectName("warningBadge")
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
        self.btn_connect.hide()
        self.btn_sync.hide()
        self.helper.setText(
            "Google credentials are missing on this computer. Ask your instructor for help."
        )

    def set_syncing(self, syncing: bool) -> None:
        self._syncing = syncing
        if syncing:
            self.btn_sync.setText("Syncing…")
            self.btn_sync.setEnabled(False)
        else:
            self.btn_sync.setText("Sync Calendar")
            self.btn_sync.setEnabled(self._connected)

    def show_sync_count(self, count: int) -> None:
        self.sync_result.setText(f"{count} events synced")
        self.sync_result.show()

    def set_busy(self, busy: bool) -> None:
        self.btn_back.setEnabled(not busy)
        self.btn_connect.setEnabled(not busy)
        if not self._syncing:
            self.btn_sync.setEnabled((not busy) and self._connected)
