"""Study Materials multi-file card placement and client URLs."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DESKTOP = Path(__file__).resolve().parents[1]
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))

from PySide6.QtWidgets import QApplication, QVBoxLayout

from api_client.backend_client import BackendClient
from pages.planner_page import PlannerPage
from presenters.dashboard_presenter import DashboardPresenter
from widgets.study_materials_panel import StudyMaterialsPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_desktop_upload_calls_exact_rag_upload_url(tmp_path: Path):
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    client = BackendClient("http://127.0.0.1:8000")
    with patch("api_client.backend_client.requests.post") as post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"document_id":"x","title":"notes","file_name":"notes.pdf","chunk_count":1,"indexed":true,"created_at":"t"}'
        mock_resp.json.return_value = {
            "document_id": "x",
            "title": "notes",
            "file_name": "notes.pdf",
            "chunk_count": 1,
            "indexed": True,
            "created_at": "t",
        }
        mock_resp.raise_for_status = MagicMock()
        post.return_value = mock_resp
        client.upload_rag_pdf("notes", pdf)
        assert post.call_args.args[0] == "http://127.0.0.1:8000/rag/upload"


def test_remove_calls_documents_path():
    client = BackendClient("http://127.0.0.1:8000")
    with patch("api_client.backend_client.requests.delete") as delete:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"documents":[],"has_document":false,"indexed":false}'
        mock_resp.json.return_value = {
            "documents": [],
            "has_document": False,
            "indexed": False,
        }
        mock_resp.raise_for_status = MagicMock()
        delete.return_value = mock_resp
        client.remove_rag_document("abc-123")
        assert delete.call_args.args[0] == "http://127.0.0.1:8000/rag/documents/abc-123"


def test_upload_failure_does_not_show_raw_not_found():
    msg = DashboardPresenter._friendly_rag_error("Not Found", "", 404)
    assert msg == "Could not upload the study material. Please try again."


def test_study_material_is_in_right_column_below_brief(qapp):
    page = PlannerPage()
    right_layout = page.right_host.layout()
    assert isinstance(right_layout, QVBoxLayout)

    widgets = []
    for i in range(right_layout.count()):
        item = right_layout.itemAt(i)
        w = item.widget() if item is not None else None
        if w is not None:
            widgets.append(w)

    assert page.brief in widgets
    assert page.study_materials in widgets
    assert widgets.index(page.brief) < widgets.index(page.study_materials)
    assert page.brief.minimumHeight() >= 400
    assert page.study_materials.maximumHeight() <= 140


def test_initial_state_has_no_placeholder_filename(qapp):
    panel = StudyMaterialsPanel()
    panel.show()
    assert panel.helper.text() == "No study material uploaded"
    assert panel.btn_upload.text() == "+ Add PDF"
    assert panel.documents == []


def test_multi_document_list_and_per_file_remove(qapp):
    panel = StudyMaterialsPanel()
    panel.show()
    panel.set_documents(
        [
            {
                "document_id": "a",
                "file_name": "OperatingSystems.pdf",
                "title": "OS",
                "indexed": True,
            },
            {
                "document_id": "b",
                "file_name": "Algorithms.pdf",
                "title": "Algo",
                "indexed": True,
            },
        ]
    )
    assert len(panel.documents) == 2
    assert "Study Materials (2)" in panel.heading.text()
    assert panel.btn_upload.text() == "+ Add PDF"
    assert "Replace" not in panel.btn_upload.text()
    removed: list[str] = []
    panel.remove_requested.connect(removed.append)
    # Click first row Remove
    rows = []
    for i in range(panel.list_layout.count()):
        item = panel.list_layout.itemAt(i)
        w = item.widget() if item is not None else None
        if w is not None:
            rows.append(w)
    assert len(rows) >= 2
    from PySide6.QtWidgets import QPushButton

    btn = rows[0].findChild(QPushButton)
    assert btn is not None
    btn.click()
    assert removed == ["a"]


def test_study_material_stays_compact(qapp):
    panel = StudyMaterialsPanel()
    panel.set_documents(
        [{"document_id": "1", "file_name": "מערכות הפעלה.pdf", "indexed": True}]
    )
    assert 70 <= panel.height() <= 95
    assert panel.maximumHeight() <= 140

    panel.set_documents(
        [
            {"document_id": "1", "file_name": "a.pdf", "indexed": True},
            {"document_id": "2", "file_name": "b.pdf", "indexed": True},
            {"document_id": "3", "file_name": "c.pdf", "indexed": True},
        ]
    )
    assert panel.height() <= 140
    # Remove stays a small secondary control.
    from PySide6.QtWidgets import QPushButton

    row = panel.list_layout.itemAt(0).widget()
    btn = row.findChild(QPushButton)
    assert btn is not None
    assert btn.objectName() == "ragRemoveButton"
    assert btn.height() <= 32
