"""Split long Telegram messages at natural boundaries (≤3800 chars per chunk)."""

from __future__ import annotations

TELEGRAM_SAFE_CHUNK = 3800
TELEGRAM_HARD_LIMIT = 4096


def split_telegram_message(text: str, *, max_len: int = TELEGRAM_SAFE_CHUNK) -> list[str]:
    """Split text into ordered chunks that fit Telegram's sendMessage limit."""
    body = (text or "").strip()
    if not body:
        return []
    if len(body) <= max_len:
        return [body]

    # Prefer splitting between days / blocks (blank lines), then lines
    paragraphs = body.split("\n\n")
    raw_chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            raw_chunks.append(current.strip())
        current = ""

    for para in paragraphs:
        candidate = para if not current else current + "\n\n" + para
        if len(candidate) <= max_len:
            current = candidate
            continue
        flush()
        if len(para) <= max_len:
            current = para
            continue
        # Split long paragraph on lines
        for line in para.split("\n"):
            line_cand = line if not current else current + "\n" + line
            if len(line_cand) <= max_len:
                current = line_cand
                continue
            flush()
            if len(line) <= max_len:
                current = line
                continue
            # Last resort: hard split on character boundary (avoid mid-surrogate)
            for piece in _hard_split(line, max_len):
                if current and len(current) + 1 + len(piece) <= max_len:
                    current = current + "\n" + piece
                else:
                    flush()
                    current = piece
        flush()
    flush()

    total = len(raw_chunks)
    if total <= 1:
        return raw_chunks

    headed: list[str] = []
    for idx, chunk in enumerate(raw_chunks, start=1):
        header = f"Study Plan — Part {idx}/{total}\n\n"
        room = max_len - len(header)
        if room < 200:
            room = max_len // 2
        if len(chunk) <= room:
            headed.append(header + chunk)
        else:
            # Re-split oversized chunk after header accounting
            for j, piece in enumerate(_hard_split(chunk, room)):
                if j == 0:
                    headed.append(header + piece)
                else:
                    headed.append(f"Study Plan — Part {idx}/{total} (cont.)\n\n" + piece)
    # Re-number if continuation inflated count
    if len(headed) != total:
        n = len(headed)
        renumbered = []
        for i, msg in enumerate(headed, start=1):
            # Strip old header line
            rest = msg.split("\n\n", 1)[-1] if "\n\n" in msg else msg
            renumbered.append(f"Study Plan — Part {i}/{n}\n\n{rest}")
        return renumbered
    return headed


def _hard_split(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    pieces: list[str] = []
    i = 0
    while i < len(text):
        end = min(i + max_len, len(text))
        # Prefer break at space
        if end < len(text):
            space = text.rfind(" ", i, end)
            if space > i + max_len // 2:
                end = space
        pieces.append(text[i:end].strip())
        i = end
        while i < len(text) and text[i] == " ":
            i += 1
    return [p for p in pieces if p]
