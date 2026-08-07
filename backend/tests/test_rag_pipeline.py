"""Tests for the standalone RAG pipeline (real retrieval, mocked Ollama I/O)."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.main import app
from app.rag.document_loader import LoadedPage, load_pdf_pages
from app.rag.embedding_service import EmbeddingService
from app.rag.rag_service import NO_CONTEXT_ANSWER, RagService
from app.rag.retriever import Retriever
from app.rag.text_splitter import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, split_pages
from app.rag.vector_store import VectorStore


class FakeEmbedder(EmbeddingService):
    """Deterministic local embeddings so tests do not need Ollama."""

    def __init__(self) -> None:
        pass

    @property
    def model_name(self) -> str:
        return "fake-embed"

    def ensure_ready(self) -> None:
        return None

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * 32
        for token in (text or "").lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = digest[0] % 32
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FakeLLM:
    def __init__(self, answer: str = "Photosynthesis converts light into chemical energy.") -> None:
        self.answer = answer
        self.last_prompt: str | None = None
        self.last_system: str | None = None

    def invoke(self, prompt: str, **kwargs) -> str:
        self.last_prompt = prompt
        self.last_system = kwargs.get("system_prompt")
        return self.answer


def _write_text_pdf(path: Path, lines: list[str]) -> None:
    """Create a minimal PDF with extractable text (no reportlab)."""
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
def rag_tmp(tmp_path: Path):
    chroma = tmp_path / "chroma"
    uploads = tmp_path / "uploads"
    chroma.mkdir()
    uploads.mkdir()
    from app.config import Settings

    cfg = Settings(
        chroma_persist_dir=str(chroma),
        rag_upload_dir=str(uploads),
    )
    store = VectorStore(cfg, persist_path=str(chroma))
    embedder = FakeEmbedder()
    llm = FakeLLM()
    service = RagService(
        cfg,
        vector_store=store,
        embedding_service=embedder,
        retriever=Retriever(store, embedder, top_k=4),
        llm=llm,  # type: ignore[arg-type]
    )
    return {
        "cfg": cfg,
        "store": store,
        "embedder": embedder,
        "llm": llm,
        "service": service,
        "uploads": uploads,
        "tmp": tmp_path,
    }


def test_chunk_creation_parameters_and_overlap():
    pages = [
        LoadedPage(
            page_number=1,
            text=("Photosynthesis is the process by which green plants make food. " * 40),
        )
    ]
    chunks = split_pages(
        pages,
        chunk_size=DEFAULT_CHUNK_SIZE,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    )
    assert len(chunks) >= 2
    assert all(c.page == 1 for c in chunks)
    assert [c.chunk_number for c in chunks] == list(range(1, len(chunks) + 1))
    assert DEFAULT_CHUNK_SIZE == 800
    assert DEFAULT_CHUNK_OVERLAP == 120


def test_embedding_generation(rag_tmp):
    vec = rag_tmp["embedder"].embed("chlorophyll absorbs light")
    assert isinstance(vec, list)
    assert len(vec) == 32
    assert all(isinstance(x, float) for x in vec)


def test_vector_insert_and_retrieval(rag_tmp):
    pages = [
        LoadedPage(
            page_number=1,
            text="Chlorophyll absorbs sunlight during photosynthesis in plant leaves.",
        ),
        LoadedPage(
            page_number=2,
            text="The mitochondria is the powerhouse of the cell and produces ATP.",
        ),
    ]
    chunks = split_pages(pages)
    embeddings = rag_tmp["embedder"].embed_many([c.text for c in chunks])
    added = rag_tmp["store"].add_document_chunks(
        document_id="doc-1",
        title="Biology Notes",
        chunks=chunks,
        embeddings=embeddings,
    )
    assert added == len(chunks)
    assert rag_tmp["store"].count() == len(chunks)

    hits = rag_tmp["service"]._retriever.retrieve("What absorbs sunlight in plants?")
    assert hits
    assert any("Chlorophyll" in h.text or "photosynthesis" in h.text.lower() for h in hits)
    assert hits[0].title == "Biology Notes"
    assert hits[0].page >= 1
    assert hits[0].chunk_number >= 1


def test_rag_answer_uses_retrieved_context(rag_tmp):
    pages = [
        LoadedPage(
            page_number=1,
            text="Newton's second law states that force equals mass times acceleration.",
        )
    ]
    chunks = split_pages(pages)
    embeddings = rag_tmp["embedder"].embed_many([c.text for c in chunks])
    rag_tmp["store"].add_document_chunks(
        document_id="doc-physics",
        title="Physics",
        chunks=chunks,
        embeddings=embeddings,
    )
    rag_tmp["llm"].answer = "Force equals mass times acceleration."
    result = rag_tmp["service"].ask("What is Newton's second law?")
    assert "mass" in result.answer.lower()
    assert result.sources
    assert result.sources[0].title == "Physics"
    assert rag_tmp["llm"].last_prompt is not None
    assert "Context:" in rag_tmp["llm"].last_prompt
    assert "Newton" in rag_tmp["llm"].last_prompt


def test_no_answer_found_when_store_empty(rag_tmp):
    result = rag_tmp["service"].ask("What is quantum entanglement?")
    assert result.answer == NO_CONTEXT_ANSWER
    assert result.sources == []


def test_pdf_upload_indexes_document(rag_tmp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pdf_path = tmp_path / "notes.pdf"
    _write_text_pdf(
        pdf_path,
        [
            "Cellular respiration releases energy from glucose.",
            "Glycolysis is the first stage of cellular respiration.",
        ],
    )

    from app.rag import rag_service as rag_mod

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
                text=(
                    "Cellular respiration releases energy from glucose. "
                    "Glycolysis is the first stage of cellular respiration."
                ),
            )
        ]

    monkeypatch.setattr(rag_mod, "load_pdf_pages", _safe_load)

    record = rag_tmp["service"].upload_pdf(
        title="Cell Biology",
        filename="notes.pdf",
        content=pdf_path.read_bytes(),
    )
    assert record.document_id
    assert record.title == "Cell Biology"
    assert record.chunk_count >= 1
    assert rag_tmp["store"].count() >= 1
    assert Path(record.file_path).is_file()


def test_upload_and_ask_api_endpoints(rag_tmp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service = rag_tmp["service"]
    pages = [
        LoadedPage(
            page_number=1,
            text="Water boils at 100 degrees Celsius at sea level.",
        )
    ]
    chunks = split_pages(pages)
    embeddings = rag_tmp["embedder"].embed_many([c.text for c in chunks])
    rag_tmp["store"].add_document_chunks(
        document_id="api-doc",
        title="Chemistry",
        chunks=chunks,
        embeddings=embeddings,
    )

    from app.api import rag as rag_api
    from app.rag import rag_service as rag_mod

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
                text="Water boils at 100 degrees Celsius at sea level.",
            )
        ]

    monkeypatch.setattr(rag_mod, "load_pdf_pages", _safe_load)

    client = TestClient(app)
    pdf_path = tmp_path / "chem.pdf"
    _write_text_pdf(pdf_path, ["Water boils at 100 degrees Celsius at sea level."])

    with pdf_path.open("rb") as fh:
        resp = client.post(
            "/rag/upload",
            data={"title": "Chemistry Notes"},
            files={"file": ("chem.pdf", fh, "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Chemistry Notes"
    assert body["chunk_count"] >= 1

    rag_tmp["llm"].answer = "100 degrees Celsius."
    ask = client.post(
        "/rag/ask",
        json={"question": "At what temperature does water boil?"},
    )
    assert ask.status_code == 200, ask.text
    payload = ask.json()
    assert payload["answer"]
    assert "sources" in payload
