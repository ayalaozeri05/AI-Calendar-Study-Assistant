"""Workload-by-day strip with paper-styled event tooltips."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QCursor, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from styles import category_style


class PaperTip(QLabel):
    """Named light paper popup — avoids Windows dark-mode QToolTip."""

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setObjectName("paperTip")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWordWrap(True)
        self.setMargin(0)
        self.setStyleSheet(
            "QLabel#paperTip {"
            "background-color: #FFFDF8;"
            "color: #273043;"
            "border: 1px solid #D8D0C4;"
            "padding: 6px 8px;"
            "border-radius: 4px;"
            "font-size: 12px;"
            "font-weight: 500;"
            "}"
        )
        self.hide()

    def show_text(self, text: str, global_pos: QPoint) -> None:
        text = (text or "").strip()
        if not text:
            self.hide()
            return
        self.setText(text)
        self.adjustSize()
        hint = self.sizeHint()
        self.resize(min(max(hint.width(), 80), 320), max(hint.height(), 24))
        self.move(global_pos + QPoint(12, 16))
        self.show()
        self.raise_()


class _TipFilter(QObject):
    def __init__(self, tip: PaperTip, text: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tip = tip
        self._text = text

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if et == QEvent.Type.Enter or et == QEvent.Type.ToolTip:
            if self._text:
                self._tip.show_text(self._text, QCursor.pos())
            return True if et == QEvent.Type.ToolTip else False
        if et == QEvent.Type.Leave:
            self._tip.hide()
        return False


class WorkloadTimeline(QFrame):
    _shared_tip: PaperTip | None = None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("timelineCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(4)

        title = QLabel("Workload")
        title.setObjectName("cardTitle")
        root.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(96)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.host = QWidget()
        self.host.setStyleSheet("background: transparent;")
        self.row = QHBoxLayout(self.host)
        self.row.setContentsMargins(2, 2, 2, 2)
        self.row.setSpacing(4)
        self.scroll.setWidget(self.host)
        root.addWidget(self.scroll)

        self._filters: list[_TipFilter] = []
        self._day_cells: list[tuple[QWidget, QProgressBar, int]] = []
        self._pending: tuple | None = None

    @classmethod
    def _tip(cls) -> PaperTip:
        if cls._shared_tip is None:
            cls._shared_tip = PaperTip()
        return cls._shared_tip

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._scale_bars()

    def _scale_bars(self) -> None:
        if not self._day_cells:
            return
        n = len(self._day_cells)
        avail = max(40, self.scroll.viewport().width() - 6)
        spacing = self.row.spacing() * max(0, n - 1)
        bar_w = max(8, min(28, (avail - spacing) // n))
        for _cell, bar, max_h in self._day_cells:
            bar.setFixedWidth(bar_w)
            # Keep height readable; shrink slightly when many days
            h = max_h if n <= 16 else max(48, max_h - 10)
            bar.setFixedHeight(h)

    def update_from_events(
        self,
        events: list[dict],
        start_iso: str,
        end_iso: str,
        mode: str,
    ) -> None:
        self._tip().hide()
        self._filters.clear()
        self._day_cells.clear()
        while self.row.count():
            item = self.row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if mode == "today" or not events:
            self.hide()
            return

        start = date.fromisoformat(start_iso)
        end = date.fromisoformat(end_iso)
        counts: Counter[str] = Counter()
        cats_by_day: dict[str, Counter[str]] = defaultdict(Counter)
        events_by_day: dict[str, list[dict]] = defaultdict(list)

        for event in events:
            raw = event.get("start")
            if not raw:
                continue
            try:
                day = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date().isoformat()
            except Exception:
                continue
            counts[day] += 1
            cats_by_day[day][str(event.get("category", "Other"))] += 1
            events_by_day[day].append(event)

        days: list[date] = []
        cur = start
        while cur <= end:
            days.append(cur)
            cur += timedelta(days=1)

        if mode == "month" and len(days) > 16:
            self._render_weeks(days, counts, cats_by_day, events_by_day)
        else:
            self._render_days(days, counts, cats_by_day, events_by_day)

        self._scale_bars()
        self.show()

    def _bar_color(self, cat_counts: Counter[str]) -> str:
        if cat_counts.get("Exam"):
            return category_style("Exam")["accent"]
        if cat_counts.get("Assignment"):
            return category_style("Assignment")["accent"]
        if cat_counts.get("Meeting"):
            return category_style("Meeting")["accent"]
        if cat_counts.get("Project"):
            return category_style("Project")["accent"]
        return category_style("Other")["accent"]

    @staticmethod
    def _tooltip_for_events(day_label: str, day_events: list[dict]) -> str:
        if not day_events:
            return ""
        n = len(day_events)
        workload = f"{n} event" if n == 1 else f"{n} events"
        lines = [f"Date: {day_label}", f"Workload: {workload}"]
        for event in sorted(day_events, key=lambda e: str(e.get("start") or ""))[:8]:
            cat = str(event.get("category", "Other"))
            title = str(event.get("title", "Untitled")).strip() or "Untitled"
            time_s = WorkloadTimeline._fmt_range(event.get("start"), event.get("end"))
            if time_s:
                lines.append(f"- {cat}: {title}, {time_s}")
            else:
                lines.append(f"- {cat}: {title}")
        return "\n".join(lines)

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
            return f"{a}–{b}"
        return a or b or ""

    def _bind_paper_tip(self, widget: QWidget, tip: str) -> None:
        widget.setToolTip("")
        if not tip or not tip.strip():
            return
        filt = _TipFilter(self._tip(), tip.strip(), widget)
        widget.installEventFilter(filt)
        self._filters.append(filt)

    def _render_days(
        self,
        days: list[date],
        counts: Counter[str],
        cats_by_day: dict[str, Counter[str]],
        events_by_day: dict[str, list[dict]],
    ) -> None:
        max_count = max((counts.get(d.isoformat(), 0) for d in days), default=0) or 1
        for day in days:
            key = day.isoformat()
            value = counts.get(key, 0)
            cats = cats_by_day.get(key, Counter())
            accent = self._bar_color(cats)
            height = 70 if value >= 2 else 56

            cell = QWidget()
            cell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            layout = QVBoxLayout(cell)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)

            bar = QProgressBar()
            bar.setOrientation(Qt.Vertical)
            bar.setTextVisible(False)
            bar.setRange(0, max_count)
            bar.setValue(value)
            bar.setFixedWidth(14)
            bar.setFixedHeight(height)
            bar.setStyleSheet(
                "QProgressBar { background:#EFE8DC; border:none; border-radius:6px; }"
                f"QProgressBar::chunk {{ background:{accent}; border-radius:6px; }}"
            )
            tip = self._tooltip_for_events(
                day.strftime("%d %b"), events_by_day.get(key, [])
            )
            self._bind_paper_tip(bar, tip)

            label = QLabel(day.strftime("%d"))
            label.setObjectName("mutedLabel")
            label.setAlignment(Qt.AlignCenter)
            self._bind_paper_tip(label, tip)

            layout.addStretch()
            layout.addWidget(bar, 0, Qt.AlignHCenter)
            layout.addWidget(label)
            self.row.addWidget(cell, 1)
            self._day_cells.append((cell, bar, height))

    def _render_weeks(
        self,
        days: list[date],
        counts: Counter[str],
        cats_by_day: dict[str, Counter[str]],
        events_by_day: dict[str, list[dict]],
    ) -> None:
        buckets: list[tuple[str, int, Counter[str], list[dict]]] = []
        i = 0
        week_num = 1
        while i < len(days):
            chunk = days[i : i + 7]
            total = sum(counts.get(d.isoformat(), 0) for d in chunk)
            merged: Counter[str] = Counter()
            week_events: list[dict] = []
            for d in chunk:
                merged.update(cats_by_day.get(d.isoformat(), Counter()))
                week_events.extend(events_by_day.get(d.isoformat(), []))
            label = (
                f"{chunk[0].strftime('%d %b')}–{chunk[-1].strftime('%d %b')}"
                if chunk
                else f"Week {week_num}"
            )
            buckets.append((label, total, merged, week_events))
            week_num += 1
            i += 7

        max_count = max((b[1] for b in buckets), default=0) or 1
        for label, total, cats, week_events in buckets:
            cell = QWidget()
            cell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            layout = QVBoxLayout(cell)
            layout.setContentsMargins(0, 0, 0, 0)
            accent = self._bar_color(cats)
            bar = QProgressBar()
            bar.setOrientation(Qt.Vertical)
            bar.setTextVisible(False)
            bar.setRange(0, max_count)
            bar.setValue(total)
            bar.setFixedWidth(22)
            bar.setFixedHeight(64)
            bar.setStyleSheet(
                "QProgressBar { background:#EFE8DC; border:none; border-radius:6px; }"
                f"QProgressBar::chunk {{ background:{accent}; border-radius:6px; }}"
            )
            tip = self._tooltip_for_events(label, week_events)
            self._bind_paper_tip(bar, tip)
            lab = QLabel("W")
            lab.setObjectName("mutedLabel")
            lab.setAlignment(Qt.AlignCenter)
            self._bind_paper_tip(lab, tip)
            layout.addStretch()
            layout.addWidget(bar, 0, Qt.AlignHCenter)
            layout.addWidget(lab)
            self.row.addWidget(cell, 1)
            self._day_cells.append((cell, bar, 64))
