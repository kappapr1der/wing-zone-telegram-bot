from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import Draft, NewsItem


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS seen_items (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    published_at TEXT,
                    first_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def is_seen(self, item_id: str) -> bool:
        with self.connect() as connection:
            row = connection.execute("SELECT 1 FROM seen_items WHERE id = ?", (item_id,)).fetchone()
            return row is not None

    def mark_seen(self, item: NewsItem) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO seen_items (id, title, url, source, published_at, first_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.title,
                    item.url,
                    item.source,
                    item.published_at.isoformat() if item.published_at else None,
                    now_iso(),
                ),
            )

    def save_draft(self, item: NewsItem, text: str) -> int:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO drafts (item_id, title, url, text, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item.id, item.title, item.url, text, "draft", timestamp, timestamp),
            )
            return int(cursor.lastrowid)

    def get_draft(self, draft_id: int) -> Draft | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
            return draft_from_row(row) if row else None

    def set_draft_status(self, draft_id: int, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE drafts SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), draft_id),
            )

    def update_draft_text(self, draft_id: int, text: str, status: str = "revised") -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE drafts SET text = ?, status = ?, updated_at = ? WHERE id = ?",
                (text, status, now_iso(), draft_id),
            )

    def recent_drafts(self, limit: int = 10) -> list[Draft]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM drafts ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [draft_from_row(row) for row in rows]


def draft_from_row(row: sqlite3.Row) -> Draft:
    return Draft(
        id=row["id"],
        item_id=row["item_id"],
        title=row["title"],
        url=row["url"],
        text=row["text"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
