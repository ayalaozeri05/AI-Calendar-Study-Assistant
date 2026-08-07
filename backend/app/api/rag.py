"""RAG API — upload study PDFs used to enrich Create Study Plan."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.rag.rag_service import RagError, RagService
from app.schemas.rag_schema import (
    RagAskRequest,
    RagAskResponse,
    RagDocumentOut,
    RagSourceOut,
    RagStatusResponse,
    RagUploadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


def _http_from_rag_error(exc: RagError) -> HTTPException:
    status = 503 if exc.code in {
        "embedding_not_configured",
        "llm_unavailable",
    } else 400
    logger.warning(
        "rag_api_error status=%s code=%s message=%s",
        status,
        exc.code,
        str(exc),
    )
    return HTTPException(
        status_code=status,
        detail={"message": str(exc), "code": exc.code},
    )


def _status_payload(service: RagService | None = None) -> RagStatusResponse:
    service = service or RagService()
    docs = service.list_indexed_documents()
    items = [
        RagDocumentOut(
            document_id=d.document_id,
            file_name=d.file_name,
            title=d.title,
            indexed=True,
            chunk_count=d.chunk_count,
            created_at=d.created_at or None,
        )
        for d in docs
    ]
    latest = docs[-1] if docs else None
    return RagStatusResponse(
        documents=items,
        has_document=bool(items),
        indexed=bool(items),
        document_id=latest.document_id if latest else None,
        title=latest.title if latest else None,
        file_name=latest.file_name if latest else None,
        chunk_count=latest.chunk_count if latest else 0,
        created_at=latest.created_at if latest else None,
    )


@router.get("/status", response_model=RagStatusResponse)
def rag_status():
    """Return all indexed study PDFs available for planner enrichment."""
    return _status_payload()


@router.post("/upload", response_model=RagUploadResponse)
async def upload_study_material(
    title: str = Form(..., description="Display title for the study PDF"),
    file: UploadFile = File(..., description="PDF study material"),
):
    """Accept a PDF + title, extract/chunk/embed, and ADD it to the index.

    Existing documents are kept; this never replaces other PDFs.
    """
    filename = file.filename or "document.pdf"
    content = await file.read()
    logger.info(
        "rag_upload_received filename=%s title=%s bytes=%s",
        filename,
        title,
        len(content or b""),
    )
    try:
        record = RagService().upload_pdf(
            title=title,
            filename=filename,
            content=content,
        )
    except RagError as exc:
        raise _http_from_rag_error(exc) from exc
    return RagUploadResponse(
        document_id=record.document_id,
        title=record.title,
        file_name=record.file_name,
        chunk_count=record.chunk_count,
        page_count=record.page_count,
        indexed=True,
        created_at=record.created_at,
    )


@router.delete("/documents/{document_id}", response_model=RagStatusResponse)
def remove_study_document(document_id: str):
    """Remove one indexed study PDF without affecting the others."""
    service = RagService()
    removed = service.remove_document(document_id)
    if removed is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Study material not found.",
                "code": "not_found",
            },
        )
    return _status_payload(service)


@router.delete("/document", response_model=RagStatusResponse)
def remove_study_material(document_id: str | None = None):
    """Legacy remove endpoint — prefers document_id query param."""
    if not (document_id or "").strip():
        raise HTTPException(
            status_code=400,
            detail={
                "message": "document_id is required.",
                "code": "document_id_required",
            },
        )
    return remove_study_document(document_id.strip())


@router.post("/ask", response_model=RagAskResponse)
def ask_study_material(body: RagAskRequest):
    """Debug/helper: retrieve chunks and answer with Ollama."""
    try:
        result = RagService().ask(body.question, document_id=body.document_id)
    except RagError as exc:
        raise _http_from_rag_error(exc) from exc
    return RagAskResponse(
        answer=result.answer,
        sources=[
            RagSourceOut(title=s.title, page=s.page, chunk=s.chunk)
            for s in result.sources
        ],
    )
