"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root .env (ai-study-planner/.env) when running from backend/
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"


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

    # Local Ollama (optional — falls back to rule-based planner when unavailable)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""


settings = Settings()

# Backwards-compatible module-level names
API_HOST = settings.api_host
API_PORT = settings.api_port
