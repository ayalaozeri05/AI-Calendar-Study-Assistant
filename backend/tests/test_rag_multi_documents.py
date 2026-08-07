"""Multi-document RAG: add, status list, selective remove, multi-match retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.rag.document_matcher import score_all_documents
from app.rag.embedding_service import EmbeddingService
from app.rag.rag_service import DocumentRecord, RagService
from app.rag.retriever import Retriever
from app.rag.text_splitter import TextChunk
from app.rag.vector_store import VectorStore
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.ai_recommendation_service import AiRecommendationService


class FakeEmbedder(EmbeddingService):
    def __init__(self) -> None:
        pass

    def ensure_ready(self) -> None:
        return None

    def embed(self, text: str) -> list[float]:
        t = (text or "").lower()
        return [
            1.0 if "deadlock" in t or "operating" in t or "os" in t else 0.0,
            1.0 if "algorithm" in t or "sort" in t else 0.0,
            0.25,
            0.1,
        ]


def _service(tmp_path: Path) -> RagService:
    chroma = tmp_path / "chroma"
    uploads = tmp_path / "uploads"
    chroma.mkdir()
    uploads.mkdir()
    cfg = Settings(chroma_persist_dir=str(chroma), rag_upload_dir=str(uploads))
    store = VectorStore(cfg, persist_path=str(chroma))
    embedder = FakeEmbedder()
    return RagService(
        cfg,
        vector_store=store,
        embedding_service=embedder,
        retriever=Retriever(store, embedder),
        llm=object(),  # type: ignore[arg-type]
    )


def _index(
    service: RagService,
    *,
    document_id: str,
    title: str,
    file_name: str,
    text: str,
) -> DocumentRecord:
    store = service._store
    embedder = service._embeddings
    chunk = TextChunk(text=text, page=1, chunk_number=1)
    store.add_document_chunks(
        document_id=document_id,
        title=title,
        chunks=[chunk],
        embeddings=[embedder.embed(chunk.text)],
    )
    path = Path(service._upload_root) / f"{document_id}.pdf"
    path.write_bytes(b"%PDF-1.4")
    record = DocumentRecord(
        document_id=document_id,
        title=title,
        file_name=file_name,
        file_path=str(path),
        chunk_count=1,
        created_at="t",
    )
    service._save_record(record)
    return record


def test_upload_adds_without_replacing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service = _service(tmp_path)
    from app.rag import rag_service as rag_mod
    from app.rag.document_loader import LoadedPage

    pages = {"n": 0}

    def _load(_path):
        pages["n"] += 1
        text = (
            "Deadlocks and Virtual Memory"
            if pages["n"] == 1
            else "Sorting and Graph Algorithms"
        )
        return [LoadedPage(page_number=1, text=text)]

    monkeypatch.setattr(rag_mod, "load_pdf_pages", _load)
    a = service.upload_pdf(
        title="Operating Systems",
        filename="OperatingSystems.pdf",
        content=b"%PDF-1.4 fake-a",
    )
    b = service.upload_pdf(
        title="Algorithms",
        filename="Algorithms.pdf",
        content=b"%PDF-1.4 fake-b",
    )
    docs = service.list_indexed_documents()
    ids = {d.document_id for d in docs}
    names = {d.file_name for d in docs}
    assert a.document_id in ids
    assert b.document_id in ids
    assert names == {"OperatingSystems.pdf", "Algorithms.pdf"}
    assert a.document_id != b.document_id


def test_status_returns_all_documents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service = _service(tmp_path)
    _index(
        service,
        document_id="os",
        title="Operating Systems",
        file_name="OperatingSystems.pdf",
        text="Deadlocks Virtual Memory Paging",
    )
    _index(
        service,
        document_id="algo",
        title="Algorithms",
        file_name="Algorithms.pdf",
        text="Sorting graphs dynamic programming",
    )
    monkeypatch.setattr("app.api.rag.RagService", lambda: service)
    client = TestClient(app)
    status = client.get("/rag/status").json()
    assert status["has_document"] is True
    assert len(status["documents"]) == 2
    names = {d["file_name"] for d in status["documents"]}
    assert names == {"OperatingSystems.pdf", "Algorithms.pdf"}


def test_remove_one_keeps_other(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service = _service(tmp_path)
    _index(
        service,
        document_id="os",
        title="Operating Systems",
        file_name="OperatingSystems.pdf",
        text="Deadlocks",
    )
    _index(
        service,
        document_id="algo",
        title="Algorithms",
        file_name="Algorithms.pdf",
        text="Sorting",
    )
    monkeypatch.setattr("app.api.rag.RagService", lambda: service)
    client = TestClient(app)
    resp = client.delete("/rag/documents/os")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["documents"]) == 1
    assert body["documents"][0]["document_id"] == "algo"
    assert service.list_indexed_documents()[0].document_id == "algo"


def test_event_retrieves_from_matching_document_only(tmp_path: Path):
    service = _service(tmp_path)
    _index(
        service,
        document_id="os",
        title="Operating Systems",
        file_name="OperatingSystems.pdf",
        text="Deadlocks Virtual Memory Paging Scheduling Threads",
    )
    _index(
        service,
        document_id="algo",
        title="Algorithms",
        file_name="Algorithms.pdf",
        text="QuickSort Dijkstra dynamic programming",
    )
    events = [
        ClassifiedCalendarEvent(
            id="e-os",
            title="Operating Systems Exam",
            category=EventCategory.EXAM,
            start=datetime.now(timezone.utc) + timedelta(days=3),
            end=datetime.now(timezone.utc) + timedelta(days=3, hours=2),
        )
    ]
    topics = service.topics_for_events(events)
    assert topics
    joined = " ".join(topics.get("e-os") or []).lower()
    assert "deadlock" in joined or "paging" in joined or "thread" in joined
    assert "quicksort" not in joined
    assert "OperatingSystems.pdf" in service.last_matched_documents
    assert "Algorithms.pdf" not in service.last_matched_documents


def test_multiple_relevant_pdfs_can_contribute(tmp_path: Path):
    service = _service(tmp_path)
    _index(
        service,
        document_id="os1",
        title="Operating Systems",
        file_name="OperatingSystems.pdf",
        text="Deadlocks and Synchronization",
    )
    _index(
        service,
        document_id="os2",
        title="OS Exam Review",
        file_name="ExamReview.pdf",
        text="Virtual Memory Paging and Threads in Operating Systems",
    )
    _index(
        service,
        document_id="algo",
        title="Algorithms",
        file_name="Algorithms.pdf",
        text="Heap sort and graph algorithms",
    )
    matches = score_all_documents(
        "Operating Systems Exam",
        service.list_indexed_documents(),
    )
    names = {m.document_name for m in matches}
    assert "OperatingSystems.pdf" in names
    assert "ExamReview.pdf" in names
    assert "Algorithms.pdf" not in names

    topics = service.topics_for_events(
        [
            ClassifiedCalendarEvent(
                id="e1",
                title="Operating Systems Exam",
                category=EventCategory.EXAM,
                start=datetime.now(timezone.utc) + timedelta(days=2),
                end=datetime.now(timezone.utc) + timedelta(days=2, hours=2),
            )
        ]
    )
    assert topics
    assert len(service.last_matched_documents) >= 1


def test_plan_meta_exposes_matched_documents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service = _service(tmp_path)
    _index(
        service,
        document_id="os",
        title="Operating Systems",
        file_name="OperatingSystems.pdf",
        text="Deadlocks Virtual Memory Paging",
    )
    ai = AiRecommendationService(rag=service)
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "ai_polish_enabled", False)
    now = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    plan, _text, _mode, _w = ai.generate_study_plan(
        [
            ClassifiedCalendarEvent(
                id="e1",
                title="Operating Systems Exam",
                category=EventCategory.EXAM,
                start=now + timedelta(days=4),
                end=now + timedelta(days=4, hours=2),
            )
        ],
        start=now.date(),
        end=(now + timedelta(days=1)).date(),
        now=now,
        force_fallback=True,
    )
    assert ai.last_rag_used is True
    assert "OperatingSystems.pdf" in ai.last_rag_matched_documents
    assert ai.last_rag_topics
    assert any(
        any(t.lower() in (item.action or "").lower() for t in ai.last_rag_topics)
        for day in plan.daily_plan
        for item in day.items
        if item.kind == "study"
    )


def _minimal_pdf_bytes(text: str) -> bytes:
    """Tiny valid-enough PDF with extractable text via pypdf loader path.

    For unit tests that call upload_pdf, monkeypatch load_pdf_pages instead
    when full PDF parsing is brittle — here we still index via _index helper.
    """
    # Prefer direct index in most tests; upload_pdf needs loadable pages.
    from io import BytesIO

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 50 720 Td ({safe}) Tj ET".encode("latin-1", "replace"))
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    page[NameObject("/Contents")] = stream
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


@dataclass
class _Evt:
    id: str
    title: str
    category: str
    description: str = ""
