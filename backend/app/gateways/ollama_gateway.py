"""Ollama gateway — local LLM via LangChain. No UI / Supabase."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings, settings

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Readable Ollama / model error for service-layer fallbacks."""


class OllamaGateway:
    """Connects to a local Ollama server and invokes a chat model."""

    def __init__(self, app_settings: Settings | None = None) -> None:
        self._settings = app_settings or settings

    @property
    def base_url(self) -> str:
        return (self._settings.ollama_base_url or "http://localhost:11434").rstrip("/")

    @property
    def model(self) -> str:
        return (self._settings.ollama_model or "").strip()

    def is_available(self) -> bool:
        """Return True when Ollama responds and the configured model exists."""
        if not self.model:
            return False
        try:
            models = self.list_models()
            return self.model in models
        except OllamaError:
            return False

    def list_models(self) -> list[str]:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise OllamaError(
                f"Ollama is not reachable at {self.base_url}. "
                "Start Ollama and pull a model first."
            ) from exc

        names: list[str] = []
        for item in payload.get("models") or []:
            name = (item.get("name") or item.get("model") or "").strip()
            if name:
                names.append(name)
                # Also accept bare tags without :latest
                if ":" in name:
                    names.append(name.split(":", 1)[0])
        return names

    def ensure_ready(self) -> None:
        if not self.model:
            raise OllamaError(
                "OLLAMA_MODEL is not configured. Set it in .env (for example: llama3.2)."
            )
        models = self.list_models()
        if self.model not in models and f"{self.model}:latest" not in models:
            raise OllamaError(
                f"Ollama model '{self.model}' is not available. "
                f"Run: ollama pull {self.model}"
            )

    def invoke(self, prompt: str, *, temperature: float = 0.2) -> str:
        """Invoke the configured model through LangChain and return text."""
        self.ensure_ready()
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise OllamaError(
                "LangChain Ollama packages are missing. "
                "Install langchain and langchain-ollama."
            ) from exc

        model_name = self.model
        llm = ChatOllama(
            model=model_name,
            base_url=self.base_url,
            temperature=temperature,
        )
        messages = [
            SystemMessage(
                content=(
                    "You are a careful academic study planner. "
                    "Follow instructions exactly. Prefer valid JSON when asked."
                )
            ),
            HumanMessage(content=prompt),
        ]
        try:
            result: Any = llm.invoke(messages)
        except Exception as exc:
            raise OllamaError(
                f"Ollama model invocation failed ({model_name}): {exc}"
            ) from exc

        text = getattr(result, "content", None)
        if text is None:
            text = str(result)
        if isinstance(text, list):
            # Some chat models return content blocks
            parts = []
            for block in text:
                if isinstance(block, dict) and "text" in block:
                    parts.append(str(block["text"]))
                else:
                    parts.append(str(block))
            text = "\n".join(parts)
        cleaned = str(text).strip()
        if not cleaned:
            raise OllamaError("Ollama returned an empty response.")
        logger.info("ollama_invoke ok model=%s chars=%s", model_name, len(cleaned))
        return cleaned

