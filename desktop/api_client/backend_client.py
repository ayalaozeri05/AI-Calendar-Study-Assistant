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
            timeout=180,
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
