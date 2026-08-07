"""Resolve RAG storage paths relative to the project root."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings, settings

# backend/app/rag/paths.py → project root is parents[3]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def project_root() -> Path:
    return _PROJECT_ROOT


def resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (_PROJECT_ROOT / path).resolve()


def chroma_dir(app_settings: Settings | None = None) -> Path:
    cfg = app_settings or settings
    path = resolve_path(cfg.chroma_persist_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def upload_dir(app_settings: Settings | None = None) -> Path:
    cfg = app_settings or settings
    path = resolve_path(cfg.rag_upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path
