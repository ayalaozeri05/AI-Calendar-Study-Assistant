"""Background Study Plan generation — never touch widgets from this object."""

from __future__ import annotations

import logging
import traceback
from typing import Any

from PySide6.QtCore import QObject, Signal

from api_client.backend_client import BackendClient, BackendApiError

logger = logging.getLogger(__name__)


class PlanGenerationWorker(QObject):
    """Runs POST /briefs/range on a worker thread; reports via signals only."""

    finished = Signal(object)  # BriefResponse dict
    failed = Signal(str, str, object)  # message, code, detail_dict|None

    def __init__(
        self,
        client: BackendClient,
        user_id: str,
        start_date: str,
        end_date: str,
        *,
        label: str | None = None,
        regenerate: bool = False,
        previous_plan: dict | None = None,
        variation_seed: int | None = None,
        planning_anchor: str | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._user_id = user_id
        self._start_date = start_date
        self._end_date = end_date
        self._label = label
        self._regenerate = regenerate
        self._previous_plan = previous_plan
        self._variation_seed = variation_seed
        self._planning_anchor = planning_anchor

    def run(self) -> None:
        logger.info(
            "plan_request_started user_id=%s range=%s..%s regenerate=%s",
            self._user_id,
            self._start_date,
            self._end_date,
            self._regenerate,
        )
        try:
            result = self._client.generate_range_brief(
                self._user_id,
                self._start_date,
                self._end_date,
                label=self._label,
                regenerate=self._regenerate,
                previous_plan=self._previous_plan,
                variation_seed=self._variation_seed,
                planning_anchor=self._planning_anchor,
            )
            if not isinstance(result, dict):
                raise RuntimeError("Malformed study plan response from server.")
            plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
            daily = plan.get("daily_plan") or []
            logger.info(
                "plan_request_ok status=200 keys=%s ai_mode=%s event_count=%s daily_plan_len=%s",
                sorted(result.keys()),
                result.get("ai_mode"),
                result.get("event_count"),
                len(daily) if isinstance(daily, list) else 0,
            )
            self.finished.emit(result)
        except BackendApiError as exc:
            logger.warning(
                "stage=desktop_worker_failed status=%s code=%s message=%s",
                exc.status_code,
                exc.code,
                (exc.message or "")[:160],
            )
            self.failed.emit(exc.message, exc.code or "", exc.detail)
        except Exception as exc:
            traceback.print_exc()
            logger.warning(
                "stage=desktop_worker_failed status=client code=client_error err=%s",
                type(exc).__name__,
            )
            self.failed.emit(str(exc).split("\n")[0][:200], "client_error", None)
