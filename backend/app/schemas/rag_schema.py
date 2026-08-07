"""Pydantic schemas for the RAG API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RagUploadResponse(BaseModel):
    document_id: str
    title: str
    file_name: str
    chunk_count: int
    page_count: int = 0
    indexed: bool = True
    created_at: str


class RagDocumentOut(BaseModel):
    document_id: str
    file_name: str
    title: str
    indexed: bool = True
    chunk_count: int = 0
    created_at: str | None = None


class RagStatusResponse(BaseModel):
    """Multi-document status. Legacy single-file fields remain for older clients."""

    documents: list[RagDocumentOut] = Field(default_factory=list)
    has_document: bool = False
    indexed: bool = False
    # Legacy convenience (latest document) — prefer `documents`.
    document_id: str | None = None
    title: str | None = None
    file_name: str | None = None
    chunk_count: int = 0
    created_at: str | None = None


class RagAskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    document_id: str | None = None


class RagSourceOut(BaseModel):
    title: str
    page: int
    chunk: int


class RagAskResponse(BaseModel):
    answer: str
    sources: list[RagSourceOut]
