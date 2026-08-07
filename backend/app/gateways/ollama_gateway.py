"""Ollama gateway — local LLM. Uses hard httpx timeouts (cancellable)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, settings

logger = logging.getLogger(__name__)

# Project root / logs (ai-study-planner/logs)
_LOGS_DIR = Path(__file__).resolve().parents[3] / "logs"
_LAST_RESPONSE_PATH = _LOGS_DIR / "ollama_last_response.txt"


class OllamaError(Exception):
    """Readable Ollama / model error for service-layer fallbacks."""

    def __init__(self, message: str, *, reason: str = "http_error") -> None:
        super().__init__(message)
        self.reason = reason


class OllamaTimeoutError(OllamaError):
    """Model call exceeded the configured timeout."""

    def __init__(self, message: str, *, reason: str = "timeout") -> None:
        super().__init__(message, reason=reason)


def save_raw_ollama_response(raw: str, *, note: str = "") -> Path:
    """Persist last Ollama text for offline inspection."""
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    header = f"# note={note}\n# chars={len(raw or '')}\n\n"
    _LAST_RESPONSE_PATH.write_text(header + (raw or ""), encoding="utf-8")
    logger.info("saved_raw_ollama_response path=%s chars=%s", _LAST_RESPONSE_PATH, len(raw or ""))
    return _LAST_RESPONSE_PATH


class OllamaGateway:
    """Connects to a local Ollama server.

    Invoke uses Ollama's HTTP /api/chat with hard httpx timeouts so a stuck
    model cannot block the FastAPI request past the configured bound.

    Note: wrapping ChatOllama in ``with ThreadPoolExecutor()`` is unsafe —
    after ``future.result(timeout=…)`` raises, the context manager's
    ``shutdown(wait=True)`` waits for the stuck worker and defeats the timeout.
    """

    def __init__(self, app_settings: Settings | None = None) -> None:
        self._settings = app_settings or settings

    @property
    def base_url(self) -> str:
        return (self._settings.ollama_base_url or "http://localhost:11434").rstrip("/")

    @property
    def model(self) -> str:
        return (self._settings.ollama_model or "").strip()

    @property
    def timeout_sec(self) -> float:
        return float(getattr(self._settings, "ollama_timeout_sec", 75.0) or 75.0)

    def is_available(self) -> bool:
        """Return True when Ollama responds and the configured model exists."""
        if not self.model:
            return False
        try:
            models = self.list_models()
            return self.model in models or f"{self.model}:latest" in models
        except OllamaError:
            return False

    def list_models(self) -> list[str]:
        try:
            response = httpx.get(
                f"{self.base_url}/api/tags",
                timeout=httpx.Timeout(connect=3.0, read=3.0, write=3.0, pool=3.0),
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise OllamaError(
                f"Ollama is not reachable at {self.base_url}. "
                "Start Ollama and pull a model first.",
                reason="connection_failure",
            ) from exc

        names: list[str] = []
        for item in payload.get("models") or []:
            name = (item.get("name") or item.get("model") or "").strip()
            if name:
                names.append(name)
                if ":" in name:
                    names.append(name.split(":", 1)[0])
        return names

    def ensure_ready(self) -> None:
        if not self.model:
            raise OllamaError(
                "OLLAMA_MODEL is not configured. Set it in .env (for example: llama3.2).",
                reason="model_not_configured",
            )
        models = self.list_models()
        if self.model not in models and f"{self.model}:latest" not in models:
            raise OllamaError(
                f"Ollama model '{self.model}' is not available. "
                f"Run: ollama pull {self.model}",
                reason="model_missing",
            )

    @property
    def embed_model(self) -> str:
        return (getattr(self._settings, "ollama_embed_model", None) or "nomic-embed-text").strip()

    def ensure_embed_model_ready(self) -> None:
        """Require the configured embedding model to be present in Ollama."""
        model_name = self.embed_model
        if not model_name:
            raise OllamaError(
                "OLLAMA_EMBED_MODEL is not configured. "
                "Set it in .env (for example: nomic-embed-text).",
                reason="model_not_configured",
            )
        models = self.list_models()
        if model_name not in models and f"{model_name}:latest" not in models:
            raise OllamaError(
                f"Ollama embedding model '{model_name}' is not available. "
                f"Run: ollama pull {model_name}",
                reason="model_missing",
            )

    def embed(self, text: str, *, timeout_sec: float = 60.0) -> list[float]:
        """Create an embedding vector via Ollama /api/embeddings."""
        self.ensure_embed_model_ready()
        model_name = self.embed_model
        endpoint = f"{self.base_url}/api/embeddings"
        timeout = httpx.Timeout(
            connect=5.0,
            read=max(1.0, float(timeout_sec)),
            write=10.0,
            pool=5.0,
        )
        payload = {"model": model_name, "prompt": text or ""}
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Ollama embedding timed out ({model_name}).",
                reason="timeout",
            ) from exc
        except Exception as exc:
            raise OllamaError(
                f"Ollama embedding failed ({model_name}): {exc}",
                reason="http_error",
            ) from exc

        vector = data.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise OllamaError(
                "Ollama returned an empty embedding.",
                reason="unexpected_response_format",
            )
        return [float(x) for x in vector]

    def invoke(
        self,
        prompt: str,
        *,
        temperature: float = 0.2,
        timeout_sec: float | None = None,
        max_tokens: int | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Invoke the model via Ollama /api/chat with a hard read timeout."""
        self.ensure_ready()
        model_name = self.model
        endpoint = f"{self.base_url}/api/chat"
        # Allow sub-5s bounds for leftover budget / tests; floor at 1s.
        bound = max(1.0, float(timeout_sec if timeout_sec is not None else self.timeout_sec))
        timeout = httpx.Timeout(
            connect=5.0,
            read=bound,
            write=10.0,
            pool=5.0,
        )
        options: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = int(max_tokens)

        system_content = system_prompt or (
            "You are a careful academic study planner. "
            "Follow instructions exactly. Prefer valid JSON when asked."
        )
        payload: dict[str, Any] = {
            "model": model_name,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            "options": options,
        }
        prompt_chars = len(prompt or "")
        # Rough token estimate for audit logs only (not sent to Ollama).
        prompt_tokens_est = max(1, prompt_chars // 4)

        logger.info(
            "stage=ollama_request model=%s endpoint=%s prompt_chars=%s "
            "prompt_tokens_est=%s timeout_sec=%.1f temperature=%s max_tokens=%s",
            model_name,
            endpoint,
            prompt_chars,
            prompt_tokens_est,
            bound,
            temperature,
            max_tokens if max_tokens is not None else "unset",
        )

        t0 = time.perf_counter()
        http_status: int | None = None
        raw_body_preview = ""
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(endpoint, json=payload)
                http_status = response.status_code
                raw_body_preview = (response.text or "")[:500]
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            elapsed = time.perf_counter() - t0
            logger.warning(
                "stage=ollama_response answered=false http_status=%s elapsed_sec=%.3f "
                "exception=%s fallback_reason=timeout ollama_timeout_after=%.1f model=%s",
                http_status,
                elapsed,
                type(exc).__name__,
                bound,
                model_name,
            )
            raise OllamaTimeoutError(
                f"Ollama model timed out after {bound:.0f}s ({model_name}).",
                reason="timeout",
            ) from exc
        except httpx.HTTPStatusError as exc:
            elapsed = time.perf_counter() - t0
            status = exc.response.status_code if exc.response is not None else http_status
            logger.warning(
                "stage=ollama_response answered=false http_status=%s elapsed_sec=%.3f "
                "exception=HTTPStatusError fallback_reason=http_error body_preview=%r",
                status,
                elapsed,
                raw_body_preview[:200],
            )
            raise OllamaError(
                f"Ollama HTTP {status} ({model_name}): {exc}",
                reason="http_error",
            ) from exc
        except httpx.RequestError as exc:
            elapsed = time.perf_counter() - t0
            logger.warning(
                "stage=ollama_response answered=false http_status=%s elapsed_sec=%.3f "
                "exception=%s fallback_reason=connection_failure detail=%s",
                http_status,
                elapsed,
                type(exc).__name__,
                exc,
            )
            raise OllamaError(
                f"Ollama connection failed ({model_name}): {exc}",
                reason="connection_failure",
            ) from exc
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            logger.warning(
                "stage=ollama_response answered=false http_status=%s elapsed_sec=%.3f "
                "exception=%s fallback_reason=unexpected_response_format detail=%s",
                http_status,
                elapsed,
                type(exc).__name__,
                exc,
            )
            raise OllamaError(
                f"Ollama model invocation failed ({model_name}): {exc}",
                reason="unexpected_response_format",
            ) from exc

        elapsed = time.perf_counter() - t0
        message = data.get("message") or {}
        cleaned = str(message.get("content") or "").strip()
        if not cleaned:
            cleaned = str(data.get("response") or "").strip()

        logger.info(
            "stage=ollama_response answered=%s http_status=%s elapsed_sec=%.3f "
            "response_chars=%s model=%s",
            bool(cleaned),
            http_status,
            elapsed,
            len(cleaned),
            model_name,
        )

        if not cleaned:
            raise OllamaError(
                "Ollama returned an empty response.",
                reason="unexpected_response_format",
            )
        return cleaned
