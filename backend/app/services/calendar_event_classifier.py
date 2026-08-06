"""Classify calendar events from title + cleaned description (EN + HE)."""

from __future__ import annotations

import re

from app.schemas.calendar_schema import EventCategory
from app.services.description_cleaner import clean_description

# Priority order (first match wins after study-intent overrides).
_PRIORITY: list[tuple[EventCategory, tuple[str, ...]]] = [
    (
        EventCategory.EXAM,
        (
            "exam",
            "test",
            "quiz",
            "midterm",
            "final",
            "assessment",
            "מבחן",
            "בחינה",
            "בוחן",
            "מתכונת",
        ),
    ),
    (
        EventCategory.ASSIGNMENT,
        (
            "assignment",
            "homework",
            "exercise",
            "worksheet",
            "submission",
            "מטלת בית",
            "שיעורי בית",
            "תרגיל בית",
            "מטלה",
            "תרגיל",
            "הגשה",
            "task",
        ),
    ),
    (
        EventCategory.PROJECT,
        (
            "project",
            "presentation",
            "capstone",
            "פרויקט",
            "פרוייקט",
            "מצגת",
        ),
    ),
    (
        EventCategory.STUDY,
        (
            "study",
            "review",
            "practice",
            "revise",
            "revision",
            "learning",
            "ללמוד",
            "לימוד",
            "למידה",
            "חזרה",
            "תרגול",
            "להתכונן",
        ),
    ),
    (
        EventCategory.CLASS,
        (
            "class",
            "lecture",
            "lesson",
            "course",
            "tutorial",
            "lab",
            "שיעור",
            "הרצאה",
            "קורס",
            "מעבדה",
        ),
    ),
    (
        EventCategory.MEETING,
        (
            "meeting",
            "standup",
            "stand-up",
            "office hours",
            "פגישה",
            "ישיבה",
            "שעות קבלה",
        ),
    ),
]

# Studying for an exam is Study, not Exam.
_STUDY_INTENT = (
    re.compile(r"ללמוד\s+למבחן", re.I),
    re.compile(r"להתכונן\s+למבחן", re.I),
    re.compile(r"study\s+for\s+(an?\s+)?(exam|test|quiz|midterm|final)", re.I),
    re.compile(r"prepare\s+for\s+(an?\s+)?(exam|test|quiz|midterm|final)", re.I),
    re.compile(r"review\s+for\s+(an?\s+)?(exam|test|quiz)", re.I),
)

_PREFIX_MAP = {
    "exam": EventCategory.EXAM,
    "test": EventCategory.EXAM,
    "quiz": EventCategory.EXAM,
    "midterm": EventCategory.EXAM,
    "final": EventCategory.EXAM,
    "assignment": EventCategory.ASSIGNMENT,
    "homework": EventCategory.ASSIGNMENT,
    "project": EventCategory.PROJECT,
    "study": EventCategory.STUDY,
    "class": EventCategory.CLASS,
    "lecture": EventCategory.CLASS,
    "meeting": EventCategory.MEETING,
    "מבחן": EventCategory.EXAM,
    "בחינה": EventCategory.EXAM,
    "בוחן": EventCategory.EXAM,
    "הגשה": EventCategory.ASSIGNMENT,
    "תרגיל": EventCategory.ASSIGNMENT,
    "מטלה": EventCategory.ASSIGNMENT,
    "פרויקט": EventCategory.PROJECT,
    "פרוייקט": EventCategory.PROJECT,
    "לימוד": EventCategory.STUDY,
    "ללמוד": EventCategory.STUDY,
    "שיעור": EventCategory.CLASS,
    "הרצאה": EventCategory.CLASS,
    "קורס": EventCategory.CLASS,
    "פגישה": EventCategory.MEETING,
    "ישיבה": EventCategory.MEETING,
}


def _is_hebrew(word: str) -> bool:
    return any("\u0590" <= ch <= "\u05FF" for ch in word)


def _keyword_matches(keyword: str, text: str, lowered: str) -> bool:
    if _is_hebrew(keyword):
        return keyword in text
    # Whole-word match for English to avoid task⊂test mistakes and similar
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", re.I)
    return bool(pattern.search(lowered))


class CalendarEventClassifier:
    """Deterministic keyword classifier (no LLM)."""

    @staticmethod
    def classify(title: str, description: str | None = None) -> EventCategory:
        cleaned_desc = clean_description(description) or ""
        title_only = (title or "").strip()
        text = " ".join(
            part for part in (title_only, cleaned_desc) if part
        ).strip()
        if not text:
            return EventCategory.OTHER

        # 1) Study-for-exam intent overrides exam keywords
        for pattern in _STUDY_INTENT:
            if pattern.search(text):
                return EventCategory.STUDY

        # 2) Explicit category prefix before colon (title only)
        if ":" in title_only:
            prefix = title_only.split(":", 1)[0].strip()
            for category in EventCategory:
                if category != EventCategory.OTHER and prefix.lower() == category.value.lower():
                    return category
            mapped = _PREFIX_MAP.get(prefix.lower()) or _PREFIX_MAP.get(prefix)
            if mapped:
                return mapped

        # 3) Exact short titles
        lowered_title = title_only.lower()
        if lowered_title in {"test", "exam", "quiz", "midterm", "final", "assessment"}:
            return EventCategory.EXAM
        if title_only in {"מבחן", "בחינה", "בוחן", "מתכונת"}:
            return EventCategory.EXAM

        lowered = text.lower()

        # 4) Project vs Meeting disambiguation when both present
        has_project = _keyword_matches("project", text, lowered) or "פרויקט" in text or "פרוייקט" in text
        has_meeting = _keyword_matches("meeting", text, lowered) or "פגישה" in text or "ישיבה" in text
        if has_project and has_meeting:
            # Prefer the earlier subject word in the title
            title_l = title_only.lower()
            p_idx = title_l.find("project")
            m_idx = title_l.find("meeting")
            if p_idx >= 0 and (m_idx < 0 or p_idx < m_idx):
                return EventCategory.PROJECT
            if m_idx >= 0:
                return EventCategory.MEETING
            return EventCategory.PROJECT

        # 5) Priority keyword scan
        for category, keywords in _PRIORITY:
            # Longer phrases first within the category
            for keyword in sorted(keywords, key=len, reverse=True):
                if _keyword_matches(keyword, text, lowered):
                    return category

        return EventCategory.OTHER
