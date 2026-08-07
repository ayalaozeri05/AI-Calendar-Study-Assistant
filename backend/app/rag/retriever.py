"""Retrieve top-k relevant chunks for a question."""

from __future__ import annotations

from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store import StoredChunk, VectorStore

DEFAULT_TOP_K = 4


class Retriever:
    """Embed the question and query the persistent Chroma store."""

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedding_service: EmbeddingService | None = None,
        *,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._store = vector_store or VectorStore()
        self._embeddings = embedding_service or EmbeddingService()
        self.top_k = top_k

    def retrieve(
        self,
        question: str,
        *,
        document_id: str | None = None,
        top_k: int | None = None,
    ) -> list[StoredChunk]:
        """Return the most relevant chunks and their metadata."""
        q = (question or "").strip()
        if not q:
            return []
        if self._store.count() == 0:
            return []

        query_embedding = self._embeddings.embed(q)
        return self._store.query(
            query_embedding,
            top_k=top_k if top_k is not None else self.top_k,
            document_id=document_id,
        )
