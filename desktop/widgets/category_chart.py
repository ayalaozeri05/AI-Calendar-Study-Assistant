"""Category chart — pastel bars, no decorative painter effects."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QVBoxLayout, QWidget

from styles import category_style


class CategoryChartWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._chart = QChart()
        self._chart.setTitle("By category")
        self._chart.setAnimationOptions(QChart.SeriesAnimations)
        self._chart.legend().setVisible(False)
        self._chart.setBackgroundVisible(False)
        self._chart.setPlotAreaBackgroundVisible(False)
        self._chart.setTitleBrush(QColor("#7D8495"))

        self._view = QChartView(self._chart)
        self._view.setRenderHint(QPainter.Antialiasing)
        self._view.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    def update_from_events(self, events: list[dict]) -> None:
        counts = Counter(e.get("category", "Other") for e in events)
        order = ["Exam", "Assignment", "Project", "Study", "Class", "Meeting", "Other"]
        categories = [c for c in order if counts.get(c, 0) > 0]
        if not categories:
            categories = ["None"]
            values = [0]
            colors = [QColor("#D8D3CA")]
        else:
            values = [counts[c] for c in categories]
            colors = [QColor(category_style(c)["accent"]) for c in categories]

        series = QBarSeries()
        for category, value, color in zip(categories, values, colors):
            bar_set = QBarSet(category)
            row = [0] * len(categories)
            row[categories.index(category)] = value
            bar_set.append(row)
            bar_set.setColor(color)
            bar_set.setBorderColor(color)
            series.append(bar_set)

        self._chart.removeAllSeries()
        for axis in list(self._chart.axes()):
            self._chart.removeAxis(axis)

        self._chart.addSeries(series)
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsColor(QColor("#7D8495"))
        self._chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0, max(values) + 1)
        axis_y.setLabelFormat("%d")
        axis_y.setLabelsColor(QColor("#7D8495"))
        axis_y.setGridLineColor(QColor("#E5E1DA"))
        self._chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)
