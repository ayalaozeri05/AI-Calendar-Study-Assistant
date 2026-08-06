"""Compact priority + workload summary."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

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


class SummaryCard(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("summaryCard")
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(16)

        self._blocks: list[tuple[QLabel, QLabel]] = []
        for _ in range(3):
            col = QVBoxLayout()
            col.setSpacing(2)
            heading = QLabel()
            heading.setObjectName("summaryHeading")
            body = QLabel()
            body.setObjectName("mutedLabel")
            body.setWordWrap(True)
            body.setTextFormat(Qt.RichText)
            col.addWidget(heading)
            col.addWidget(body)
            root.addLayout(col, 1)
            self._blocks.append((heading, body))

    def update_from_events(self, events: list[dict], mode: str = "today") -> None:
        if not events:
            self.hide()
            return

        counts = Counter(str(e.get("category", "Other")) for e in events)
        lines = [f"<b>{len(events)}</b> events"]
        for cat in ("Exam", "Assignment", "Project", "Study"):
            n = counts.get(cat, 0)
            if n:
                label = cat.lower() + ("s" if n != 1 else "")
                lines.append(f"{n} {label}")
        self._blocks[0][0].setText("Upcoming")
        self._blocks[0][1].setText("<br>".join(lines))

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
        self._blocks[1][0].setText("Highest priority")
        if chosen:
            style = category_style(str(chosen.get("category", "Other")))
            self._blocks[1][1].setText(
                f"{chosen.get('title', 'Untitled')}<br>"
                f"<span style='color:{style['fg']}; font-weight:600'>"
                f"{chosen.get('category')}</span>"
            )
        else:
            self._blocks[1][1].setText("—")

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
            self._blocks[2][0].setText("Day overview")
            only = next(iter(by_day.values()), events)
            self._blocks[2][1].setText(_workload_label(only))
        else:
            self._blocks[2][0].setText("Busy dates")
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
            self._blocks[2][1].setText(
                "<br>".join(day_labels) if day_labels else "Even pace"
            )

        self.show()
