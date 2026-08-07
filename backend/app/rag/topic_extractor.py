"""Turn retrieved chunk text into short study-topic labels for the planner."""

from __future__ import annotations

import re

from app.rag.vector_store import StoredChunk

_SPLIT = re.compile(r"[\n•]+|(?<=[.!?])\s+|[,;]|\band\b", re.I)
_CHAPTER = re.compile(r"^(chapter|section|unit)\s+\d+[:.\s-]*", re.I)
_BOILERPLATE = re.compile(
    r"^(table of contents|contents|index|references|bibliography|"
    r"page \d+|copyright|all rights reserved|this chapter|in this|"
    r"introduction|overview|summary)\b",
    re.I,
)
_TITLE_CASE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def extract_topics_from_chunks(
    chunks: list[StoredChunk],
    *,
    limit: int = 8,
) -> list[str]:
    """Extract concise topic phrases from retrieved chunks (no LLM)."""
    found: list[str] = []
    for chunk in chunks:
        text = chunk.text or ""
        for part in _SPLIT.split(text):
            topic = _normalize_topic(part)
            if topic:
                found.append(topic)
        for match in _TITLE_CASE.findall(text):
            topic = _normalize_topic(match)
            if topic:
                found.append(topic)

    out = _dedupe(found, limit)
    if out:
        return out

    # Fallback 1: short lines as topics (common in lecture outlines).
    line_topics: list[str] = []
    for chunk in chunks:
        for line in (chunk.text or "").splitlines():
            topic = _normalize_topic(line)
            if topic:
                line_topics.append(topic)
    out = _dedupe(line_topics, limit)
    if out:
        return out

    # Fallback 2: distinctive words from chunk text (Deadlocks, Paging, …).
    word_topics: list[str] = []
    for chunk in chunks:
        for word in _WORD.findall(chunk.text or ""):
            if word.lower() in _STOP:
                continue
            # Prefer Capitalized concept words.
            if word[0].isupper() or len(word) >= 6:
                word_topics.append(word)
    return _dedupe(word_topics, limit)


def _dedupe(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for topic in items:
        key = topic.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(topic)
        if len(out) >= limit:
            break
    return out


def _normalize_topic(raw: str) -> str | None:
    text = (raw or "").strip()
    # Strip common PDF bullets / private-use glyphs (e.g. \uf0b7).
    text = re.sub(r"^[\s\-\u2022\u25cf\u25e6\u2219\uf0b7•*·▪▸►]+", "", text)
    text = text.strip(" \t-•*·\"'\uf0b7")
    text = _CHAPTER.sub("", text).strip(" \t-•*:")
    if not text or _BOILERPLATE.search(text):
        return None
    # Drop trailing sentence punctuation that survived split.
    text = text.rstrip(".。")
    words = text.split()
    if len(words) < 1 or len(words) > 6:
        return None
    if len(text) < 3 or len(text) > 48:
        return None
    if re.fullmatch(r"[\d.\-]+", text):
        return None
    if text.lower() in _STOP:
        return None
    # Prefer concept labels over full Hebrew/English sentences.
    if len(words) >= 4 and text.endswith((".", "。")):
        return None
    return text


_STOP = {
    "study",
    "review",
    "practice",
    "notes",
    "introduction",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "chapter",
    "section",
    "figure",
    "table",
    "exam",
    "course",
}
