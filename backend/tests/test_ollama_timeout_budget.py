"""Ollama polish must return fallback within a hard HTTP/budget timeout."""

from __future__ import annotations

import inspect
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from app.config import settings
from app.gateways.ollama_gateway import OllamaGateway, OllamaTimeoutError
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.schemas.brief_schema import PriorityItem, StructuredStudyPlan
from app.services.ai_recommendation_service import AiRecommendationService
from app.services.study_scheduling_engine import StudySchedulingEngine


def _evt(title, cat, start, hours=1.0, desc=None):
    return ClassifiedCalendarEvent(
        id=title,
        title=title,
        category=cat,
        start=start,
        end=start + timedelta(hours=hours),
        description=desc,
    )


def test_gateway_invoke_does_not_use_threadpool_executor():
    src = inspect.getsource(OllamaGateway.invoke)
    assert "concurrent.futures" not in src
    assert "executor" not in src.lower()
    assert "httpx.Client" in src or "httpx.Timeout" in src


def test_stuck_http_server_triggers_read_timeout_quickly():
    """A server that accepts but never replies must not block past read timeout."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    stop = threading.Event()

    def _serve() -> None:
        conn, _ = sock.accept()
        # Never respond — hold the connection until test ends.
        while not stop.wait(0.05):
            pass
        try:
            conn.close()
        except OSError:
            pass

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    class _Cfg:
        ollama_base_url = f"http://127.0.0.1:{port}"
        ollama_model = "llama3.2"
        ollama_timeout_sec = 1.5
        skip_ollama_polish = False

    gw = OllamaGateway(app_settings=_Cfg())  # type: ignore[arg-type]
    # Bypass tags/ready probe — exercise invoke HTTP path only.
    gw.ensure_ready = lambda: None  # type: ignore[method-assign]

    t0 = time.perf_counter()
    with pytest.raises(OllamaTimeoutError):
        gw.invoke("hello", timeout_sec=1.5)
    elapsed = time.perf_counter() - t0
    stop.set()
    sock.close()
    assert elapsed < 4.0, f"httpx timeout did not cancel quickly: {elapsed:.2f}s"


def test_never_returning_ollama_returns_fallback_within_budget(monkeypatch):
    monkeypatch.setattr(settings, "ai_polish_enabled", True)
    monkeypatch.setattr(settings, "ollama_timeout_sec", 2.0)
    monkeypatch.setattr(settings, "skip_ollama_polish", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, day.replace(hour=9), 2),
        _evt("Next", EventCategory.EXAM, day + timedelta(days=5), desc="Topic"),
    ]

    def hang_invoke(*_a, **_k):
        raise OllamaTimeoutError("simulated never-return cancelled by httpx")

    ollama = MagicMock()
    ollama.is_available.return_value = True
    ollama.model = "llama3.2"
    ollama.invoke.side_effect = hang_invoke
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())

    t0 = time.perf_counter()
    plan, _, mode, warnings = svc.generate_study_plan(
        events, start=day.date(), end=day.date(), now=now
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0
    assert elapsed < 120.0
    assert mode == "rule_based_fallback"
    assert plan.daily_plan
    assert sum(len(d.items) for d in plan.daily_plan) > 0
    assert warnings == []
    assert svc.last_fallback_reason == "timeout"


def test_json_retry_does_not_stack_full_timeouts(monkeypatch):
    """First attempt consumes budget → skip second invoke (no 75+75)."""
    monkeypatch.setattr(settings, "ai_polish_enabled", True)
    monkeypatch.setattr(settings, "ollama_timeout_sec", 20.0)
    monkeypatch.setattr(settings, "skip_ollama_polish", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, day.replace(hour=9), 2),
        _evt("Next", EventCategory.EXAM, day + timedelta(days=5), desc="Topic"),
    ]

    calls: list[float | None] = []
    clock = {"t": 1000.0}

    def fake_perf():
        return clock["t"]

    def invoke(_prompt, *, temperature=0.2, timeout_sec=None, max_tokens=None):
        _ = max_tokens
        calls.append(timeout_sec)
        # Consume almost the entire remaining budget so retry is skipped.
        clock["t"] += max(0.0, float(timeout_sec or 0.0) - 1.0)
        return "not-valid-json{"

    monkeypatch.setattr(time, "perf_counter", fake_perf)
    ollama = MagicMock()
    ollama.is_available.return_value = True
    ollama.model = "llama3.2"
    ollama.invoke.side_effect = invoke
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())

    plan, _, mode, warnings = svc.generate_study_plan(
        events, start=day.date(), end=day.date(), now=now
    )
    assert len(calls) == 1, f"expected one invoke within budget, got {calls}"
    assert mode == "rule_based_fallback"
    assert plan.daily_plan
    assert warnings == []
    assert svc.last_fallback_reason == "timeout"


def test_fast_ollama_still_returns_ollama_mode(monkeypatch):
    monkeypatch.setattr(settings, "ai_polish_enabled", True)
    monkeypatch.setattr(settings, "skip_ollama_polish", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, day.replace(hour=9), 2),
        _evt("Next", EventCategory.EXAM, day + timedelta(days=5), desc="Topic"),
    ]
    engine_plan = StudySchedulingEngine().build(
        events,
        range_start=day.date(),
        range_end=day.date(),
        now=now,
        language="en",
    )
    polished = StructuredStudyPlan(
        summary="Polished focus",
        priority_item=PriorityItem(title="Exam", reason="Soon"),
        daily_plan=engine_plan.daily_plan,
        tips=["Tip"],
        planning_anchor=engine_plan.planning_anchor,
    )

    ollama = MagicMock()
    ollama.is_available.return_value = True
    ollama.model = "llama3.2"
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())
    svc._polish_with_ollama = MagicMock(return_value=polished)  # type: ignore[method-assign]

    plan, _, mode, warnings = svc.generate_study_plan(
        events, start=day.date(), end=day.date(), now=now
    )
    assert mode == "ollama"
    assert plan.summary == "Polished focus"
    assert warnings == []


def test_skip_flag_under_two_seconds(monkeypatch):
    monkeypatch.setattr(settings, "ai_polish_enabled", False)
    monkeypatch.setattr(settings, "skip_ollama_polish", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        _evt("Exam", EventCategory.EXAM, day.replace(hour=9), 2),
        _evt("Next", EventCategory.EXAM, day + timedelta(days=5), desc="Topic"),
    ]
    ollama = MagicMock()
    svc = AiRecommendationService(ollama=ollama, engine=StudySchedulingEngine())
    t0 = time.perf_counter()
    plan, _, mode, warnings = svc.generate_study_plan(
        events, start=day.date(), end=day.date(), now=now
    )
    assert time.perf_counter() - t0 < 2.0
    assert mode == "deterministic"
    assert warnings == []
    assert plan.daily_plan
    ollama.invoke.assert_not_called()


def test_gateway_timeout_uses_httpx_timeout_object(monkeypatch):
    captured: dict = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *_a, **_k):
            raise httpx.ReadTimeout("read timed out")

    class _Cfg:
        ollama_base_url = "http://127.0.0.1:9"
        ollama_model = "llama3.2"
        ollama_timeout_sec = 75.0
        skip_ollama_polish = False

    gw = OllamaGateway(app_settings=_Cfg())  # type: ignore[arg-type]
    gw.ensure_ready = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    with pytest.raises(OllamaTimeoutError):
        gw.invoke("x", timeout_sec=60.0)

    timeout = captured["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 60.0
    assert timeout.connect == 5.0
