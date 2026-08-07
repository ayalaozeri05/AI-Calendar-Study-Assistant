"""Fixed three-card summary strip — LTR geometry, RTL only on title text."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from styles import category_style


def _workload_label(events_for_day: list[dict]) -> str:
    """Calendar density → Light / Moderate / Heavy / Very heavy."""
    if not events_for_day:
        return "Light"
    cats = Counter(str(e.get("category", "Other")) for e in events_for_day)
    exams = cats.get("Exam", 0)
    heavy_items = cats.get("Assignment", 0) + cats.get("Project", 0) + exams
    total = len(events_for_day)

    if exams >= 2 or (exams >= 1 and total >= 4):
        return "Very heavy"
    if exams >= 1 and heavy_items >= 2:
        return "Heavy"
    if total >= 5 or heavy_items >= 3:
        return "Heavy"
    if total >= 3 or heavy_items >= 2:
        return "Moderate"
    if total >= 2:
        return "Moderate"
    return "Light"


class SummaryMiniCard(QFrame):
    """One fixed summary cell. Parent layout stays LTR; only title may be RTL."""

    def __init__(self, heading: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("summaryMiniCard")
        self.setLayoutDirection(Qt.LeftToRight)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(140)
        self.setMinimumHeight(88)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.setDirection(QVBoxLayout.TopToBottom)

        self.heading = QLabel(heading)
        self.heading.setObjectName("summaryHeading")
        self.heading.setLayoutDirection(Qt.LeftToRight)
        self.heading.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.heading.setTextInteractionFlags(Qt.NoTextInteraction)

        self.primary = QLabel("—")
        self.primary.setObjectName("summaryPrimary")
        self.primary.setLayoutDirection(Qt.LeftToRight)
        self.primary.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.primary.setWordWrap(True)
        self.primary.setTextInteractionFlags(Qt.NoTextInteraction)
        self.primary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.secondary = QLabel("")
        self.secondary.setObjectName("summarySecondary")
        self.secondary.setLayoutDirection(Qt.LeftToRight)
        self.secondary.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.secondary.setWordWrap(True)
        self.secondary.setTextInteractionFlags(Qt.NoTextInteraction)
        self.secondary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        lay.addWidget(self.heading)
        lay.addSpacing(6)
        lay.addWidget(self.primary)
        lay.addSpacing(4)
        lay.addWidget(self.secondary)

    def set_heading(self, text: str) -> None:
        self.heading.setText(text)

    def set_values(
        self,
        primary: str,
        secondary: str = "",
        *,
        primary_rtl_auto: bool = False,
        secondary_html: bool = False,
    ) -> None:
        primary = (primary or "").strip() or "—"
        secondary = (secondary or "").strip()

        if primary_rtl_auto:
            # RTL/LTR only inside the title line — card geometry stays LTR
            self.primary.setTextFormat(Qt.RichText)
            self.primary.setText(f'<span dir="auto">{escape(primary)}</span>')
        else:
            self.primary.setTextFormat(Qt.PlainText)
            self.primary.setText(primary)

        if secondary_html:
            self.secondary.setTextFormat(Qt.RichText)
            self.secondary.setText(secondary)
        else:
            self.secondary.setTextFormat(Qt.PlainText)
            self.secondary.setText(secondary)
        self.secondary.setVisible(bool(secondary))

        # Cap title to ~2 lines via elision when extremely long
        self._elide_primary_if_needed(primary if not primary_rtl_auto else primary)

    def _elide_primary_if_needed(self, plain: str) -> None:
        if len(plain) <= 80:
            return
        fm = QFontMetrics(self.primary.font())
        width = max(self.primary.width(), self.minimumWidth() - 28)
        if width < 40:
            width = 220
        # Approximate two-line budget
        budget = width * 2
        elided = fm.elidedText(plain, Qt.ElideRight, budget)
        if elided != plain and not self.primary.textFormat() == Qt.RichText:
            self.primary.setText(elided)
        elif elided != plain:
            self.primary.setText(f'<span dir="auto">{escape(elided)}</span>')


class SummaryCard(QFrame):
    """Three equal-width mini-cards: Upcoming | Highest priority | Overview."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("summaryStrip")
        self.setLayoutDirection(Qt.LeftToRight)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.setDirection(QHBoxLayout.LeftToRight)
        root.setAlignment(Qt.AlignTop)

        self.upcoming = SummaryMiniCard("Upcoming")
        self.priority = SummaryMiniCard("Highest priority")
        self.overview = SummaryMiniCard("Day overview")

        for card in (self.upcoming, self.priority, self.overview):
            root.addWidget(card, 1)

    def update_from_events(self, events: list[dict], mode: str = "today") -> None:
        if not events:
            self.hide()
            return

        counts = Counter(str(e.get("category", "Other")) for e in events)
        lines = [f"{len(events)} events"]
        for cat in ("Exam", "Assignment", "Project", "Study"):
            n = counts.get(cat, 0)
            if n:
                label = cat.lower() + ("s" if n != 1 else "")
                lines.append(f"{n} {label}")
        self.upcoming.set_heading("Upcoming")
        self.upcoming.set_values(lines[0], "\n".join(lines[1:]) if len(lines) > 1 else "")

        priority_order = (
            "Exam",
            "Assignment",
            "Project",
            "Study",
            "Class",
            "Meeting",
            "Other",
        )
        chosen = None
        for cat in priority_order:
            items = [e for e in events if e.get("category") == cat]
            if items:
                chosen = sorted(items, key=lambda e: str(e.get("start") or ""))[0]
                break

        self.priority.set_heading("Highest priority")
        if chosen:
            style = category_style(str(chosen.get("category", "Other")))
            cat = str(chosen.get("category") or "")
            title = str(chosen.get("title") or "Untitled")
            self.priority.set_values(
                title,
                f"<span style='color:{style['fg']}; font-weight:600'>{escape(cat)}</span>",
                primary_rtl_auto=True,
                secondary_html=True,
            )
        else:
            self.priority.set_values("—", "")

        by_day: dict[str, list[dict]] = defaultdict(list)
        for event in events:
            try:
                key = datetime.fromisoformat(
                    str(event.get("start")).replace("Z", "+00:00")
                ).strftime("%d %b")
                by_day[key].append(event)
            except Exception:
                continue

        if mode == "today" or len(by_day) <= 1:
            self.overview.set_heading("Day overview")
            only = next(iter(by_day.values()), events)
            self.overview.set_values(_workload_label(only), "")
        else:
            self.overview.set_heading("Busy dates")
            day_labels = []
            for day, day_events in sorted(
                by_day.items(),
                key=lambda item: (-len(item[1]), item[0]),
            )[:3]:
                label = _workload_label(day_events)
                if label in ("Moderate", "Heavy", "Very heavy"):
                    day_labels.append(f"{day} · {label}")
            if not day_labels:
                for day, day_events in sorted(
                    by_day.items(),
                    key=lambda item: (-len(item[1]), item[0]),
                )[:2]:
                    day_labels.append(f"{day} · {_workload_label(day_events)}")
            primary = day_labels[0] if day_labels else "Even pace"
            secondary = "\n".join(day_labels[1:]) if len(day_labels) > 1 else ""
            self.overview.set_values(primary, secondary)

        self.show()
