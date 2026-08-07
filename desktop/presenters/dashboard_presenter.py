"""Presenter for Start → Calendar → Planner with range planning."""

from __future__ import annotations

import logging
import time
import traceback

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

from api_client.backend_client import BackendApiError, BackendClient
from models.dashboard_models import DashboardState, StudentInfo
from views.dashboard_view import DashboardView
from workers.plan_generation_worker import PlanGenerationWorker
from workers.rag_worker import RagUploadWorker

logger = logging.getLogger(__name__)

_BRIEF_LABELS = {
    "today": "Today Study Plan",
    "7days": "7-Day Study Plan",
    "14days": "14-Day Study Plan",
    "month": "Monthly Study Plan",
    "custom": "Custom Study Plan",
}


class _PlanUiBridge(QObject):
    """Receives worker-thread signals and re-emits them on the UI thread."""

    succeeded = Signal(object)
    failed = Signal(str, str, object)


class DashboardPresenter(QObject):
    """UI presenter. Lives on the Qt UI thread (parented to the view)."""

    def __init__(self, view: DashboardView, client: BackendClient) -> None:
        # Parent to the view so this object lives on the Qt UI thread.
        super().__init__(view)
        self.view = view
        self.client = client
        self.state = DashboardState()
        self._plan_thread: QThread | None = None
        self._plan_worker: PlanGenerationWorker | None = None
        self._rag_thread: QThread | None = None
        self._rag_worker: QObject | None = None
        self._rag_auto_regenerate = False
        # Worker → bridge (queued across threads) → presenter slots (UI thread).
        self._plan_bridge = _PlanUiBridge(self)
        self._plan_bridge.succeeded.connect(self._on_plan_finished)
        self._plan_bridge.failed.connect(self._on_plan_failed)

        self.view.load_demo_requested.connect(self.start_planner)
        self.view.connect_calendar_requested.connect(self.connect_google_calendar)
        self.view.sync_calendar_requested.connect(self.sync_calendar)
        self.view.range_events_requested.connect(self.load_range_events)
        self.view.generate_brief_requested.connect(
            lambda: self.generate_range_brief(regenerate=False)
        )
        self.view.regenerate_brief_requested.connect(
            lambda: self.generate_range_brief(regenerate=True)
        )
        self.view.send_telegram_requested.connect(self.send_current_brief)
        self.view.rag_upload_requested.connect(self.upload_study_material)
        self.view.rag_remove_requested.connect(self.remove_study_material)
        # Start empty; restore only after backend confirms indexed documents.
        self.view.planner_page.study_materials.clear_documents()
        self.refresh_study_material_status()

    def _require_student(self) -> str | None:
        if not self.state.student:
            self.view.show_status("Start the planner first.", is_error=True)
            return None
        return self.state.student.id

    def _refresh_calendar_status(self, user_id: str) -> None:
        try:
            status = self.client.get_calendar_status(user_id)
            connected = bool(status.get("connected"))
            self.state.calendar_connected = connected
            google_email = status.get("google_email")
            if not status.get("credentials_configured"):
                self.view.set_calendar_connection_status(
                    "Credentials missing", google_email=google_email
                )
            elif connected:
                self.view.set_calendar_connection_status(
                    "Connected", google_email=google_email
                )
            else:
                self.view.set_calendar_connection_status(
                    "Not connected", google_email=google_email
                )
        except Exception:
            self.state.calendar_connected = False
            self.view.set_calendar_connection_status("Not connected")

    def start_planner(self) -> None:
        if self.state.student:
            self._refresh_calendar_status(self.state.student.id)
            self.view.go_to_calendar_after_start()
            return

        self.view.set_busy(True)
        QApplication.processEvents()
        try:
            user = self.client.create_demo_user()
            self.state.student = StudentInfo(
                id=str(user["id"]),
                email=user.get("email", ""),
                full_name=user.get("full_name"),
                telegram_chat_id=user.get("telegram_chat_id"),
            )
            self.view.set_student_header(
                self.state.student.full_name or "Student",
                self.state.student.email,
            )
            self._refresh_calendar_status(self.state.student.id)
            self.view.go_to_calendar_after_start()
        except Exception as err:
            self.view.show_status(self._friendly_error(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def connect_google_calendar(self) -> None:
        user_id = self._require_student()
        if not user_id:
            return
        self.view.set_busy(True)
        self.view.show_status("Opening Google sign-in…")
        QApplication.processEvents()
        try:
            self.client.connect_google_calendar(user_id)
            self._refresh_calendar_status(user_id)
            self.view.show_status("Calendar connected")
        except Exception as err:
            self._refresh_calendar_status(user_id)
            self.view.show_status(self._friendly_error(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def sync_calendar(self) -> None:
        user_id = self._require_student()
        if not user_id:
            return
        self.view.set_busy(True)
        self.view.set_syncing(True)
        QApplication.processEvents()
        try:
            result = self.client.sync_google_calendar(user_id, days_ahead=62)
            events = result.get("events", [])
            self.state.last_sync_count = result.get("synced_count", len(events))
            self.state.events = events
            self.state.brief_text = ""
            self._refresh_calendar_status(user_id)
            self.view.on_sync_finished(events, self.state.last_sync_count)
        except Exception as err:
            self.view.set_syncing(False)
            self._refresh_calendar_status(user_id)
            self.view.show_status(self._friendly_error(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def load_range_events(self, mode: str, start_date: str, end_date: str) -> None:
        user_id = self._require_student()
        if not user_id:
            return
        self.view.set_busy(True)
        QApplication.processEvents()
        try:
            result = self.client.get_events_range(user_id, start_date, end_date)
            events = result.get("events", [])
            self.state.events = events
            self.state.brief_text = ""
            self.view.clear_brief()
            self.state.brief_text = ""
            self.state.brief_plan = None
            self.state.planning_anchor = None
            self.state.ai_mode = ""
            self.view.populate_events(events)
            self.view.set_ai_source("")
            self.refresh_study_material_status()
        except Exception as err:
            self.view.show_status(self._friendly_error(err), is_error=True)
        finally:
            self.view.set_busy(False)

    def generate_range_brief(self, regenerate: bool = False) -> None:
        user_id = self._require_student()
        if not user_id:
            return
        if self.state.plan_request_in_flight:
            return
        if self._plan_thread is not None and self._plan_thread.isRunning():
            return

        mode, start, end = self.view.current_range()
        label = _BRIEF_LABELS.get(mode, "Study Plan")
        if mode != "today":
            label = f"{label} — {start} to {end}"
        else:
            label = f"{label} — {start}"

        previous_plan = None
        planning_anchor = None
        if regenerate:
            previous_plan = self.state.brief_plan or self.view.current_brief_plan()
            planning_anchor = self.state.planning_anchor
            if not planning_anchor and isinstance(previous_plan, dict):
                planning_anchor = previous_plan.get("planning_anchor")
        else:
            self.state.planning_anchor = None

        variation_seed = int(time.time() * 1000) % 10_000_000
        logger.info(
            "plan_request_started user_id=%s range=%s..%s event_count_ui=%s",
            user_id,
            start,
            end,
            len(self.state.events or []),
        )

        self.state.plan_request_in_flight = True
        # Keep the window responsive: only disable plan buttons, not the whole shell.
        self.view.set_plan_loading(True, regenerating=regenerate)

        worker = PlanGenerationWorker(
            self.client,
            user_id,
            start,
            end,
            label=label,
            regenerate=regenerate,
            previous_plan=previous_plan,
            variation_seed=variation_seed,
            planning_anchor=planning_anchor,
        )
        thread = QThread(self.view)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # Signal→signal across threads is queued onto the bridge's (UI) thread.
        # Connecting the worker directly to plain methods runs on the worker thread
        # and paints an empty Study Plan while still showing "Study plan created".
        worker.finished.connect(self._plan_bridge.succeeded)
        worker.failed.connect(self._plan_bridge.failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._clear_plan_thread)
        self._plan_worker = worker
        self._plan_thread = thread
        thread.start()

    def _clear_plan_thread(self) -> None:
        worker = self._plan_worker
        thread = self._plan_thread
        self._plan_worker = None
        self._plan_thread = None
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()

    @Slot(object)
    def _on_plan_finished(self, result: object) -> None:
        # Guard: widget updates must run on the UI thread only.
        if QThread.currentThread() is not QApplication.instance().thread():
            logger.warning(
                "plan_finished_off_ui_thread — Study Plan UI would not paint correctly"
            )
        regenerating = False
        try:
            if not isinstance(result, dict):
                raise RuntimeError("Malformed study plan response from server.")
            text = result.get("text", "")
            plan = result.get("plan")
            if not text and not plan:
                raise RuntimeError("The planner returned an empty study plan.")
            ai_mode = str(result.get("ai_mode") or "deterministic")
            self.state.brief_text = text
            self.state.brief_plan = plan if isinstance(plan, dict) else None
            self.state.ai_mode = ai_mode
            anchor = result.get("planning_anchor")
            if not anchor and isinstance(plan, dict):
                anchor = plan.get("planning_anchor")
            if anchor:
                self.state.planning_anchor = str(anchor)
            mode, _, _ = self.view.current_range()
            self.state.last_brief_type = (
                "today"
                if mode == "today"
                else "weekly"
                if mode == "7days"
                else "range"
            )
            daily = (plan or {}).get("daily_plan") if isinstance(plan, dict) else []
            if not isinstance(daily, list) or not daily:
                raise RuntimeError("The server returned a plan with no daily schedule.")
            item_count = sum(
                len(d.get("items") or []) for d in daily if isinstance(d, dict)
            )
            if item_count <= 0:
                raise RuntimeError("The server returned a plan with no schedule items.")
            meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
            logger.info(
                "stage=desktop_received ai_mode=%s event_count=%s "
                "day_count=%s block_count=%s ollama_called=%s",
                ai_mode,
                result.get("event_count"),
                len(daily),
                item_count,
                meta.get("ollama_called"),
            )
            rag_enhanced = bool(meta.get("rag_used"))
            rag_message = meta.get("rag_message")
            if not isinstance(rag_message, str):
                rag_message = None
            self.view.set_brief_text(
                text,
                self.state.last_brief_type,
                plan=plan,
                ai_mode=ai_mode,
                rag_enhanced=rag_enhanced,
                rag_message=rag_message,
            )
            # Confirm cards actually exist before success toast.
            rendered = self.view.planner_page.brief
            if not rendered._has_brief or rendered.note_layout.count() <= 0:
                raise RuntimeError("Study Plan rendering failed.")
            logger.info(
                "stage=ui_render_completed day_count=%s block_count=%s rag_used=%s",
                len(daily),
                item_count,
                rag_enhanced,
            )
            if getattr(self, "_rag_auto_regenerate", False):
                self._rag_auto_regenerate = False
                if rag_enhanced:
                    self.view.toast.show_message(
                        "Study plan updated using uploaded study material.",
                        kind="success",
                    )
                else:
                    self.view.toast.show_message(
                        rag_message
                        or "No relevant study material was found for this study plan.",
                        kind="info",
                    )
            else:
                # Normal UI: always a clean success — never timeout/fallback banners.
                self.view.show_status("Study plan created")
        except Exception as err:
            traceback.print_exc()
            logger.warning("plan_render_failed err=%s", type(err).__name__)
            self.view.show_status(self._friendly_error(err), is_error=True)
            # Keep previous plan on render failure
            if self.state.ai_mode:
                self.view.set_ai_source(self.state.ai_mode)
        finally:
            self.state.plan_request_in_flight = False
            self.view.set_plan_loading(False, regenerating=regenerating)

    @Slot(str, str, object)
    def _on_plan_failed(self, message: str, code: str, detail: object) -> None:
        _ = detail
        friendly = self._friendly_error_message(message, code)
        is_soft = code in {
            "calendar_not_synced",
            "no_events_in_range",
        } or "no events" in friendly.lower()
        logger.warning(
            "stage=desktop_worker_failed code=%s keep_previous_plan=%s message=%s",
            code or "unknown",
            bool(self.state.brief_plan),
            (message or "")[:160],
        )
        self.view.show_status(friendly, is_error=not is_soft)
        # Keep previous plan / AI source on failure
        if self.state.ai_mode:
            self.view.set_ai_source(self.state.ai_mode)
        self.state.plan_request_in_flight = False
        self.view.set_plan_loading(False)

    def send_current_brief(self) -> None:
        user_id = self._require_student()
        if not user_id:
            return
        if self.state.telegram_send_in_flight:
            return
        if self.state.plan_request_in_flight:
            self.view.show_status(
                "Wait for the study plan to finish before sending.",
                is_error=True,
            )
            return
        mode, start, end = self.view.current_range()
        brief_type = (
            "today"
            if mode == "today"
            else "weekly"
            if mode == "7days"
            else "range"
        )
        self.state.telegram_send_in_flight = True
        self.view.set_telegram_sending(True)
        self.view.set_busy(True)
        QApplication.processEvents()
        try:
            brief_text = self.state.brief_text.strip() or None
            plan = self.state.brief_plan or self.view.current_brief_plan()
            if not brief_text and not plan:
                self.view.show_status(
                    "Create a study plan before sending to Telegram.",
                    is_error=True,
                )
                return

            result = self.client.send_brief_to_telegram(
                user_id,
                brief_type=brief_type,
                brief_text=brief_text,
                start_date=start,
                end_date=end,
                plan=plan if isinstance(plan, dict) else None,
            )
            message = result.get("message") or "Study plan sent to Telegram."
            self.view.show_status(message)
        except Exception as err:
            self.view.show_status(self._friendly_error(err), is_error=True)
        finally:
            self.state.telegram_send_in_flight = False
            self.view.set_telegram_sending(False)
            self.view.set_busy(False)

    def refresh_study_material_status(self) -> None:
        panel = self.view.planner_page.study_materials
        try:
            status = self.client.rag_status()
        except Exception as exc:
            # On failure, show empty — never keep a guessed/placeholder filename.
            logger.warning("rag_status_refresh_failed err=%s", exc)
            panel.clear_documents()
            return
        docs = status.get("documents")
        if isinstance(docs, list) and docs:
            panel.set_documents(docs)
            panel.set_error("")
            return
        # Legacy single-file status fallback.
        file_name = (status.get("file_name") or "").strip()
        if bool(status.get("indexed")) and file_name:
            panel.set_document(
                file_name,
                title=status.get("title"),
                document_id=status.get("document_id"),
            )
            panel.set_error("")
        else:
            panel.clear_documents()

    def remove_study_material(self, document_id: str = "") -> None:
        panel = self.view.planner_page.study_materials
        doc_id = (document_id or "").strip()
        if not doc_id:
            panel.set_error("Could not remove the study material. Please try again.")
            return
        panel.set_busy(True)
        try:
            status = self.client.remove_rag_document(doc_id)
        except Exception as err:
            logger.warning("rag_remove_failed err=%s", type(err).__name__)
            panel.set_busy(False)
            panel.set_error("Could not remove the study material. Please try again.")
            return
        panel.set_busy(False)
        docs = status.get("documents") if isinstance(status, dict) else None
        if isinstance(docs, list):
            panel.set_documents(docs)
        else:
            self.refresh_study_material_status()
        panel.set_error("")
        self.view.show_status("Study material removed")
        # Regenerate so plan reflects remaining material.
        if self.state.brief_plan:
            self._rag_auto_regenerate = False
            self.generate_range_brief(regenerate=True)

    def upload_study_material(self, title: str, file_path: str) -> None:
        if self._rag_thread is not None and self._rag_thread.isRunning():
            panel = self.view.planner_page.study_materials
            panel.set_error("Upload already in progress.")
            return
        panel = self.view.planner_page.study_materials
        panel.set_busy(True)
        panel.set_error("")
        panel.set_status("Uploading study material…")

        thread = QThread(self)
        worker = RagUploadWorker(self.client, title, file_path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_rag_upload_finished)
        worker.failed.connect(self._on_rag_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_rag_thread)
        self._rag_thread = thread
        self._rag_worker = worker
        thread.start()

    @Slot(object)
    def _on_rag_upload_finished(self, result: object) -> None:
        panel = self.view.planner_page.study_materials
        panel.set_busy(False)
        data = result if isinstance(result, dict) else {}
        if not data.get("indexed") or not data.get("document_id"):
            panel.set_error("Could not upload the study material. Please try again.")
            self.refresh_study_material_status()
            return
        file_name = (data.get("file_name") or "").strip()
        if not file_name:
            panel.set_error("Could not upload the study material. Please try again.")
            self.refresh_study_material_status()
            return
        # Refresh full multi-document list from status (upload ADDS, never replaces).
        self.refresh_study_material_status()
        panel.set_error("")
        logger.info(
            "rag_upload_ui_ok document_id=%s file=%s chunks=%s",
            data.get("document_id"),
            file_name,
            data.get("chunk_count"),
        )
        # Auto-regenerate current plan so RAG enrichment appears immediately.
        # Visible plan is replaced only when the new brief response succeeds.
        if self.state.brief_plan:
            self._rag_auto_regenerate = True
            self.generate_range_brief(regenerate=True)
        else:
            self._rag_auto_regenerate = False

    @Slot(object)
    def _on_rag_failed(self, err: object) -> None:
        panel = self.view.planner_page.study_materials
        panel.set_busy(False)
        if isinstance(err, BackendApiError):
            logger.error(
                "rag_upload_ui_failed status=%s code=%s detail=%s",
                err.status_code,
                err.code,
                err.detail or err.message,
            )
            panel.set_error(
                self._friendly_rag_error(err.message, err.code, err.status_code)
            )
            return
        message = str(err or "")
        logger.error("rag_upload_ui_failed message=%s", message)
        panel.set_error(self._friendly_rag_error(message, "", None))

    def _clear_rag_thread(self) -> None:
        self._rag_thread = None
        self._rag_worker = None

    @staticmethod
    def _friendly_rag_error(
        message: str,
        code: str = "",
        status_code: int | None = None,
    ) -> str:
        lowered = (message or "").lower()
        code = (code or "").lower()
        if code == "embedding_not_configured" or "nomic-embed" in lowered or (
            "embedding model" in lowered and ("not available" in lowered or "not configured" in lowered)
        ):
            return "The local embedding model is not available."
        if status_code == 404 or lowered.strip() in {"not found", "404"}:
            return "Could not upload the study material. Please try again."
        if status_code in {500, 502, 503} or code in {
            "index_failed",
            "pdf_load_failed",
            "llm_unavailable",
        }:
            return "Could not upload the study material. Please try again."
        if "connection" in lowered or code == "connection_error":
            return "Could not upload the study material. Please try again."
        return "Could not upload the study material. Please try again."

    @staticmethod
    def _friendly_error(err: Exception) -> str:
        if isinstance(err, BackendApiError):
            return DashboardPresenter._friendly_error_message(err.message, err.code)
        return DashboardPresenter._friendly_error_message(str(err), "")

    @staticmethod
    def _friendly_error_message(message: str, code: str = "") -> str:
        for prefix in (
            "API Error (404): ",
            "API Error (400): ",
            "API Error (409): ",
            "API Error (422): ",
            "API Error (502): ",
            "API Error (500): ",
            "Connection Error: ",
        ):
            if message.startswith(prefix):
                message = message[len(prefix) :]
        lowered = (message or "").lower()
        code = (code or "").lower()
        if code == "calendar_not_synced" or "calendar data is not available" in lowered:
            return "Calendar data is not available yet. Please sync Google Calendar first."
        if code == "no_events_in_range" or "no events were found in the selected" in lowered:
            return "No events were found in the selected date range. Choose another range."
        if code == "timeout" or "timed out" in lowered:
            return "The study plan request timed out before the server responded."
        if "normalization" in lowered:
            return "The schedule-normalization step failed."
        if "not connected" in lowered:
            return "Google Calendar is not connected yet."
        if "no events" in lowered:
            return "No events were found in the selected date range. Choose another range."
        if "telegram bot token is missing" in lowered:
            return "Telegram is not configured yet."
        if "telegram chat id is missing" in lowered:
            return "Telegram chat is not set up yet."
        if "failed to establish" in lowered or "connection refused" in lowered:
            return "Cannot reach the server. Start the backend first."
        if "malformed" in lowered or "invalid response" in lowered:
            return "The server returned an invalid response."
        # Prefer first line of readable backend message
        return (message or "Something went wrong.").split("\n")[0][:200]
