"""Client-side description cleaner (mirrors backend clean_description)."""

from __future__ import annotations

import re

_BOILERPLATE_PHRASES = (
    re.compile(
        r"שינויים בשם,?\s*בתיאור או בקבצים המצורפים לא יי?שמרו\.?",
        re.I,
    ),
    re.compile(r"שינויים בשם.*?לא יי?שמרו\.?", re.I | re.S),
    re.compile(r"כדי לערוך,?\s*צריך לעבור אל\s*:?", re.I),
    re.compile(r"this event was created from a (google )?task\.?", re.I),
    re.compile(r"view this task in google tasks\.?", re.I),
    re.compile(r"open in google tasks\.?", re.I),
    re.compile(r"created from a google task\.?", re.I),
    re.compile(r"changes to the title, description, or attachments won.?t be saved\.?", re.I),
    re.compile(r"changes you make.*?won.?t be saved\.?", re.I),
    re.compile(r"to edit this task,?\s*open it in google tasks\.?", re.I),
)

_GOOGLE_URL = re.compile(
    r"https?://(?:tasks|calendar|mail)\.google\.com\S*",
    re.I,
)


def clean_description(text: str | None) -> str:
    if not text:
        return ""
    plain = re.sub(r"<br\s*/?>", "\n", str(text), flags=re.I)
    plain = re.sub(r"</p\s*>", "\n", plain, flags=re.I)
    plain = re.sub(r"</div\s*>", "\n", plain, flags=re.I)
    plain = re.sub(r"<[^>]+>", "", plain)
    plain = (
        plain.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&quot;", '"')
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    for pattern in _BOILERPLATE_PHRASES:
        plain = pattern.sub("", plain)
    plain = _GOOGLE_URL.sub("", plain)

    kept: list[str] = []
    for raw_line in plain.splitlines():
        line = raw_line.strip()
        if not line:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        if re.fullmatch(r"https?://\S+", line, flags=re.I) and "google.com" in line.lower():
            continue
        if re.fullmatch(r"[:.\-–—•*]+", line):
            continue
        kept.append(line)

    result: list[str] = []
    for line in kept:
        if line == "" and (not result or result[-1] == ""):
            continue
        result.append(line)
    return "\n".join(result).strip()
