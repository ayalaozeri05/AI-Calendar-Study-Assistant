"""Match calendar course/exam titles to uploaded study documents.

Supports Hebrew and English titles/filenames. Exact filename equality is not required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.rag_service import DocumentRecord

# Calendar / file noise in English and Hebrew.
_NOISE = re.compile(
    r"(?:"
    r"\b(?:exam|midterm|final|test|quiz|assignment|homework|hw|project|"
    r"lecture|class|course|notes?|pdf)\b|"
    r"מבחן|בוחן|מטלה|תרגיל|פרויקט|הרצאה|קורס|סיכום|הערות"
    r")",
    re.I,
)

# Compact bilingual course aliases (after normalize_key).
_ALIAS_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"operatingsystems", "os", "מערכתהפעלה", "מערכותהפעלה"}),
    frozenset({"java", "javaprogramming", "גאווה", "ג'אווה"}),
    frozenset({"networks", "computernetworks", "רשתות", "רשתותמחשבים"}),
    frozenset({"automata", "אוטומטים", "תורתהחישוביות"}),
    frozenset({"databases", "database", "db", "מסדינתונים", "בסיסינתונים"}),
    frozenset({"algorithms", "אלגוריתמים", "תכנוןאלגוריתמים"}),
    frozenset({"datastructures", "מבנינתונים"}),
    frozenset({"compilers", "מהדרים"}),
    frozenset({"security", "אבטחתמידע", "סייבר"}),
)


@dataclass(frozen=True)
class MatchResult:
    document: "DocumentRecord | None"
    score: float
    matched: bool
    reason: str
    event_key: str
    document_key: str
    document_name: str = ""


def normalize_key(value: str) -> str:
    """Normalize for matching while preserving Hebrew and Latin letters."""
    text = _NOISE.sub(" ", value or "")
    text = text.casefold()
    # Keep unicode word characters (letters/digits), drop separators.
    text = re.sub(r"[^\w]+", "", text, flags=re.UNICODE)
    return text.replace("_", "")


def course_lookup_key(value: str) -> str:
    """Stable dict key for title-based RAG topic lookup."""
    return f"course:{normalize_key(value)}"


MATCH_THRESHOLD = 0.42


def match_document_for_course(
    course_title: str,
    documents: list["DocumentRecord"],
    *,
    description: str = "",
) -> "DocumentRecord | None":
    """Return the uploaded document that best matches a calendar event title."""
    result = score_document_match(course_title, documents, description=description)
    return result.document if result.matched else None


def score_all_documents(
    course_title: str,
    documents: list["DocumentRecord"],
    *,
    description: str = "",
    threshold: float = MATCH_THRESHOLD,
) -> list[MatchResult]:
    """Return every document whose match score meets the threshold (best first)."""
    title_key = normalize_key(course_title or "")
    desc_key = normalize_key(description or "")
    event_key = title_key or desc_key
    if not documents or not event_key or len(event_key) < 2:
        return []

    scored: list[MatchResult] = []
    for doc in documents:
        best_score = -1.0
        best_doc_key = ""
        for raw in (
            doc.title or "",
            doc.file_name or "",
            Path(doc.file_name or "").stem,
        ):
            doc_key = normalize_key(raw)
            if len(doc_key) < 2:
                continue
            score = _similarity(title_key, doc_key) if title_key else 0.0
            if desc_key:
                score = max(score, _similarity(desc_key, doc_key) * 0.95)
            if score > best_score:
                best_score = score
                best_doc_key = doc_key
        if best_score >= threshold:
            scored.append(
                MatchResult(
                    document=doc,
                    score=best_score,
                    matched=True,
                    reason="score_ok",
                    event_key=event_key,
                    document_key=best_doc_key,
                    document_name=doc.file_name or doc.title or doc.document_id,
                )
            )
    scored.sort(key=lambda r: r.score, reverse=True)
    return scored


def score_document_match(
    course_title: str,
    documents: list["DocumentRecord"],
    *,
    description: str = "",
) -> MatchResult:
    """Score event↔best document match with an explicit rejection reason."""
    title_key = normalize_key(course_title or "")
    desc_key = normalize_key(description or "")
    event_key = title_key or desc_key
    if not documents:
        return MatchResult(
            document=None,
            score=0.0,
            matched=False,
            reason="no_indexed_documents",
            event_key=event_key,
            document_key="",
        )
    if not event_key or len(event_key) < 2:
        return MatchResult(
            document=None,
            score=0.0,
            matched=False,
            reason="event_key_too_short_after_normalize",
            event_key=event_key,
            document_key="",
        )

    matches = score_all_documents(
        course_title, documents, description=description, threshold=0.0
    )
    if not matches:
        return MatchResult(
            document=None,
            score=0.0,
            matched=False,
            reason="no_document_keys",
            event_key=event_key,
            document_key="",
        )
    best = matches[0]
    if best.score < MATCH_THRESHOLD:
        return MatchResult(
            document=None,
            score=best.score,
            matched=False,
            reason=f"score_below_threshold({best.score:.3f}<{MATCH_THRESHOLD})",
            event_key=event_key,
            document_key=best.document_key,
            document_name=best.document_name,
        )
    return best


def expand_aliases(key: str) -> set[str]:
    """Expand a normalized course key with known bilingual aliases."""
    keys = {key} if key else set()
    if not key:
        return keys
    for group in _ALIAS_GROUPS:
        if key in group:
            keys |= set(group)
            continue
        # Partial containment for compacted compounds (e.g. examinmavar...).
        if any(alias and (alias in key or key in alias) for alias in group):
            keys |= set(group)
    return keys


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    aliases_a = expand_aliases(a)
    aliases_b = expand_aliases(b)
    if aliases_a & aliases_b:
        return 0.92

    # Contained compacted forms (במערכותהפעלה vs מערכותהפעלה).
    best_contain = 0.0
    for x in aliases_a:
        for y in aliases_b:
            if not x or not y:
                continue
            if x in y or y in x:
                shorter = min(len(x), len(y))
                longer = max(len(x), len(y))
                best_contain = max(best_contain, shorter / longer)
    if best_contain >= 0.55:
        return best_contain

    # Character n-gram overlap (works for Hebrew and English).
    best_grams = 0.0
    for x in aliases_a:
        for y in aliases_b:
            best_grams = max(best_grams, _ngram_overlap(x, y))
    return best_grams


def _ngram_overlap(a: str, b: str, n: int = 3) -> float:
    if not a or not b:
        return 0.0
    if len(a) < n or len(b) < n:
        return 1.0 if a == b else (1.0 if a in b or b in a else 0.0)
    grams_a = {a[i : i + n] for i in range(len(a) - n + 1)}
    grams_b = {b[i : i + n] for i in range(len(b) - n + 1)}
    if not grams_a or not grams_b:
        return 0.0
    inter = len(grams_a & grams_b)
    return inter / max(len(grams_a), len(grams_b))
