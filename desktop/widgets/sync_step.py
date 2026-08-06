"""Sync guide panel — informational; primary action lives in the shell."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class SyncStep(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._synced = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

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

        icon = QLabel("🔄")
        icon.setStyleSheet("font-size: 28px;")
        layout.addWidget(icon)

        title = QLabel("Sync Calendar")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        self.helper = QLabel(
            "Press Sync to import the next 7 days. "
            "When it finishes, the planner opens automatically."
        )
        self.helper.setObjectName("helperText")
        self.helper.setWordWrap(True)
        layout.addWidget(self.helper)

        self.success = QLabel("")
        self.success.setObjectName("badgeConnected")
        self.success.setAlignment(Qt.AlignCenter)
        self.success.setVisible(False)
        self._success_opacity = QGraphicsOpacityEffect(self.success)
        self.success.setGraphicsEffect(self._success_opacity)
        layout.addWidget(self.success)
        layout.addStretch()

        root.addWidget(card)

        self._fade = QPropertyAnimation(self._success_opacity, b"opacity", self)
        self._fade.setDuration(400)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)

    @property
    def synced(self) -> bool:
        return self._synced

    def reset_success(self) -> None:
        self.success.setVisible(False)

    def show_sync_success(self, count: int) -> None:
        self._synced = True
        if count:
            self.success.setText(f"Synced {count} events ✓")
            self.helper.setText("Opening your planner…")
        else:
            self.success.setText("Sync complete ✓")
            self.helper.setText(
                "No events in the next 7 days — opening the planner anyway…"
            )
        self.success.setVisible(True)
        self._success_opacity.setOpacity(0.0)
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
