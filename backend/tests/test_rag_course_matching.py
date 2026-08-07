"""Course ↔ document matching and unrelated-PDF isolation."""

from __future__ import annotations

from dataclasses import dataclass

from app.rag.document_matcher import match_document_for_course
from app.rag.rag_service import DocumentRecord, RagService
from app.rag.topic_extractor import extract_topics_from_chunks
from app.rag.vector_store import StoredChunk


def _doc(title: str, file_name: str, document_id: str = "x") -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        title=title,
        file_name=file_name,
        file_path=f"/tmp/{file_name}",
        chunk_count=1,
        created_at="t",
    )


def test_match_operating_systems_exam_to_os_pdf():
    docs = [
        _doc("Operating Systems", "OperatingSystems.pdf", "os"),
        _doc("Java", "Java.pdf", "java"),
        _doc("Networks", "Networks.pdf", "net"),
    ]
    matched = match_document_for_course("Operating Systems Exam", docs)
    assert matched is not None
    assert matched.document_id == "os"


def test_hebrew_os_exam_matches_hebrew_pdf():
    docs = [_doc("מערכות הפעלה", "מערכות הפעלה.pdf", "os")]
    matched = match_document_for_course("מבחן במערכות הפעלה", docs)
    assert matched is not None
    assert matched.document_id == "os"


def test_hebrew_os_exam_matches_english_os_pdf():
    docs = [
        _doc("Operating Systems", "OperatingSystems.pdf", "os"),
        _doc("Java", "Java.pdf", "java"),
    ]
    matched = match_document_for_course("מבחן במערכות הפעלה", docs)
    assert matched is not None
    assert matched.document_id == "os"


def test_hebrew_automata_does_not_match_os_pdf():
    docs = [_doc("מערכות הפעלה", "מערכות הפעלה.pdf", "os")]
    assert match_document_for_course("מבחן באוטומטים", docs) is None


def test_java_assignment_does_not_match_os_pdf():
    docs = [_doc("Operating Systems", "OperatingSystems.pdf", "os")]
    assert match_document_for_course("Java Assignment", docs) is None


def test_java_assignment_matches_java_pdf():
    docs = [
        _doc("Operating Systems", "OperatingSystems.pdf", "os"),
        _doc("Java Programming", "Java.pdf", "java"),
    ]
    matched = match_document_for_course("Java Assignment", docs)
    assert matched is not None
    assert matched.document_id == "java"


def test_topic_extractor_finds_os_concepts():
    chunks = [
        StoredChunk(
            document_id="os",
            title="OS",
            page=1,
            chunk_number=1,
            text=(
                "Deadlocks, Virtual Memory, Process Scheduling, and Paging "
                "are core Operating Systems topics."
            ),
        )
    ]
    topics = extract_topics_from_chunks(chunks, limit=8)
    joined = " ".join(topics).lower()
    assert "deadlock" in joined or "Deadlocks" in topics
    assert any("virtual" in t.lower() or "paging" in t.lower() or "scheduling" in t.lower() for t in topics)


@dataclass
class _Event:
    id: str
    title: str
    category: str
    description: str = ""


def test_topics_for_events_skips_unrelated_document(tmp_path, monkeypatch):
    """Only the matched document is queried — not every uploaded PDF."""
    from app.config import Settings
    from app.rag.embedding_service import EmbeddingService
    from app.rag.retriever import Retriever
    from app.rag.vector_store import VectorStore
    from app.rag.text_splitter import TextChunk

    class FakeEmbedder(EmbeddingService):
        def __init__(self) -> None:
            pass

        def ensure_ready(self) -> None:
            return None

        def embed(self, text: str) -> list[float]:
            return [1.0 if "java" in text.lower() else 0.0, 0.5, 0.25]

    chroma = tmp_path / "chroma"
    uploads = tmp_path / "uploads"
    chroma.mkdir()
    uploads.mkdir()
    cfg = Settings(chroma_persist_dir=str(chroma), rag_upload_dir=str(uploads))
    store = VectorStore(cfg, persist_path=str(chroma))
    embedder = FakeEmbedder()
    service = RagService(
        cfg,
        vector_store=store,
        embedding_service=embedder,
        retriever=Retriever(store, embedder),
        llm=object(),  # type: ignore[arg-type]
    )

    # Index Java material only.
    java_id = "java-doc"
    chunks = [
        TextChunk(text="Java generics and collections framework.", page=1, chunk_number=1)
    ]
    store.add_document_chunks(
        document_id=java_id,
        title="Java",
        chunks=chunks,
        embeddings=[embedder.embed(chunks[0].text)],
    )
    pdf_path = uploads / f"{java_id}.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    service._save_record(
        DocumentRecord(
            document_id=java_id,
            title="Java",
            file_name="Java.pdf",
            file_path=str(pdf_path),
            chunk_count=1,
            created_at="t",
        )
    )

    events = [_Event(id="e1", title="Operating Systems Exam", category="Exam")]
    topics = service.topics_for_events(events)
    assert topics == {}
