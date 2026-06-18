from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NewsItem(BaseModel):
    id: str
    source: str
    title: str
    url: str
    summary: str = ""
    published_at: datetime | None = None


class Draft(BaseModel):
    id: int
    item_id: str
    title: str
    url: str
    text: str
    status: str
    created_at: str
    updated_at: str
