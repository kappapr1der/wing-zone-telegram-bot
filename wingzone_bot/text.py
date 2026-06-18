from __future__ import annotations

import re
from html import unescape

from .models import Draft

TELEGRAM_MESSAGE_LIMIT = 4096


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_feed_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    clean = normalize_spaces(unescape(without_tags))
    clean = re.sub(r"(?<=[.!?])(?=[A-ZА-Я])", " ", clean)
    clean = re.sub(r"\s*(keep reading|continue reading)\s*$", "", clean, flags=re.IGNORECASE)
    return clean.strip()


def telegram_chunks(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    clean = text.strip()
    if not clean:
        return [""]
    if len(clean) <= limit:
        return [clean]

    chunks: list[str] = []
    current = ""
    for paragraph in clean.split("\n\n"):
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph

        while len(current) > limit:
            chunks.append(current[:limit])
            current = current[limit:]

    if current:
        chunks.append(current)
    return chunks


def format_review_message(draft: Draft) -> str:
    return (
        f"Draft #{draft.id} [{draft.status}]\n"
        f"{draft.title}\n\n"
        f"{draft.text}"
    ).strip()


def format_draft_list(drafts: list[Draft]) -> str:
    if not drafts:
        return "No drafts yet."
    lines = ["Recent drafts:"]
    for draft in drafts:
        title = draft.title
        if len(title) > 90:
            title = f"{title[:87]}..."
        lines.append(f"#{draft.id} [{draft.status}] {title}")
    return "\n".join(lines)
