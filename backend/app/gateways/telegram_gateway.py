"""Telegram Bot external-service gateway."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.config import Settings, settings


def _telegram_api_error_message(raw: str) -> str:
    """Extract the exact error description from a Telegram API response body."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip() or "Unknown Telegram API error"

    if not isinstance(data, dict):
        return raw.strip() or "Unknown Telegram API error"

    description = data.get("description")
    if description:
        return str(description)

    if data.get("ok") is False:
        code = data.get("error_code", "unknown")
        return f"Telegram API error {code}"

    return raw.strip() or "Unknown Telegram API error"


class TelegramGateway:
    """Sends messages via the Telegram Bot API."""

    def __init__(self, app_settings: Settings | None = None) -> None:
        self._settings = app_settings or settings

    @property
    def bot_token_configured(self) -> bool:
        return bool(self._settings.telegram_bot_token.strip())

    def send_message(self, chat_id: str, text: str) -> dict:
        token = self._settings.telegram_bot_token.strip()
        if not token:
            raise ValueError("Telegram bot token is missing.")
        if not chat_id:
            raise ValueError("Telegram chat_id is required")

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(_telegram_api_error_message(raw)) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Telegram connection failed: {exc.reason}") from exc

        if not body.get("ok"):
            raise RuntimeError(_telegram_api_error_message(json.dumps(body)))

        return body
