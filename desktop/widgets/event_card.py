"""Academic journal event card — cleaned description, no decorative dots."""

from __future__ import annotations

import re
import webbrowser
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from styles import category_style
from utils.description_clean import clean_description


def _has_hebrew(text: str) -> bool:
    return any("\u0590" <= ch <= "\u05FF" for ch in text)


def _resolve_description(event: dict) -> str:
    raw = event.get("description")
    if raw is None:
        raw = ""
    cleaned = clean_description(raw)
    if cleaned:
        return cleaned
    # Fallback: strip only Google URLs if cleaner removed everything useful
    fallback = re.sub(r"https?://\S*google\.\S+", "", str(raw), flags=re.I)
    fallback = re.sub(r"שינויים בשם.*?(\n|$)", "", fallback, flags=re.S)
    fallback = re.sub(r"כדי לערוך.*?(\n|$)", "", fallback, flags=re.S)
    fallback = re.sub(r"\n{3,}", "\n\n", fallback).strip()
    return fallback


class EventCard(QFrame):
    PREVIEW_LINES = 3

    def __init__(self, event: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("eventCard")
        self._expanded = False
        self._full_description = _resolve_description(event)
        self._html_link = (event.get("html_link") or "").strip()

        style = category_style(str(event.get("category", "Other")))
        self.setStyleSheet(
            "QFrame#eventCard {"
            f" border-left: 4px solid {style['accent']};"
            " background-color: #FFFDF8;"
            " border-top: 1px solid #E5DED3;"
            " border-right: 1px solid #E5DED3;"
            " border-bottom: 1px solid #E5DED3;"
            " border-radius: 8px;"
            "}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(5)

        top = QHBoxLayout()
        chip = QLabel(str(event.get("category", "Other")))
        chip.setObjectName("categoryChip")
        chip.setStyleSheet(
            f"background-color: {style['bg']}; color: {style['fg']};"
            "border-radius: 5px; padding: 2px 8px; font-size: 11px; font-weight: 700;"
        )
        top.addWidget(chip)
        top.addStretch()
        time_label = QLabel(self._fmt_range(event.get("start"), event.get("end")))
        time_label.setObjectName("mutedLabel")
        top.addWidget(time_label)
        root.addLayout(top)

        title_text = str(event.get("title", "Untitled"))
        title = QLabel(title_text)
        title.setObjectName("cardTitle")
        title.setWordWrap(True)
        if _has_hebrew(title_text):
            title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            title.setLayoutDirection(Qt.RightToLeft)
        root.addWidget(title)

        date_label = QLabel(self._fmt_date(event.get("start")))
        date_label.setObjectName("mutedLabel")
        root.addWidget(date_label)

        location = (event.get("location") or "").strip()
        if location:
            loc_label = QLabel(location)
            loc_label.setObjectName("mutedLabel")
            root.addWidget(loc_label)

        if self._full_description:
            root.addSpacing(10)
            self.desc_label = QLabel()
            self.desc_label.setWordWrap(True)
            self.desc_label.setObjectName("eventDescription")
            self.desc_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if _has_hebrew(self._full_description):
                self.desc_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
                self.desc_label.setLayoutDirection(Qt.RightToLeft)
            root.addWidget(self.desc_label)

            self.read_more = QPushButton("Show more")
            self.read_more.setObjectName("linkButton")
            self.read_more.setCursor(Qt.PointingHandCursor)
            self.read_more.clicked.connect(self._toggle_description)
            root.addWidget(self.read_more, alignment=Qt.AlignLeft)
            self._apply_description()

        if self._html_link:
            open_btn = QPushButton("Open source")
            open_btn.setObjectName("linkButton")
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.clicked.connect(lambda: webbrowser.open(self._html_link))
            root.addWidget(open_btn, alignment=Qt.AlignLeft)

    def _toggle_description(self) -> None:
        self._expanded = not self._expanded
        self._apply_description()

    def _apply_description(self) -> None:
        text = self._full_description
        lines = text.splitlines() or [text]
        short = len(lines) <= self.PREVIEW_LINES and len(text) <= 240
        if short:
            self.desc_label.setText(text)
            self.read_more.hide()
            return
        if self._expanded:
            self.desc_label.setText(text)
            self.read_more.setText("Show less")
        else:
            preview = "\n".join(lines[: self.PREVIEW_LINES]).rstrip()
            if len(lines) > self.PREVIEW_LINES or len(text) > 240:
                preview += "…"
            self.desc_label.setText(preview)
            self.read_more.setText("Show more")
        self.read_more.show()

    @staticmethod
    def _fmt_date(value: str | None) -> str:
        if not value:
            return ""
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return dt.strftime("%A, %b %d")
        except Exception:
            return str(value)

    @staticmethod
    def _fmt_range(start: str | None, end: str | None) -> str:
        def one(value: str | None) -> str:
            if not value:
                return ""
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime(
                    "%H:%M"
                )
            except Exception:
                return ""

        a, b = one(start), one(end)
        if a and b:
            return f"{a} – {b}"
        return a or b or ""
