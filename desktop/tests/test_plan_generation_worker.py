"""Plan generation must not block the Qt UI thread."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DESKTOP = Path(__file__).resolve().parents[1]
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))

from PySide6.QtCore import QObject, QThread, Slot
from PySide6.QtWidgets import QApplication

from api_client.backend_client import AI_TIMEOUT, BackendApiError, BackendClient
from presenters.dashboard_presenter import DashboardPresenter
from views.dashboard_view import DashboardView
from widgets.brief_panel import BriefPanel
from workers.plan_generation_worker import PlanGenerationWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class SlowClient(BackendClient):
    def __init__(self, delay: float = 0.35, result: dict | None = None) -> None:
        super().__init__()
        self.delay = delay
        self.result = result or {
            "text": "Plan",
            "plan": {
                "summary": "Summary",
                "daily_plan": [
                    {
                        "date": "2026-08-07",
                        "items": [
                            {
                                "start_time": "16:00",
                                "end_time": "17:00",
                                "title": "Study",
                                "kind": "study",
                                "action": "Review",
                            }
                        ],
                    },
                    {
                        "date": "2026-08-08",
                        "items": [
                            {
                                "start_time": "10:00",
                                "end_time": "11:00",
                                "title": "Practice",
                                "kind": "study",
                            }
                        ],
                    },
                ],
                "tips": ["Tip"],
            },
            "ai_mode": "ollama",
            "event_count": 2,
            "planning_anchor": None,
        }
        self.calls = 0

    def generate_range_brief(self, *args, **kwargs):
        self.calls += 1
        time.sleep(self.delay)
        return self.result


class _ResultProbe(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.ok = False
        self.payload = None

    @Slot(object)
    def on_finished(self, result) -> None:
        self.ok = True
        self.payload = result


def test_ai_timeout_is_dedicated_tuple():
    assert AI_TIMEOUT == (10, 120)


def test_slow_backend_does_not_freeze_qt(qapp):
    client = SlowClient(delay=0.35)
    worker = PlanGenerationWorker(
        client, "user-1", "2026-08-07", "2026-08-08", label="Test"
    )
    thread = QThread()
    probe = _ResultProbe()
    worker.moveToThread(thread)
    worker.finished.connect(probe.on_finished)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.start()

    ticks = 0
    deadline = time.time() + 3.0
    while time.time() < deadline and not probe.ok:
        qapp.processEvents()
        ticks += 1
        time.sleep(0.02)

    assert thread.wait(3000)
    assert probe.ok
    assert ticks > 5
    assert client.calls == 1
    assert isinstance(probe.payload, dict)


def test_loading_disables_buttons_and_restores(qapp):
    panel = BriefPanel()
    panel.show()
    qapp.processEvents()
    panel.set_loading(True)
    assert panel.loading_label.isVisible()
    assert "AI study plan" in panel.loading_label.text()
    assert not panel.btn_generate.isEnabled()
    panel.set_loading(False)
    assert panel.btn_generate.isEnabled()
    assert not panel.loading_label.isVisible()


def test_success_updates_ui_and_preserves_ai_mode(qapp):
    view = DashboardView()
    view.show()
    client = SlowClient(delay=0.05)
    presenter = DashboardPresenter(view, client)
    presenter.state.student = MagicMock(id="user-1")
    view.planner_page.populate_events(
        [
            {
                "title": "Exam",
                "category": "Exam",
                "start": "2026-08-10T09:00:00+00:00",
                "end": "2026-08-10T10:00:00+00:00",
            }
        ]
    )
    view.show_planner()
    qapp.processEvents()
    view.planner_page.current_range = lambda: ("7days", "2026-08-07", "2026-08-13")
    presenter.generate_range_brief(regenerate=False)

    deadline = time.time() + 3.0
    while time.time() < deadline and presenter.state.plan_request_in_flight:
        qapp.processEvents()
        time.sleep(0.02)
    for _ in range(20):
        qapp.processEvents()
        time.sleep(0.01)

    assert presenter.state.ai_mode == "ollama"
    assert presenter.state.brief_plan is not None
    assert "Ollama" in view.planner_page.brief.ai_source_label.text()
    assert view.planner_page.brief._has_brief
    assert view.planner_page.brief.notebook.isVisible()
    assert view.planner_page.brief.note_layout.count() > 1
    assert view.planner_page.right_host.isVisible()
    assert view.planner_page.brief.btn_generate.isEnabled()
    assert len(presenter.state.brief_plan.get("daily_plan") or []) == 2


def test_plan_finished_slot_runs_on_ui_thread(qapp):
    """Regression: worker success must reach the UI thread via the plan bridge."""
    view = DashboardView()
    view.show()
    client = SlowClient(delay=0.05)
    presenter = DashboardPresenter(view, client)
    seen = {"thread": None}

    class Probe(QObject):
        @Slot(object)
        def on_success(self, result):
            seen["thread"] = QThread.currentThread()

    probe = Probe(presenter)
    presenter._plan_bridge.succeeded.connect(probe.on_success)

    worker = PlanGenerationWorker(
        client, "user-1", "2026-08-07", "2026-08-13", label="t"
    )
    thread = QThread()
    worker.moveToThread(thread)
    worker.finished.connect(presenter._plan_bridge.succeeded)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    thread.start()
    deadline = time.time() + 3.0
    while time.time() < deadline and seen["thread"] is None:
        qapp.processEvents()
        time.sleep(0.02)
    thread.wait(2000)
    assert seen["thread"] is qapp.thread()
    assert presenter.state.ai_mode == "ollama"
    assert view.planner_page.brief.note_layout.count() > 1


def test_timeout_and_empty_range_keep_previous_plan(qapp):
    view = DashboardView()
    client = MagicMock()
    presenter = DashboardPresenter(view, client)
    presenter.state.student = MagicMock(id="user-1")
    previous = {"summary": "Old", "daily_plan": [{"date": "2026-08-07", "items": []}]}
    presenter.state.brief_plan = previous
    presenter.state.brief_text = "Old plan"
    presenter.state.ai_mode = "ollama"
    view.show()
    view.show_planner()
    view.set_brief_text("Old plan", plan=previous, ai_mode="ollama")
    qapp.processEvents()

    presenter._on_plan_failed(
        "No events were found in the selected date range.",
        "no_events_in_range",
        {"matching_event_count": 0},
    )
    qapp.processEvents()
    assert presenter.state.brief_plan == previous
    assert "Ollama" in view.planner_page.brief.ai_source_label.text()


def test_fallback_still_renders(qapp):
    panel = BriefPanel()
    panel.show()
    qapp.processEvents()
    panel.set_brief(
        "Fallback text",
        plan={
            "summary": "Engine plan",
            "daily_plan": [
                {
                    "date": "2026-08-07",
                    "items": [{"title": "Study", "kind": "study", "start_time": "16:00"}],
                }
            ],
        },
        ai_mode="rule_based_fallback",
    )
    qapp.processEvents()
    assert panel._has_brief
    assert panel.notebook.isVisible()
    # Normal UI hides technical fallback labels
    assert not panel.ai_source_label.isVisible() or panel.ai_source_label.text() == ""


def test_deterministic_plan_hides_source_and_renders(qapp):
    panel = BriefPanel()
    panel.show()
    qapp.processEvents()
    panel.set_brief(
        "Deterministic plan",
        plan={
            "summary": "Engine plan",
            "daily_plan": [
                {
                    "date": "2026-08-07",
                    "items": [{"title": "Study", "kind": "study", "start_time": "16:00"}],
                }
            ],
        },
        ai_mode="deterministic",
    )
    qapp.processEvents()
    assert panel._has_brief
    assert panel.notebook.isVisible()
    assert not panel.ai_source_label.isVisible()
    assert "Rule-based" not in panel.ai_source_label.text()
    assert "Ollama" not in panel.ai_source_label.text()


def test_malformed_json_surfaces_readable_error():
    err = BackendApiError("Malformed JSON response from server.", code="malformed_json")
    msg = DashboardPresenter._friendly_error(err)
    assert "invalid" in msg.lower() or "malformed" in msg.lower()
