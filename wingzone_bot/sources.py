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
from .text import clean_feed_text, normalize_spaces

LOGGER = logging.getLogger(__name__)


async def fetch_news_items(settings: Settings) -> list[NewsItem]:
    headers = {"User-Agent": settings.user_agent}
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        tasks = [fetch_feed(session, url) for url in settings.news_feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    items: list[NewsItem] = []
    for result in results:
        if isinstance(result, Exception):
            LOGGER.warning("feed fetch failed: %s", result)
            continue
        items.extend(result)

    items.sort(key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return dedupe_items(items)


async def fetch_feed(session: aiohttp.ClientSession, url: str) -> list[NewsItem]:
    async with session.get(url) as response:
        body = await response.read()
        if response.status >= 400:
            raise RuntimeError(f"{url} returned HTTP {response.status}")

    parsed = feedparser.parse(body)
    source = normalize_spaces(parsed.feed.get("title") or url)
    items: list[NewsItem] = []

    for entry in parsed.entries:
        title = normalize_spaces(entry.get("title", ""))
        link = entry.get("link") or ""
        if not title or not link:
            continue

        summary = clean_feed_text(entry.get("summary") or entry.get("description") or "")
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
