from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    id: str
    source: str
    title: str
    url: str
    summary: str = ""
    published_at: datetime | None = None
    series: str = "f1"
    source_score: int = 0
    source_kind: str = "news"
    source_tags: list[str] = Field(default_factory=list)
    editorial_mode: str = "single_story"


class Draft(BaseModel):
    id: int
    item_id: str
    title: str
    url: str
    text: str
    status: str
    created_at: str
    updated_at: str
