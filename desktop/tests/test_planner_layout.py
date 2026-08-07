"""Offscreen layout checks for empty state and summary strip geometry."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DESKTOP = Path(__file__).resolve().parents[1]
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))

from PySide6.QtWidgets import QApplication

from pages.planner_page import PlannerPage
from widgets.summary_card import SummaryCard


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _event(title: str, category: str = "Exam") -> dict:
    return {
        "title": title,
        "category": category,
        "start": "2026-08-10T09:00:00+00:00",
        "end": "2026-08-10T10:00:00+00:00",
    }


def test_empty_state_sits_under_events_heading(qapp):
    page = PlannerPage()
    page.resize(1366, 768)
    page.set_sync_context(connected=True, has_synced=True)
    page.populate_events([])
    page.show()
    qapp.processEvents()

    assert page.empty_card.isVisible()
    assert not page.scroll.isVisible()
    assert not page.summary.isVisible()
    assert not page.right_host.isVisible()

    heading_bottom = page.events_label.mapTo(page, page.events_label.rect().bottomLeft()).y()
    card_top = page.empty_card.mapTo(page, page.empty_card.rect().topLeft()).y()
    # Card must start just below EVENTS — not near the window bottom
    assert card_top >= heading_bottom
    assert card_top - heading_bottom <= 24
    assert page.empty_card.y() < page.height() * 0.45

    assert page.empty_title.text() == "No events today"
    assert "clear for the rest of today" in page.empty_message.text()
    assert page.btn_empty_primary.text() == "View next 7 days"


def test_empty_copy_by_range(qapp):
    page = PlannerPage()
    page.set_sync_context(connected=True, has_synced=True)
    page._mode = "7days"
    page.populate_events([])
    assert page.empty_title.text() == "No events in the next 7 days"
    assert page.btn_empty_primary.text() == "View 14 days"

    page._mode = "month"
    page.populate_events([])
    assert page.empty_title.text() == "No events this month"
    assert page.btn_empty_primary.text() == "Choose dates"


def test_summary_priority_card_stays_centered(qapp):
    strip = SummaryCard()
    strip.resize(900, 120)
    strip.show()
    qapp.processEvents()

    titles = [
        "Test",
        "מבחן באוטומטים",
        "Operating Systems מבחן",
        "Very long priority title that should wrap or elide without moving neighbors " * 2,
    ]
    centers = []
    for title in titles:
        strip.update_from_events([_event(title)], mode="today")
        qapp.processEvents()
        strip.adjustSize()
        strip.resize(900, strip.sizeHint().height())
        qapp.processEvents()
        geo = strip.priority.geometry()
        centers.append(geo.center().x())
        # Equal stretch: priority remains the middle third
        assert geo.left() >= 250
        assert geo.right() <= 650

    # Centers should stay within a few pixels across RTL/LTR titles
    assert max(centers) - min(centers) <= 8


def test_summary_three_equal_cards(qapp):
    strip = SummaryCard()
    strip.resize(900, 120)
    strip.update_from_events([_event("Test"), _event("HW", "Assignment")], mode="7days")
    strip.show()
    qapp.processEvents()
    widths = [
        strip.upcoming.width(),
        strip.priority.width(),
        strip.overview.width(),
    ]
    assert max(widths) - min(widths) <= 4
