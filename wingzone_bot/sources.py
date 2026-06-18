from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp
import feedparser

from .config import Settings
from .models import NewsItem
from .source_config import SourceDefinition, keyword_matches, load_source_policy
from .text import clean_feed_text, normalize_spaces

LOGGER = logging.getLogger(__name__)


async def fetch_news_items(settings: Settings) -> list[NewsItem]:
    policy = load_source_policy(settings)
    active_sources = [
        source
        for source in policy.sources
        if source.score >= policy.min_score
        and source.series.lower() in policy.allowed_series
        and source.series.lower() not in policy.blocked_series
    ]
    headers = {"User-Agent": settings.user_agent}
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        tasks = [fetch_feed(session, source, policy.blocked_series) for source in active_sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    items: list[NewsItem] = []
    for result in results:
        if isinstance(result, Exception):
            LOGGER.warning("feed fetch failed: %s", result)
            continue
        items.extend(result)

    items.sort(
        key=lambda item: (
            item.published_at or datetime.min.replace(tzinfo=timezone.utc),
            item.source_score,
        ),
        reverse=True,
    )
    return dedupe_items(items)


async def fetch_feed(
    session: aiohttp.ClientSession,
    source_def: SourceDefinition,
    blocked_series: list[str] | None = None,
) -> list[NewsItem]:
    url = str(source_def.url)
    async with session.get(url) as response:
        body = await response.read()
        if response.status >= 400:
            raise RuntimeError(f"{url} returned HTTP {response.status}")

    parsed = feedparser.parse(body)
    source = normalize_spaces(source_def.name or parsed.feed.get("title") or url)
    items: list[NewsItem] = []

    for entry in parsed.entries:
        title = normalize_spaces(entry.get("title", ""))
        link = entry.get("link") or ""
        if not title or not link:
            continue

        summary = clean_feed_text(entry.get("summary") or entry.get("description") or "")
        combined = " ".join([title, summary, link]).lower()
        if should_skip_entry(combined, source_def, blocked_series or []):
            continue

        published_at = parse_entry_date(entry)
        item_id = stable_item_id(link, title)
        items.append(
            NewsItem(
                id=item_id,
                source=source,
                title=title,
                url=link,
                summary=summary,
                published_at=published_at,
                series=source_def.series.lower(),
                source_score=source_def.score,
                source_kind=source_def.kind,
                source_tags=source_def.tags,
                editorial_mode=classify_editorial_mode(title, summary, source_def),
            )
        )

    return items


def stable_item_id(url: str, title: str) -> str:
    raw = f"{url.strip()}::{title.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_entry_date(entry: dict[str, Any]) -> datetime | None:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (TypeError, ValueError):
            continue
    return None


def dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    deduped: list[NewsItem] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        deduped.append(item)
    return deduped


def should_skip_entry(text: str, source_def: SourceDefinition, blocked_series: list[str]) -> bool:
    if keyword_matches(text, source_def.block_keywords):
        return True
    if keyword_matches(text, blocked_series):
        return True
    if source_def.allow_keywords and not keyword_matches(text, source_def.allow_keywords):
        return True
    return False


def classify_editorial_mode(title: str, summary: str, source_def: SourceDefinition) -> str:
    if source_def.series.lower() == "nascar":
        return "nascar"

    text = f"{title} {summary}".lower()
    breaking_keywords = [
        "breaking",
        "confirmed",
        "announces",
        "announced",
        "penalty",
        "ban",
        "investigation",
        "under investigation",
        "signs",
        "leaves",
        "joins",
        "sacked",
        "replaced",
    ]
    rumor_keywords = [
        "rumour",
        "rumor",
        "report",
        "linked",
        "could",
        "set to",
        "silly season",
        "eyeballing",
    ]

    if keyword_matches(text, breaking_keywords):
        return "breaking"
    if source_def.kind == "rumor" or keyword_matches(text, rumor_keywords):
        return "single_story"
    return source_def.default_mode
