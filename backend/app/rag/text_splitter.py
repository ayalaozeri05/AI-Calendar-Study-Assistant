"""Split loaded PDF text into overlapping chunks for embedding."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.document_loader import LoadedPage

# chunk_size ≈ 800: large enough to keep a paragraph/concept together for
# retrieval, small enough that several chunks fit in the LLM context window.
DEFAULT_CHUNK_SIZE = 800

# chunk_overlap ≈ 120: preserves sentences that would otherwise be cut at
# chunk boundaries so retrieval still finds them when the question matches
# the overlapping region.
DEFAULT_CHUNK_OVERLAP = 120


@dataclass(frozen=True)
class TextChunk:
    """A single chunk ready for embedding + vector storage."""

    text: str
    page: int
    chunk_number: int


def split_pages(
    pages: list[LoadedPage],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    """Split page texts with RecursiveCharacterTextSplitter."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False,
    )

    chunks: list[TextChunk] = []
    chunk_number = 0
    for page in pages:
        pieces = splitter.split_text(page.text)
        for piece in pieces:
            text = (piece or "").strip()
            if not text:
                continue
            chunk_number += 1
            chunks.append(
                TextChunk(
                    text=text,
                    page=page.page_number,
                    chunk_number=chunk_number,
                )
            )
    return chunks
