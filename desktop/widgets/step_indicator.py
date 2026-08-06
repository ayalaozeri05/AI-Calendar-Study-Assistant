"""Clickable wizard progress: Connect → Sync → Plan."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class StepIndicator(QWidget):
    LABELS = ("Connect", "Sync", "Plan")
    step_clicked = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._buttons: list[QPushButton] = []
        for i, label in enumerate(self.LABELS):
            btn = QPushButton(f"{i + 1}. {label}")
            btn.setObjectName("stepButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked=False, index=i: self.step_clicked.emit(index))
            self._buttons.append(btn)
            layout.addWidget(btn)
            if i < len(self.LABELS) - 1:
                arrow = QPushButton("→")
                arrow.setObjectName("stepArrow")
                arrow.setEnabled(False)
                arrow.setFlat(True)
                layout.addWidget(arrow)
        self.set_step(0)

    def set_step(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            label = self.LABELS[i]
            if i < index:
                btn.setText(f"✓ {i + 1}. {label}")
                btn.setProperty("done", "true")
                btn.setProperty("active", "false")
            elif i == index:
                btn.setText(f"● {i + 1}. {label}")
                btn.setProperty("done", "false")
                btn.setProperty("active", "true")
            else:
                btn.setText(f"{i + 1}. {label}")
                btn.setProperty("done", "false")
                btn.setProperty("active", "false")
            btn.setChecked(i == index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
