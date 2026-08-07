"""Compact multi-file Study Materials card under Study Plan."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class StudyMaterialsPanel(QFrame):
    """Dense multi-document list: Add PDF + per-file Remove."""

    upload_requested = Signal(str, str)  # title, file_path
    remove_requested = Signal(str)  # document_id

    _ROW_H = 26
    _EMPTY_H = 72
    _MAX_H = 140

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("studyMaterialCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.setMinimumHeight(0)
        self.setMaximumHeight(self._MAX_H)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        self.heading = QLabel("Study Materials")
        self.heading.setObjectName("cardTitle")
        self.heading.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.heading)

        self.helper = QLabel("No study material uploaded")
        self.helper.setObjectName("mutedLabel")
        self.helper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.helper)

        self.list_host = QWidget()
        self.list_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(1)
        self.list_host.hide()
        layout.addWidget(self.list_host, 0)

        self.error_label = QLabel("")
        self.error_label.setObjectName("mutedLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)
        self.btn_upload = QPushButton("+ Add PDF")
        self.btn_upload.setObjectName("ragAddButton")
        self.btn_upload.setCursor(Qt.PointingHandCursor)
        self.btn_upload.setFixedHeight(28)
        self.btn_upload.clicked.connect(self._on_upload)
        actions.addWidget(self.btn_upload, 0, Qt.AlignLeft)
        actions.addStretch(1)
        layout.addLayout(actions)

        self._documents: list[dict] = []
        self._busy = False
        self.clear_documents()

    def _fit_height(self) -> None:
        count = len(self._documents)
        self.heading.setText(
            f"Study Materials ({count})" if count else "Study Materials"
        )
        if not count:
            self.helper.show()
            self.list_host.hide()
            self.setFixedHeight(self._EMPTY_H)
            return
        self.helper.hide()
        self.list_host.show()
        # title(~20) + n rows + add(28) + margins(~14) + spacing
        height = 20 + (count * self._ROW_H) + 28 + 14 + max(0, count) * 1
        height = max(78, min(self._MAX_H, height))
        if count == 1:
            height = min(95, max(78, height))
        self.setFixedHeight(height)

    def _on_upload(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select study PDF",
            "",
            "PDF files (*.pdf)",
        )
        if not path:
            return
        title = Path(path).stem
        self.upload_requested.emit(title, path)

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self.btn_upload.setEnabled(not busy)
        for i in range(self.list_layout.count()):
            item = self.list_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is None:
                continue
            for btn in w.findChildren(QPushButton):
                btn.setEnabled(not busy)

    def set_error(self, text: str) -> None:
        value = (text or "").strip()
        self.error_label.setText(value)
        self.error_label.setVisible(bool(value))
        if value:
            self.setFixedHeight(min(self._MAX_H, self.height() + 18))

    def set_status(self, text: str) -> None:
        value = (text or "").strip()
        if self._documents:
            return
        self.helper.setText(value or "No study material uploaded")
        self.helper.show()

    def clear_documents(self) -> None:
        self._documents = []
        self._clear_rows()
        self.helper.setText("No study material uploaded")
        self.helper.show()
        self.error_label.hide()
        self.error_label.setText("")
        self._fit_height()

    def clear_document(self) -> None:
        self.clear_documents()

    def set_document(
        self,
        file_name: str | None = None,
        *,
        title: str | None = None,
        document_id: str | None = None,
    ) -> None:
        name = ""
        if isinstance(file_name, str):
            name = file_name.strip()
        elif isinstance(title, str):
            name = title.strip()
        if not name:
            self.clear_documents()
            return
        self.set_documents(
            [
                {
                    "document_id": document_id or "",
                    "file_name": name,
                    "title": title or name,
                    "indexed": True,
                }
            ]
        )

    def set_documents(self, documents: list[dict] | None) -> None:
        rows: list[dict] = []
        for raw in documents or []:
            if not isinstance(raw, dict):
                continue
            doc_id = str(raw.get("document_id") or "").strip()
            name = str(raw.get("file_name") or raw.get("title") or "").strip()
            if not doc_id or not name:
                continue
            rows.append(
                {
                    "document_id": doc_id,
                    "file_name": name,
                    "title": str(raw.get("title") or name),
                    "indexed": bool(raw.get("indexed", True)),
                }
            )
        self._documents = rows
        self._rebuild_rows()
        self.error_label.hide()
        self._fit_height()

    def _clear_rows(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()

    def _rebuild_rows(self) -> None:
        self._clear_rows()
        for doc in self._documents:
            row = QWidget()
            row.setFixedHeight(self._ROW_H)
            row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            full_name = doc["file_name"]
            label = QLabel()
            label.setObjectName("ragFileName")
            label.setToolTip(full_name)
            label.setWordWrap(False)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            label.setFixedHeight(self._ROW_H)
            # Elide after layout has a width; use a reasonable default now.
            metrics = QFontMetrics(label.font())
            label.setText(
                metrics.elidedText(full_name, Qt.ElideMiddle, 220)
            )

            btn = QPushButton("Remove")
            btn.setObjectName("ragRemoveButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setMinimumWidth(52)
            btn.setMaximumWidth(64)
            btn.setEnabled(not self._busy)
            doc_id = doc["document_id"]
            btn.clicked.connect(
                lambda _checked=False, d=doc_id: self.remove_requested.emit(d)
            )
            row_layout.addWidget(label, 1)
            row_layout.addWidget(btn, 0, Qt.AlignRight | Qt.AlignVCenter)
            self.list_layout.addWidget(row)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Re-elide filenames to available width.
        avail = max(80, self.width() - 10 - 10 - 64 - 12)
        for i in range(self.list_layout.count()):
            item = self.list_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is None:
                continue
            label = w.findChild(QLabel)
            if label is None:
                continue
            full = label.toolTip() or label.text()
            metrics = QFontMetrics(label.font())
            label.setText(metrics.elidedText(full, Qt.ElideMiddle, avail))

    @property
    def document_id(self) -> str | None:
        if not self._documents:
            return None
        return self._documents[-1].get("document_id")

    @property
    def documents(self) -> list[dict]:
        return list(self._documents)
