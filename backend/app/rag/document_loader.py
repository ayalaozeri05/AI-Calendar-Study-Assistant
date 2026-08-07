"""Load text from uploaded study PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader


class DocumentLoadError(ValueError):
    """Raised when a PDF cannot be read or contains no extractable text."""


@dataclass(frozen=True)
class LoadedPage:
    """One page of extracted PDF text."""

    page_number: int
    text: str


def load_pdf_pages(file_path: str | Path) -> list[LoadedPage]:
    """Extract text from a PDF using LangChain's PyPDFLoader.

    Returns one LoadedPage per non-empty page (1-based page numbers).
    """
    path = Path(file_path)
    if not path.is_file():
        raise DocumentLoadError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise DocumentLoadError("Only PDF files are supported.")

    try:
        loader = PyPDFLoader(str(path))
        documents = loader.load()
    except Exception as exc:
        raise DocumentLoadError(f"Failed to read PDF: {exc}") from exc

    pages: list[LoadedPage] = []
    for doc in documents:
        text = (doc.page_content or "").strip()
        if not text:
            continue
        # LangChain stores 0-based page in metadata; expose 1-based to the UI.
        raw_page = doc.metadata.get("page", len(pages))
        try:
            page_number = int(raw_page) + 1
        except (TypeError, ValueError):
            page_number = len(pages) + 1
        pages.append(LoadedPage(page_number=page_number, text=text))

    if not pages:
        raise DocumentLoadError("No extractable text found in the PDF.")
    return pages
