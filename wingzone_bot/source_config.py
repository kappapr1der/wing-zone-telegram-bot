from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl

from .config import Settings


class SourceDefinition(BaseModel):
    name: str
    url: HttpUrl
    series: str
    score: int = 50
    kind: str = "news"
    tags: list[str] = Field(default_factory=list)
    default_mode: str = "single_story"
    allow_keywords: list[str] = Field(default_factory=list)
    block_keywords: list[str] = Field(default_factory=list)


class SourcePolicy(BaseModel):
    allowed_series: list[str] = Field(default_factory=lambda: ["f1", "nascar"])
    blocked_series: list[str] = Field(default_factory=lambda: ["motogp", "moto2", "moto3"])
    min_score: int = 0
    sources: list[SourceDefinition] = Field(default_factory=list)


def load_source_policy(settings: Settings) -> SourcePolicy:
    path = settings.sources_config_path
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return SourcePolicy.model_validate(data)

    return SourcePolicy(
        allowed_series=settings.allowed_series,
        blocked_series=settings.blocked_series,
        min_score=settings.min_source_score,
        sources=[
            SourceDefinition(
                name=url,
                url=url,
                series="f1",
                score=70,
                kind="news",
                tags=["fallback"],
            )
            for url in settings.news_feeds
        ],
    )


def keyword_matches(text: str, keywords: list[str]) -> bool:
    haystack = text.lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def source_from_raw(raw: dict[str, Any]) -> SourceDefinition:
    return SourceDefinition.model_validate(raw)
