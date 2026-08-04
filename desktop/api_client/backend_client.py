"""HTTP client for the FastAPI backend. Desktop talks only to FastAPI."""

from __future__ import annotations

from typing import Any

import requests


class BackendClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def _handle_response(self, response: requests.Response) -> Any:
        try:
            response.raise_for_status()
            if not response.content:
                return None
            return response.json()
        except requests.HTTPError as err:
            try:
                detail = response.json().get("detail", str(err))
            except ValueError:
                detail = response.text or str(err)
            raise RuntimeError(f"API Error ({response.status_code}): {detail}") from err
        except requests.RequestException as err:
            raise RuntimeError(f"Connection Error: {err}") from err

    def create_demo_user(self) -> dict:
        response = requests.post(f"{self.base_url}/users/demo", timeout=15)
        return self._handle_response(response)

    def sync_calendar(self, user_id: str) -> dict:
        response = requests.post(
            f"{self.base_url}/calendar/sync",
            json={"user_id": user_id},
            timeout=30,
        )
        return self._handle_response(response)

    def get_today_events(self, user_id: str) -> dict:
        response = requests.get(
            f"{self.base_url}/calendar/events/today",
            params={"user_id": user_id},
            timeout=15,
        )
        return self._handle_response(response)

    def generate_today_brief(self, user_id: str) -> dict:
        response = requests.post(
            f"{self.base_url}/briefs/today",
            json={"user_id": user_id},
            timeout=30,
        )
        return self._handle_response(response)

    def generate_weekly_brief(self, user_id: str) -> dict:
        response = requests.post(
            f"{self.base_url}/briefs/weekly",
            json={"user_id": user_id},
            timeout=30,
        )
        return self._handle_response(response)

    def send_brief_to_telegram(
        self,
        user_id: str,
        brief_type: str = "today",
        brief_text: str | None = None,
    ) -> dict:
        payload: dict[str, str] = {
            "user_id": user_id,
            "brief_type": brief_type,
        }
        if brief_text:
            payload["brief_text"] = brief_text
        response = requests.post(
            f"{self.base_url}/briefs/send-telegram",
            json=payload,
            timeout=30,
        )
        return self._handle_response(response)
