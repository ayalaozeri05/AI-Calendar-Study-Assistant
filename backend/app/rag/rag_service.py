"""Standalone RAG orchestration: ingest PDFs and answer from retrieved context."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings, settings
from app.gateways.ollama_gateway import OllamaError, OllamaGateway
from app.rag.document_loader import DocumentLoadError, load_pdf_pages
from app.rag.document_matcher import (
    MatchResult,
    course_lookup_key,
    expand_aliases,
    normalize_key,
    score_all_documents,
    score_document_match,
)
from app.rag.embedding_service import EmbeddingConfigurationError, EmbeddingService
from app.rag.paths import upload_dir
from app.rag.retriever import Retriever
from app.rag.text_splitter import split_pages
from app.rag.topic_extractor import extract_topics_from_chunks
from app.rag.vector_store import StoredChunk, VectorStore

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = (
    "You are helping a university student. "
    "Answer ONLY from the supplied context. "
    "If the answer is not contained in the context, say so clearly."
)

NO_CONTEXT_ANSWER = (
    "I could not find relevant information in the uploaded study materials "
    "to answer that question."
)


class RagError(RuntimeError):
    """User-facing RAG failure with a stable error code."""

    def __init__(self, message: str, *, code: str = "rag_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class DocumentRecord:
    document_id: str
    title: str
    file_name: str
    file_path: str
    chunk_count: int
    created_at: str
    page_count: int = 0


@dataclass
class RagSource:
    title: str
    page: int
    chunk: int


@dataclass
class RagAnswer:
    answer: str
    sources: list[RagSource]


class RagService:
    """PDF → chunks → embeddings → Chroma → retrieve → Ollama answer."""

    def __init__(
        self,
        app_settings: Settings | None = None,
        *,
        vector_store: VectorStore | None = None,
        embedding_service: EmbeddingService | None = None,
        retriever: Retriever | None = None,
        llm: OllamaGateway | None = None,
    ) -> None:
        self._settings = app_settings or settings
        self._embeddings = embedding_service or EmbeddingService(
            OllamaGateway(self._settings)
        )
        self._store = vector_store or VectorStore(self._settings)
        self._retriever = retriever or Retriever(
            self._store,
            self._embeddings,
        )
        self._llm = llm or OllamaGateway(self._settings)
        self._upload_root = upload_dir(self._settings)
        self._registry_path = self._upload_root / "documents.json"
        # Last enrichment trace for API meta / live debugging.
        self.last_topics: list[str] = []
        self.last_chunk_count: int = 0
        self.last_matched_document: str | None = None
        self.last_matched_documents: list[str] = []
        self.last_match_reason: str | None = None

    def upload_pdf(self, *, title: str, filename: str, content: bytes) -> DocumentRecord:
        """Persist the PDF, index chunks into Chroma, return metadata.

        Always ADDS a new indexed document. Existing PDFs are kept unless the
        user explicitly removes one via remove_document().
        """
        clean_title = (title or "").strip() or Path(filename).stem or "Untitled"
        if not content:
            raise RagError("Uploaded file is empty.", code="empty_file")
        if not (filename or "").lower().endswith(".pdf"):
            raise RagError("Only PDF uploads are supported.", code="invalid_file_type")

        try:
            self._embeddings.ensure_ready()
        except EmbeddingConfigurationError as exc:
            raise RagError(str(exc), code="embedding_not_configured") from exc

        document_id = str(uuid.uuid4())
        dest = self._upload_root / f"{document_id}.pdf"
        dest.write_bytes(content)

        try:
            pages = load_pdf_pages(dest)
            page_count = len(pages)
            chunks = split_pages(pages)
            if not chunks:
                raise RagError(
                    "No text chunks could be created from this PDF.",
                    code="no_chunks",
                )
            embeddings = self._embeddings.embed_many([c.text for c in chunks])
            self._store.add_document_chunks(
                document_id=document_id,
                title=clean_title,
                chunks=chunks,
                embeddings=embeddings,
            )
        except DocumentLoadError as exc:
            dest.unlink(missing_ok=True)
            raise RagError(str(exc), code="pdf_load_failed") from exc
        except EmbeddingConfigurationError as exc:
            dest.unlink(missing_ok=True)
            raise RagError(str(exc), code="embedding_not_configured") from exc
        except RagError:
            dest.unlink(missing_ok=True)
            raise
        except Exception as exc:
            dest.unlink(missing_ok=True)
            logger.exception("rag_upload_failed document_id=%s", document_id)
            raise RagError(f"Failed to index PDF: {exc}", code="index_failed") from exc

        record = DocumentRecord(
            document_id=document_id,
            title=clean_title,
            file_name=Path(filename).name,
            file_path=str(dest),
            chunk_count=len(chunks),
            page_count=page_count,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._save_record(record)
        # Safe metadata only — never log PDF body text.
        logger.info(
            'stage=rag_upload document=%r pages=%s chunks=%s embedding_count=%s',
            Path(filename).name,
            page_count,
            len(chunks),
            len(embeddings),
        )
        return record

    def has_indexed_material(self) -> bool:
        """True when at least one verified indexed document exists."""
        return bool(self.list_indexed_documents())

    def list_documents(self) -> list[DocumentRecord]:
        """Registry rows (may include stale entries). Prefer list_indexed_documents()."""
        rows = self._load_registry()
        out: list[DocumentRecord] = []
        for row in rows:
            try:
                out.append(
                    DocumentRecord(
                        document_id=str(row.get("document_id") or ""),
                        title=str(row.get("title") or ""),
                        file_name=str(row.get("file_name") or ""),
                        file_path=str(row.get("file_path") or ""),
                        chunk_count=int(row.get("chunk_count") or 0),
                        page_count=int(row.get("page_count") or 0),
                        created_at=str(row.get("created_at") or ""),
                    )
                )
            except Exception:
                continue
        return [r for r in out if r.document_id]

    def list_indexed_documents(self) -> list[DocumentRecord]:
        """Documents that still have a PDF on disk and Chroma vectors."""
        verified: list[DocumentRecord] = []
        for doc in self.list_documents():
            if not Path(doc.file_path).is_file():
                continue
            if self._store.count_for_document(doc.document_id) <= 0:
                continue
            verified.append(doc)
        return verified

    def latest_document(self) -> DocumentRecord | None:
        docs = self.list_indexed_documents()
        return docs[-1] if docs else None

    def retrieve_topics(
        self,
        query: str,
        *,
        document_id: str | None = None,
        top_k: int = 4,
        limit: int = 8,
    ) -> tuple[list[str], list[StoredChunk]]:
        """Retrieve relevant chunks and extract study-topic labels (no LLM)."""
        q = (query or "").strip()
        if not q or not document_id:
            return [], []
        try:
            chunks = self._retriever.retrieve(q, document_id=document_id, top_k=top_k)
        except EmbeddingConfigurationError:
            raise
        except Exception as exc:
            logger.info("rag_retrieve_topics_failed err=%s", type(exc).__name__)
            return [], []
        return extract_topics_from_chunks(chunks, limit=limit), chunks

    def remove_document(self, document_id: str | None = None) -> DocumentRecord | None:
        """Remove ONE indexed study PDF (registry + file + Chroma vectors).

        Other documents are left untouched. document_id is required for
        multi-doc safety; if omitted, removes nothing.
        """
        doc_id = (document_id or "").strip()
        if not doc_id:
            return None
        docs = self.list_indexed_documents()
        target = next((d for d in docs if d.document_id == doc_id), None)
        if target is None:
            # Also allow removing a registry-only/stale row by id.
            for row in self.list_documents():
                if row.document_id == doc_id:
                    target = row
                    break
        if target is None:
            return None

        self._store.delete_document(target.document_id)
        path = Path(target.file_path)
        if path.is_file():
            path.unlink(missing_ok=True)

        keep = [
            row
            for row in self._load_registry()
            if str(row.get("document_id") or "") != target.document_id
        ]
        self._registry_path.write_text(
            json.dumps(keep, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(
            "rag_document_removed document_id=%s file=%s",
            target.document_id,
            target.file_name,
        )
        return target

    def topics_for_events(
        self,
        events: list[Any],
    ) -> dict[str, list[str]]:
        """Map event_id (+ course: title key) → topics from relevant PDFs.

        May combine chunks from multiple matching documents. Unrelated PDFs
        are excluded. Only exam/assignment/project events are enriched.
        """
        self.last_topics = []
        self.last_chunk_count = 0
        self.last_matched_document = None
        self.last_matched_documents = []
        self.last_match_reason = None

        documents = self.list_indexed_documents()
        if not documents:
            self.last_match_reason = "no_indexed_documents"
            logger.info(
                "stage=rag_retrieval matched_documents=0 retrieved_chunks=0 "
                "topics=[] rag_used=false reason=no_indexed_documents"
            )
            return {}

        try:
            self._embeddings.ensure_ready()
        except EmbeddingConfigurationError as exc:
            logger.info(
                "stage=rag_retrieval matched_documents=0 retrieved_chunks=0 "
                "topics=[] rag_used=false reason=embedding_not_configured"
            )
            self.last_match_reason = "embedding_not_configured"
            _ = exc
            return {}

        out: dict[str, list[str]] = {}
        matched_names: list[str] = []

        for event in events:
            cat_obj = getattr(event, "category", None)
            category = str(getattr(cat_obj, "value", cat_obj) or "").lower()
            if category not in {"exam", "assignment", "project"}:
                continue

            event_id = str(getattr(event, "id", "") or "")
            title = str(getattr(event, "title", "") or "").strip()
            description = str(getattr(event, "description", "") or "").strip()
            if not title:
                continue

            matches = score_all_documents(
                title, documents, description=description
            )

            # Single PDF: allow semantic retrieval when filename match is weak.
            if not matches and len(documents) == 1:
                candidate = documents[0]
                label = category.replace("_", " ").title()
                probe_query = f"{label}: {title}"
                if description:
                    probe_query = f"{probe_query}\n{description[:240]}"
                try:
                    probe_chunks = self._retriever.retrieve(
                        probe_query,
                        document_id=candidate.document_id,
                        top_k=4,
                    )
                except Exception:
                    probe_chunks = []
                if _chunks_are_relevant(
                    probe_chunks, title=title, description=description
                ):
                    matches = [
                        MatchResult(
                            document=candidate,
                            score=0.5,
                            matched=True,
                            reason="single_pdf_semantic",
                            event_key=normalize_key(title),
                            document_key=normalize_key(
                                candidate.file_name or candidate.title
                            ),
                            document_name=candidate.file_name or candidate.title,
                        )
                    ]
                    self.last_match_reason = "single_pdf_semantic_accepted"
                else:
                    best = score_document_match(
                        title, documents, description=description
                    )
                    self.last_match_reason = (
                        f"single_pdf_semantic_rejected name_reason={best.reason}"
                    )
                    logger.info(
                        "stage=rag_retrieval event=%r matched_documents=0 "
                        "retrieved_chunks=0 topics=[] rag_used=false "
                        "reason=single_pdf_semantic_rejected",
                        title,
                    )
                    continue

            if not matches:
                best = score_document_match(
                    title, documents, description=description
                )
                self.last_match_reason = best.reason
                logger.info(
                    "stage=rag_retrieval event=%r matched_documents=0 "
                    "retrieved_chunks=0 topics=[] rag_used=false reason=%s",
                    title,
                    best.reason,
                )
                continue

            label = category.replace("_", " ").title()
            query = f"{label}: {title}"
            if description:
                query = f"{query}\n{description[:240]}"

            combined_chunks: list[StoredChunk] = []
            used_docs: list[DocumentRecord] = []
            for match in matches:
                doc = match.document
                if doc is None:
                    continue
                try:
                    _topics, chunks = self.retrieve_topics(
                        query,
                        document_id=doc.document_id,
                        top_k=4,
                    )
                except EmbeddingConfigurationError:
                    return out
                except Exception:
                    chunks = []
                if not chunks:
                    chunks = self._store.get_chunks_for_document(
                        doc.document_id, limit=4
                    )
                if not chunks:
                    continue
                # Keep only semantically relevant hits for multi-doc safety.
                if len(matches) > 1 and not _chunks_are_relevant(
                    chunks, title=title, description=description
                ):
                    # Name match is strong enough (≥ threshold) — still allow.
                    if match.score < 0.75:
                        continue
                combined_chunks.extend(chunks)
                used_docs.append(doc)

            if not combined_chunks:
                self.last_match_reason = "no_topics_from_chunks"
                logger.info(
                    "stage=rag_retrieval event=%r matched_documents=0 "
                    "retrieved_chunks=0 topics=[] rag_used=false "
                    "reason=no_chunks",
                    title,
                )
                continue

            # Rank by distance (lower is better); keep best combined chunks.
            combined_chunks.sort(
                key=lambda c: (
                    c.distance if c.distance is not None else 9.0,
                    c.page,
                    c.chunk_number,
                )
            )
            best_chunks = combined_chunks[:8]
            topics = extract_topics_from_chunks(best_chunks, limit=8)
            if not topics:
                self.last_match_reason = "no_topics_from_chunks"
                logger.info(
                    "stage=rag_retrieval event=%r matched_documents=%s "
                    "retrieved_chunks=%s pages=%s topics=[] rag_used=false "
                    "reason=no_topics",
                    title,
                    len(used_docs),
                    len(best_chunks),
                    sorted({c.page for c in best_chunks if c.page}),
                )
                continue

            names = [d.file_name or d.title for d in used_docs]
            for name in names:
                if name and name not in matched_names:
                    matched_names.append(name)

            pages = sorted({c.page for c in best_chunks if c.page})
            self.last_chunk_count = max(self.last_chunk_count, len(best_chunks))
            self.last_topics = list(topics)
            self.last_matched_documents = list(matched_names)
            self.last_matched_document = matched_names[0] if matched_names else None
            self.last_match_reason = (
                "multi_document_ok" if len(used_docs) > 1 else "score_ok"
            )

            if event_id:
                out[event_id] = topics
            out[course_lookup_key(title)] = topics
            logger.info(
                "stage=rag_retrieval event=%r matched_documents=%s "
                "retrieved_chunks=%s pages=%s topics=%s rag_used=true",
                title,
                names,
                len(best_chunks),
                pages,
                topics,
            )

        if not out and self.last_match_reason is None:
            self.last_match_reason = "no_study_target_events"
            logger.info(
                "stage=rag_retrieval matched_documents=0 retrieved_chunks=0 "
                "topics=[] rag_used=false reason=no_study_target_events"
            )
        return out

    def ask(self, question: str, *, document_id: str | None = None) -> RagAnswer:
        """Retrieve relevant chunks and answer with llama3.2 via OllamaGateway.

        Kept for API/debug; the planner uses retrieve_topics() instead.
        """
        q = (question or "").strip()
        if not q:
            raise RagError("Question is required.", code="empty_question")

        try:
            chunks = self._retriever.retrieve(q, document_id=document_id)
        except EmbeddingConfigurationError as exc:
            raise RagError(str(exc), code="embedding_not_configured") from exc

        if not chunks:
            return RagAnswer(answer=NO_CONTEXT_ANSWER, sources=[])

        prompt = self._build_prompt(q, chunks)
        try:
            answer = self._llm.invoke(
                prompt,
                temperature=0.1,
                system_prompt=RAG_SYSTEM_PROMPT,
            ).strip()
        except OllamaError as exc:
            raise RagError(
                f"Ollama failed while answering: {exc}",
                code="llm_unavailable",
            ) from exc

        if not answer:
            answer = NO_CONTEXT_ANSWER

        sources = [
            RagSource(title=c.title, page=c.page, chunk=c.chunk_number)
            for c in chunks
        ]
        return RagAnswer(answer=answer, sources=sources)

    @staticmethod
    def _build_prompt(question: str, chunks: list[StoredChunk]) -> str:
        context_blocks: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            context_blocks.append(
                f"[{i}] title={chunk.title} page={chunk.page} "
                f"chunk={chunk.chunk_number}\n{chunk.text}"
            )
        context = "\n\n".join(context_blocks)
        return (
            "You are helping a university student.\n\n"
            "Answer ONLY from the supplied context.\n"
            "If the answer is not contained in the context, say so.\n\n"
            f"Context:\n{context}\n\n"
            f"Question:\n{question}\n"
        )

    def _save_record(self, record: DocumentRecord) -> None:
        rows = self._load_registry()
        rows.append(asdict(record))
        self._registry_path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_registry(self) -> list[dict[str, Any]]:
        if not self._registry_path.is_file():
            return []
        try:
            data = json.loads(self._registry_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []


def _chunks_are_relevant(
    chunks: list[StoredChunk],
    *,
    title: str,
    description: str = "",
    max_distance: float = 0.48,
) -> bool:
    """Accept single-PDF semantic hits only when similarity/content looks real."""
    if not chunks:
        return False
    distances = [c.distance for c in chunks if c.distance is not None]
    if distances and min(distances) <= max_distance:
        return True
    # Content overlap fallback when distances are unavailable.
    # Uses text only for matching — never logged.
    probe = normalize_key(f"{title} {description}")
    if len(probe) < 3:
        return False
    blob = normalize_key(" ".join((c.text or "")[:400] for c in chunks))
    if not blob:
        return False
    if probe in blob or any(len(p) >= 4 and p in blob for p in _split_probe(probe)):
        return True
    # Alias-friendly: Operating Systems keywords in English notes.
    return any(a in blob for a in expand_aliases(probe) if len(a) >= 4)


def _split_probe(key: str) -> list[str]:
    # Soft-split long compacted keys into overlapping windows.
    if len(key) <= 8:
        return [key]
    return [key[i : i + 8] for i in range(0, max(1, len(key) - 7), 4)]
