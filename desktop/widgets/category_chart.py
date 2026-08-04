"""Simple bar chart of calendar events by category."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QVBoxLayout, QWidget


class CategoryChartWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._chart = QChart()
        self._chart.setTitle("Events by category")
        self._chart.setAnimationOptions(QChart.SeriesAnimations)
        self._chart.legend().setVisible(False)

        self._view = QChartView(self._chart)
        self._view.setRenderHint(QPainter.Antialiasing)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    def update_from_events(self, events: list[dict]) -> None:
        counts = Counter(e.get("category", "Other") for e in events)
        order = ["Exam", "Assignment", "Project", "Study", "Class", "Other"]
        categories = [c for c in order if counts.get(c, 0) > 0]
        if not categories:
            categories = ["None"]
            values = [0]
        else:
            values = [counts[c] for c in categories]

        bar_set = QBarSet("Events")
        bar_set.append(values)

        series = QBarSeries()
        series.append(bar_set)

        self._chart.removeAllSeries()
        for axis in self._chart.axes():
            self._chart.removeAxis(axis)

        self._chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        self._chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0, max(values) + 1)
        axis_y.setLabelFormat("%d")
        self._chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)
