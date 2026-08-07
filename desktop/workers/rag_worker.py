"""Background worker for study-material PDF upload."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from api_client.backend_client import BackendApiError, BackendClient

logger = logging.getLogger(__name__)


class RagUploadWorker(QObject):
    finished = Signal(object)
    failed = Signal(object)

    def __init__(self, client: BackendClient, title: str, file_path: str) -> None:
        super().__init__()
        self._client = client
        self._title = title
        self._file_path = file_path

    def run(self) -> None:
        try:
            path = Path(self._file_path)
            result = self._client.upload_rag_pdf(self._title, path)
            self.finished.emit(result)
        except BackendApiError as exc:
            logger.error(
                "rag_upload_worker_failed status=%s code=%s message=%s",
                exc.status_code,
                exc.code,
                exc.message,
            )
            self.failed.emit(exc)
        except Exception as exc:
            logger.exception("rag_upload_worker_failed")
            self.failed.emit(exc)
