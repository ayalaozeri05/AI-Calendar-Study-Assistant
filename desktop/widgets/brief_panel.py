"""Single Create Study Plan flow with timeline-style study schedule."""

from __future__ import annotations

import traceback
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from styles import category_style


class BriefPanel(QFrame):
    generate_requested = Signal()
    regenerate_requested = Signal()
    send_telegram_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("briefCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._mode = "today"
        self._has_brief = False
        self._events: list[dict] = []
        self._plan: dict | None = None
        self._brief_text = ""
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        self.title = QLabel("Study Plan")
        self.title.setObjectName("cardTitle")
        root.addWidget(self.title)

        self.rag_note = QLabel("Enhanced using uploaded study material")
        self.rag_note.setObjectName("mutedLabel")
        self.rag_note.setWordWrap(True)
        self.rag_note.hide()
        root.addWidget(self.rag_note)

        self.marker = QFrame()
        self.marker.setObjectName("markerLine")
        self.marker.setFixedWidth(72)
        root.addWidget(self.marker)

        self.helper = QLabel(
            "Create a personalized study plan based on your calendar."
        )
        self.helper.setObjectName("mutedLabel")
        self.helper.setWordWrap(True)
        root.addWidget(self.helper)

        self.loading_label = QLabel("Creating your AI study plan...")
        self.loading_label.setObjectName("mutedLabel")
        self.loading_label.hide()
        root.addWidget(self.loading_label)

        self.ai_source_label = QLabel("")
        self.ai_source_label.setObjectName("mutedLabel")
        self.ai_source_label.hide()
        root.addWidget(self.ai_source_label)

        self.anchor_label = QLabel("")
        self.anchor_label.setObjectName("mutedLabel")
        self.anchor_label.hide()
        root.addWidget(self.anchor_label)

        self.btn_generate = QPushButton("Create Study Plan")
        self.btn_generate.setObjectName("compactPrimary")
        self.btn_generate.clicked.connect(self._on_generate)
        root.addWidget(self.btn_generate, 0, Qt.AlignLeft)

        self.notebook = QFrame()
        self.notebook.setObjectName("notebookPage")
        self.notebook.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        note_outer = QVBoxLayout(self.notebook)
        note_outer.setContentsMargins(0, 0, 0, 0)
        self.note_scroll = QScrollArea()
        self.note_scroll.setWidgetResizable(True)
        self.note_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.note_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.note_scroll.setFrameShape(QFrame.NoFrame)
        self.note_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.note_host = QWidget()
        self.note_host.setObjectName("notebookInner")
        self.note_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.note_layout = QVBoxLayout(self.note_host)
        self.note_layout.setContentsMargins(12, 10, 12, 14)
        self.note_layout.setSpacing(10)
        self.note_scroll.setWidget(self.note_host)
        note_outer.addWidget(self.note_scroll)
        root.addWidget(self.notebook, 1)
        self.notebook.hide()

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_regenerate = QPushButton("Regenerate Plan")
        self.btn_regenerate.setObjectName("secondaryButton")
        self.btn_regenerate.hide()
        self.btn_regenerate.clicked.connect(self._on_regenerate)
        self.btn_telegram = QPushButton("Send to Telegram")
        self.btn_telegram.setObjectName("telegramButton")
        self.btn_telegram.hide()
        self.btn_telegram.clicked.connect(self.send_telegram_requested.emit)
        actions.addWidget(self.btn_regenerate)
        actions.addWidget(self.btn_telegram)
        actions.addStretch()
        root.addLayout(actions)

    def _on_generate(self) -> None:
        if self._loading:
            return
        self.generate_requested.emit()

    def _on_regenerate(self) -> None:
        if self._loading:
            return
        self.regenerate_requested.emit()

    def set_mode(self, mode: str) -> None:
        self._mode = mode or "today"
        if not self._has_brief:
            self.helper.setText(
                "Create a personalized study plan based on your calendar."
            )
            self.btn_generate.setText("Create Study Plan")

    def set_events_context(self, events: list[dict]) -> None:
        self._events = events

    def brief_text(self) -> str:
        return self._brief_text

    def current_plan(self) -> dict | None:
        return self._plan

    def clear(self) -> None:
        self._has_brief = False
        self._plan = None
        self._brief_text = ""
        self._clear_note()
        self.notebook.hide()
        self.btn_telegram.hide()
        self.btn_regenerate.hide()
        self.btn_generate.show()
        self.helper.show()
        self.marker.show()
        self.loading_label.hide()
        self.ai_source_label.hide()
        self.ai_source_label.setText("")
        self.rag_note.hide()
        self.anchor_label.hide()
        self.anchor_label.setText("")
        self.title.setText("Study Plan")
        self.helper.setText(
            "Create a personalized study plan based on your calendar."
        )
        self.btn_generate.setText("Create Study Plan")
        # Compact empty state, but allow growth when a plan is shown
        self.setMinimumHeight(0)
        self.setMaximumHeight(220)

    def set_loading(self, loading: bool, *, regenerating: bool = False) -> None:
        self._loading = loading
        if loading:
            self.loading_label.setText(
                "Creating a new plan..."
                if regenerating
                else "Creating your AI study plan..."
            )
            self.loading_label.show()
        else:
            self.loading_label.hide()
        self.btn_generate.setEnabled(not loading)
        self.btn_regenerate.setEnabled(not loading and self._has_brief)
        self.btn_telegram.setEnabled(not loading and self._has_brief)

    def set_ai_source(self, ai_mode: str) -> None:
        """Show source only when Ollama polish actually ran. Hide otherwise."""
        mode = (ai_mode or "").strip().lower()
        if mode == "ollama":
            self.ai_source_label.setText("AI source: Ollama")
            self.ai_source_label.show()
        else:
            # deterministic / rule_based_fallback / empty — no technical label in UI
            self.ai_source_label.hide()
            self.ai_source_label.setText("")

    def set_telegram_sending(self, sending: bool) -> None:
        if sending:
            self.loading_label.setText("Sending study plan...")
            self.loading_label.show()
            self.btn_telegram.setEnabled(False)
            self.btn_regenerate.setEnabled(False)
        else:
            if not self._loading:
                self.loading_label.hide()
            self.btn_telegram.setEnabled(self._has_brief and not self._loading)
            self.btn_regenerate.setEnabled(self._has_brief and not self._loading)

    def set_brief(
        self,
        text: str,
        plan: dict | None = None,
        *,
        ai_mode: str | None = None,
        rag_enhanced: bool = False,
        rag_message: str | None = None,
    ) -> None:
        self._brief_text = (text or "").strip()
        self._plan = plan if isinstance(plan, dict) else None
        if not self._brief_text and not self._plan and not self._events:
            self.clear()
            return
        self._has_brief = True
        self.setMaximumHeight(16777215)
        self.setMinimumHeight(200)
        try:
            self._render_notebook()
        except Exception:
            traceback.print_exc()
            raise
        self.notebook.show()
        self.btn_generate.hide()
        self.helper.hide()
        self.marker.hide()
        self.loading_label.hide()
        self.btn_regenerate.show()
        self.btn_telegram.show()
        self.title.setText("Study Plan")
        if rag_enhanced:
            self.rag_note.setText("Enhanced using uploaded study material")
            self.rag_note.show()
        elif (rag_message or "").strip():
            self.rag_note.setText(rag_message.strip())
            self.rag_note.show()
        else:
            self.rag_note.hide()
        if ai_mode is not None:
            self.set_ai_source(ai_mode)
        # Keep planning_anchor in plan data for regenerate; do not show in UI
        self.anchor_label.hide()
        self.scroll_to_top()

    def scroll_to_top(self) -> None:
        bar = self.note_scroll.verticalScrollBar()
        bar.setValue(bar.minimum())

    def set_busy(self, busy: bool) -> None:
        if busy:
            return
        # Busy cleared by presenter; keep regenerate enabled when plan exists
        if not self._loading:
            self.btn_generate.setEnabled(True)
            self.btn_regenerate.setEnabled(self._has_brief)
            self.btn_telegram.setEnabled(self._has_brief)

    def _clear_note(self) -> None:
        while self.note_layout.count():
            item = self.note_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_notebook(self) -> None:
        self._clear_note()
        plan = self._plan or {}
        daily = plan.get("daily_plan") or []

        summary = (plan.get("summary") or "").strip()
        if summary:
            sum_lbl = QLabel(summary)
            sum_lbl.setObjectName("mutedLabel")
            sum_lbl.setWordWrap(True)
            self.note_layout.addWidget(sum_lbl)

        if daily:
            for day in daily:
                self._render_day(day)
        elif self._brief_text:
            body = QLabel(self._brief_text)
            body.setObjectName("mutedLabel")
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.note_layout.addWidget(body)
        else:
            empty = QLabel("No free time slots were found for a study schedule.")
            empty.setObjectName("mutedLabel")
            self.note_layout.addWidget(empty)

        tip = self._ai_suggestion(plan)
        if tip:
            tip_box = QFrame()
            tip_box.setObjectName("aiTipBox")
            tip_lay = QVBoxLayout(tip_box)
            tip_lay.setContentsMargins(10, 8, 10, 8)
            tip_head = QLabel("AI suggestion")
            tip_head.setObjectName("summaryHeading")
            tip_body = QLabel(tip)
            tip_body.setObjectName("mutedLabel")
            tip_body.setWordWrap(True)
            tip_lay.addWidget(tip_head)
            tip_lay.addWidget(tip_body)
            self.note_layout.addWidget(tip_box)

        self.note_layout.addStretch()

    def _render_day(self, day: dict) -> None:
        raw_date = str(day.get("date") or "")
        try:
            label = date.fromisoformat(raw_date).strftime("%A, %d %b")
        except Exception:
            label = raw_date or "Day"

        day_title = QLabel(label)
        day_title.setObjectName("notebookDay")
        self.note_layout.addWidget(day_title)

        for item in day.get("items") or []:
            kind = str(item.get("kind") or "study")
            card = QFrame()
            if kind == "break":
                card.setObjectName("timelineBreak")
            elif kind == "meal":
                card.setObjectName("timelineMeal")
            elif kind == "calendar":
                card.setObjectName("timelineCalendar")
            elif kind == "recovery":
                card.setObjectName("timelineRecovery")
            else:
                card.setObjectName("timelineStudy")
            category = (item.get("category") or "").strip()
            if kind == "calendar" and category:
                accent = category_style(category)["accent"]
                card.setStyleSheet(
                    "QFrame#timelineCalendar {"
                    "background-color: rgba(255, 255, 255, 0.78);"
                    "border: 1px solid #E8E0D4;"
                    f"border-left: 3px solid {accent};"
                    "border-radius: 8px;"
                    "}"
                )
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            lay = QVBoxLayout(card)
            lay.setContentsMargins(12, 10, 12, 10)
            lay.setSpacing(4)

            start_t = (item.get("start_time") or "").strip()
            end_t = (item.get("end_time") or "").strip()
            time_s = f"{start_t}–{end_t}" if start_t and end_t else (start_t or end_t)
            if time_s:
                meta = QLabel(time_s)
                meta.setObjectName("notebookMeta")
                lay.addWidget(meta)

            label = (item.get("label") or "").strip()
            if kind == "calendar":
                tag = "CALENDAR EVENT"
                if category:
                    tag = f"CALENDAR EVENT — {category}"
                tag_lbl = QLabel(tag)
                tag_lbl.setObjectName("summaryHeading")
                lay.addWidget(tag_lbl)
            elif kind == "study":
                tag_lbl = QLabel("STUDY SESSION")
                tag_lbl.setObjectName("summaryHeading")
                lay.addWidget(tag_lbl)
            elif kind == "meal":
                tag_lbl = QLabel((label or "MEAL").upper())
                tag_lbl.setObjectName("summaryHeading")
                lay.addWidget(tag_lbl)
            elif kind == "break":
                tag_lbl = QLabel("BREAK")
                tag_lbl.setObjectName("summaryHeading")
                lay.addWidget(tag_lbl)
            elif kind == "recovery":
                tag_lbl = QLabel("RECOVERY")
                tag_lbl.setObjectName("summaryHeading")
                lay.addWidget(tag_lbl)

            title = QLabel(str(item.get("title") or "Study block"))
            title.setObjectName("notebookTitle")
            title.setWordWrap(True)
            title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            lay.addWidget(title)

            action = (item.get("action") or "").strip()
            if action:
                action_lbl = QLabel(action)
                action_lbl.setObjectName("notebookNote")
                action_lbl.setWordWrap(True)
                lay.addWidget(action_lbl)

            if kind == "study":
                reason = (item.get("reason") or "").strip()
                if reason:
                    reason_lbl = QLabel(reason)
                    reason_lbl.setObjectName("mutedLabel")
                    reason_lbl.setWordWrap(True)
                    lay.addWidget(reason_lbl)

            self.note_layout.addWidget(card)

    @staticmethod
    def _ai_suggestion(plan: dict) -> str:
        tips = plan.get("tips") or []
        if tips and str(tips[0]).strip():
            return str(tips[0]).strip()
        priority = plan.get("priority_item") or {}
        if isinstance(priority, dict):
            title = (priority.get("title") or "").strip()
            reason = (priority.get("reason") or "").strip()
            if title and reason:
                return f"{title} — {reason}"
            return title or reason
        return ""
