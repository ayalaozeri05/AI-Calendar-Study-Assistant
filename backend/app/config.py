"""Application configuration."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root .env (ai-study-planner/.env) when running from backend/
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # Google Calendar OAuth (Desktop client JSON + per-user tokens)
    google_calendar_credentials_path: str = ""
    # Legacy alias still accepted for compatibility
    google_calendar_credentials_file: str = ""
    google_calendar_token_dir: str = "local_tokens/google_calendar"
    google_calendar_id: str = "primary"

    telegram_bot_token: str = ""
    demo_telegram_chat_id: str = ""

    # Ollama in Docker (optional wording polish / RAG).
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    # Embedding model for RAG (must be pulled: ollama pull nomic-embed-text).
    ollama_embed_model: str = "nomic-embed-text"
    # Total polish budget (availability + invoke + JSON retry). Must stay < desktop 120s.
    ollama_timeout_sec: float = 75.0

    # Stable demo mode: deterministic scheduling only (no Ollama wait).
    # Source of truth for whether polish runs. Default false for reliable demos.
    ai_polish_enabled: bool = False
    # Deprecated diagnostic override. When true, polish is skipped even if
    # AI_POLISH_ENABLED=true. Prefer AI_POLISH_ENABLED=false instead.
    skip_ollama_polish: bool = False

    # RAG storage (project-root relative paths resolved in rag package).
    chroma_persist_dir: str = "backend/chroma"
    rag_upload_dir: str = "backend/uploads/rag"

    @property
    def polish_enabled(self) -> bool:
        """True only when optional Ollama wording polish should run."""
        return bool(self.ai_polish_enabled) and not bool(self.skip_ollama_polish)


settings = Settings()

# Backwards-compatible module-level names
API_HOST = settings.api_host
API_PORT = settings.api_port

logger.info(
    "config_loaded ai_polish_enabled=%s skip_ollama_polish=%s "
    "polish_enabled=%s ollama_timeout_sec=%s ollama_model=%s",
    settings.ai_polish_enabled,
    settings.skip_ollama_polish,
    settings.polish_enabled,
    settings.ollama_timeout_sec,
    settings.ollama_model or "(unset)",
)
