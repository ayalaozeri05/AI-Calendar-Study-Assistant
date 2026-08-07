"""Upload API + OpenAPI registration for planner-integrated RAG."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.main import app
from app.rag.document_loader import LoadedPage
from app.rag.embedding_service import EmbeddingService
from app.rag.rag_service import RagService
from app.rag.retriever import Retriever
from app.rag.vector_store import VectorStore


class FakeEmbedder(EmbeddingService):
    def __init__(self) -> None:
        pass

    def ensure_ready(self) -> None:
        return None

    def embed(self, text: str) -> list[float]:
        # Stable tiny vector from text length / chars.
        base = [float((ord(c) % 13)) for c in (text or "x")[:16]]
        while len(base) < 16:
            base.append(0.0)
        return base[:16]


class FakeLLM:
    def invoke(self, prompt: str, **kwargs) -> str:
        return "ok"


def _write_text_pdf(path: Path, lines: list[str]) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    commands = ["BT", "/F1 12 Tf", "50 720 Td"]
    for i, line in enumerate(lines):
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if i > 0:
            commands.append("0 -16 Td")
        commands.append(f"({safe}) Tj")
    commands.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("latin-1", errors="replace"))
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = stream
    with path.open("wb") as fh:
        writer.write(fh)


@pytest.fixture
def rag_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    chroma = tmp_path / "chroma"
    uploads = tmp_path / "uploads"
    chroma.mkdir()
    uploads.mkdir()
    from app.config import Settings

    cfg = Settings(chroma_persist_dir=str(chroma), rag_upload_dir=str(uploads))
    store = VectorStore(cfg, persist_path=str(chroma))
    embedder = FakeEmbedder()
    service = RagService(
        cfg,
        vector_store=store,
        embedding_service=embedder,
        retriever=Retriever(store, embedder, top_k=4),
        llm=FakeLLM(),  # type: ignore[arg-type]
    )

    from app.api import rag as rag_api
    from app.rag import rag_service as rag_mod
    from app.rag.document_loader import load_pdf_pages

    monkeypatch.setattr(rag_api, "RagService", lambda: service)

    def _safe_load(path):
        try:
            pages = load_pdf_pages(path)
            if pages:
                return pages
        except Exception:
            pass
        return [
            LoadedPage(
                page_number=1,
                text="Processes Threads Synchronization Deadlocks operating systems.",
            )
        ]

    monkeypatch.setattr(rag_mod, "load_pdf_pages", _safe_load)
    return TestClient(app), service, tmp_path


def test_openapi_lists_rag_routes_without_duplicate_prefix():
    paths = app.openapi()["paths"]
    assert "/rag/upload" in paths
    assert "/rag/ask" in paths
    assert "/rag/status" in paths
    assert "/rag/rag/upload" not in paths
    assert "post" in paths["/rag/upload"]
    assert "get" in paths["/rag/status"]


def test_multipart_upload_succeeds_and_status_restores(rag_client):
    client, _service, tmp_path = rag_client
    pdf_path = tmp_path / "OperatingSystems.pdf"
    _write_text_pdf(
        pdf_path,
        ["Processes and Threads", "Synchronization and Deadlocks"],
    )
    with pdf_path.open("rb") as fh:
        resp = client.post(
            "/rag/upload",
            data={"title": "Operating Systems"},
            files={"file": ("OperatingSystems.pdf", fh, "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["indexed"] is True
    assert body["document_id"]
    assert body["title"] == "Operating Systems"
    assert body["chunk_count"] >= 1
    assert body["file_name"] == "OperatingSystems.pdf"

    status = client.get("/rag/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["has_document"] is True
    assert payload["indexed"] is True
    assert payload["file_name"] == "OperatingSystems.pdf"
    assert isinstance(payload.get("documents"), list)
    assert len(payload["documents"]) == 1
    assert payload["documents"][0]["file_name"] == "OperatingSystems.pdf"
