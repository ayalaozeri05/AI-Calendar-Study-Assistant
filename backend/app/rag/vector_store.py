"""Persistent Chroma vector store for study-material chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import chromadb

from app.config import Settings, settings
from app.rag.paths import chroma_dir
from app.rag.text_splitter import TextChunk

COLLECTION_NAME = "study_materials"


@dataclass(frozen=True)
class StoredChunk:
    document_id: str
    title: str
    page: int
    chunk_number: int
    text: str
    distance: float | None = None


class VectorStore:
    """Chroma persistent client scoped to the study_materials collection."""

    def __init__(self, app_settings: Settings | None = None, *, persist_path: str | None = None) -> None:
        cfg = app_settings or settings
        path = persist_path or str(chroma_dir(cfg))
        self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def collection(self):
        return self._collection

    def add_document_chunks(
        self,
        *,
        document_id: str,
        title: str,
        chunks: list[TextChunk],
        embeddings: list[list[float]],
    ) -> int:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")
        if not chunks:
            return 0

        ids = [f"{document_id}:{chunk.chunk_number}" for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas: list[dict[str, Any]] = [
            {
                "document_id": document_id,
                "title": title,
                "page": int(chunk.page),
                "chunk_number": int(chunk.chunk_number),
            }
            for chunk in chunks
        ]
        self._collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return len(chunks)

    def query(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 4,
        document_id: str | None = None,
    ) -> list[StoredChunk]:
        if top_k < 1:
            return []

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if document_id:
            kwargs["where"] = {"document_id": document_id}

        try:
            raw = self._collection.query(**kwargs)
        except Exception:
            # Empty collection / no match → empty retrieval (real RAG, not fake).
            return []

        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]

        results: list[StoredChunk] = []
        for i, text in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            dist = dists[i] if i < len(dists) else None
            if not text:
                continue
            results.append(
                StoredChunk(
                    document_id=str(meta.get("document_id") or ""),
                    title=str(meta.get("title") or ""),
                    page=int(meta.get("page") or 0),
                    chunk_number=int(meta.get("chunk_number") or 0),
                    text=str(text),
                    distance=float(dist) if dist is not None else None,
                )
            )
        return results

    def count(self) -> int:
        return int(self._collection.count())

    def count_for_document(self, document_id: str) -> int:
        doc_id = (document_id or "").strip()
        if not doc_id:
            return 0
        try:
            raw = self._collection.get(where={"document_id": doc_id}, include=[])
            return len(raw.get("ids") or [])
        except Exception:
            return 0

    def delete_document(self, document_id: str) -> int:
        """Remove all vectors for a document. Returns deleted id count (best-effort)."""
        doc_id = (document_id or "").strip()
        if not doc_id:
            return 0
        before = self.count_for_document(doc_id)
        if before <= 0:
            return 0
        try:
            self._collection.delete(where={"document_id": doc_id})
        except Exception:
            return 0
        return before

    def get_chunks_for_document(
        self,
        document_id: str,
        *,
        limit: int = 12,
    ) -> list[StoredChunk]:
        """Return stored chunks for a document (no similarity query)."""
        doc_id = (document_id or "").strip()
        if not doc_id or limit < 1:
            return []
        try:
            raw = self._collection.get(
                where={"document_id": doc_id},
                include=["documents", "metadatas"],
            )
        except Exception:
            return []
        docs = raw.get("documents") or []
        metas = raw.get("metadatas") or []
        out: list[StoredChunk] = []
        for i, text in enumerate(docs):
            if not text:
                continue
            meta = metas[i] if i < len(metas) else {}
            out.append(
                StoredChunk(
                    document_id=str(meta.get("document_id") or doc_id),
                    title=str(meta.get("title") or ""),
                    page=int(meta.get("page") or 0),
                    chunk_number=int(meta.get("chunk_number") or i + 1),
                    text=str(text),
                )
            )
            if len(out) >= limit:
                break
        return out
