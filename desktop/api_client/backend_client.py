"""HTTP client for the FastAPI backend. Desktop talks only to FastAPI."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Outer HTTP budget: must exceed backend OLLAMA_TIMEOUT_SEC (+ engine work).
# Backend returns a rule-based plan if polish times out — do not sit for 5 minutes.
AI_CONNECT_TIMEOUT_SEC = 10
AI_READ_TIMEOUT_SEC = 120
AI_TIMEOUT = (AI_CONNECT_TIMEOUT_SEC, AI_READ_TIMEOUT_SEC)


class BackendApiError(RuntimeError):
    """Structured API failure for presenters / workers."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str = "",
        detail: dict | str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.detail = detail


class BackendClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def _handle_response(self, response: requests.Response) -> Any:
        try:
            response.raise_for_status()
            if not response.content:
                return None
            try:
                return response.json()
            except ValueError as err:
                raise BackendApiError(
                    "Malformed JSON response from server.",
                    status_code=response.status_code,
                    code="malformed_json",
                ) from err
        except requests.HTTPError as err:
            detail_raw: Any
            try:
                detail_raw = response.json().get("detail", str(err))
            except ValueError:
                detail_raw = response.text or str(err)

            code = ""
            message = str(detail_raw)
            detail_dict: dict | None = None
            if isinstance(detail_raw, dict):
                detail_dict = detail_raw
                message = str(
                    detail_raw.get("message")
                    or detail_raw.get("detail")
                    or detail_raw
                )
                code = str(detail_raw.get("code") or "")
            elif isinstance(detail_raw, list):
                message = str(detail_raw)

            logger.error(
                "backend_http_error status=%s url=%s code=%s detail=%s",
                response.status_code,
                str(getattr(response, "url", "")),
                code or "(none)",
                detail_raw,
            )
            raise BackendApiError(
                message,
                status_code=response.status_code,
                code=code,
                detail=detail_dict if detail_dict is not None else detail_raw,
            ) from err
        except requests.Timeout as err:
            raise BackendApiError(
                "The study plan request timed out before the server responded.",
                code="timeout",
            ) from err
        except requests.RequestException as err:
            raise BackendApiError(
                f"Connection Error: {err}",
                code="connection_error",
            ) from err

    def create_demo_user(self) -> dict:
        response = requests.post(f"{self.base_url}/users/demo", timeout=15)
        return self._handle_response(response)

    def get_calendar_status(self, user_id: str) -> dict:
        response = requests.get(
            f"{self.base_url}/calendar/status",
            params={"user_id": user_id},
            timeout=15,
        )
        return self._handle_response(response)

    def connect_google_calendar(self, user_id: str) -> dict:
        response = requests.post(
            f"{self.base_url}/calendar/connect",
            json={"user_id": user_id},
            timeout=300,
        )
        return self._handle_response(response)

    def sync_google_calendar(self, user_id: str, days_ahead: int = 62) -> dict:
        response = requests.post(
            f"{self.base_url}/calendar/sync",
            json={"user_id": user_id, "days_ahead": days_ahead},
            timeout=90,
        )
        return self._handle_response(response)

    def sync_calendar(self, user_id: str) -> dict:
        return self.sync_google_calendar(user_id, days_ahead=62)

    def get_today_events(self, user_id: str) -> dict:
        response = requests.get(
            f"{self.base_url}/calendar/events/today",
            params={"user_id": user_id},
            timeout=15,
        )
        return self._handle_response(response)

    def get_week_events(self, user_id: str) -> dict:
        response = requests.get(
            f"{self.base_url}/calendar/events/week",
            params={"user_id": user_id},
            timeout=15,
        )
        return self._handle_response(response)

    def get_events_range(self, user_id: str, start_date: str, end_date: str) -> dict:
        response = requests.get(
            f"{self.base_url}/calendar/events/range",
            params={
                "user_id": user_id,
                "start_date": start_date,
                "end_date": end_date,
            },
            timeout=20,
        )
        return self._handle_response(response)

    def generate_today_brief(self, user_id: str) -> dict:
        response = requests.post(
            f"{self.base_url}/briefs/today",
            json={"user_id": user_id},
            timeout=AI_TIMEOUT,
        )
        return self._handle_response(response)

    def generate_weekly_brief(self, user_id: str) -> dict:
        response = requests.post(
            f"{self.base_url}/briefs/weekly",
            json={"user_id": user_id},
            timeout=AI_TIMEOUT,
        )
        return self._handle_response(response)

    def generate_range_brief(
        self,
        user_id: str,
        start_date: str,
        end_date: str,
        label: str | None = None,
        *,
        regenerate: bool = False,
        previous_plan: dict | None = None,
        variation_seed: int | None = None,
        planning_anchor: str | None = None,
    ) -> dict:
        payload: dict = {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "regenerate": regenerate,
        }
        if label:
            payload["label"] = label
        if previous_plan is not None:
            payload["previous_plan"] = previous_plan
        if variation_seed is not None:
            payload["variation_seed"] = variation_seed
        if planning_anchor:
            payload["planning_anchor"] = planning_anchor
        response = requests.post(
            f"{self.base_url}/briefs/range",
            json=payload,
            timeout=AI_TIMEOUT,
        )
        return self._handle_response(response)

    def send_brief_to_telegram(
        self,
        user_id: str,
        brief_type: str = "today",
        brief_text: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        plan: dict | None = None,
    ) -> dict:
        payload: dict = {
            "user_id": user_id,
            "brief_type": brief_type,
        }
        if brief_text:
            payload["brief_text"] = brief_text
        if start_date:
            payload["start_date"] = start_date
        if end_date:
            payload["end_date"] = end_date
        if plan is not None:
            payload["plan"] = plan
        response = requests.post(
            f"{self.base_url}/briefs/send-telegram",
            json=payload,
            timeout=120,
        )
        return self._handle_response(response)

    def health_ollama(self) -> dict:
        response = requests.get(f"{self.base_url}/health/ollama", timeout=10)
        return self._handle_response(response)

    def upload_rag_pdf(self, title: str, file_path: str | Path) -> dict:
        """POST multipart PDF to /rag/upload (fields: title, file)."""
        path = Path(file_path)
        url = f"{self.base_url}/rag/upload"
        logger.info(
            "rag_upload_request url=%s title=%s filename=%s",
            url,
            title,
            path.name,
        )
        with path.open("rb") as handle:
            response = requests.post(
                url,
                data={"title": title},
                files={"file": (path.name, handle, "application/pdf")},
                timeout=180,
            )
        logger.info(
            "rag_upload_response status=%s bytes=%s",
            response.status_code,
            len(response.content or b""),
        )
        return self._handle_response(response)

    def rag_status(self) -> dict:
        url = f"{self.base_url}/rag/status"
        logger.info("rag_status_request url=%s", url)
        response = requests.get(url, timeout=15)
        return self._handle_response(response)

    def remove_rag_document(self, document_id: str) -> dict:
        doc_id = (document_id or "").strip()
        if not doc_id:
            raise BackendApiError("document_id is required", status_code=400, code="document_id_required")
        url = f"{self.base_url}/rag/documents/{doc_id}"
        logger.info("rag_remove_request url=%s document_id=%s", url, doc_id)
        response = requests.delete(url, timeout=30)
        return self._handle_response(response)
