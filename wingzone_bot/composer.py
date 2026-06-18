from __future__ import annotations

import json
import logging
from hashlib import sha256
from typing import Any, Protocol

import aiohttp

from .config import Settings
from .models import NewsItem
from .text import normalize_spaces

LOGGER = logging.getLogger(__name__)


class Composer(Protocol):
    async def compose(self, item: NewsItem) -> str:
        """Return a Telegram-ready draft for a news item."""


class TemplateComposer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def compose(self, item: NewsItem) -> str:
        title = normalize_spaces(item.title)
        summary = normalize_spaces(item.summary)
        lead = f"{title}"
        if summary:
            lead = f"{lead}\n\n{summary}"

        punchline = self._punchline(item)

        return f"{lead}\n\n{punchline}\n\n{item.url}".strip()

    def _punchline(self, item: NewsItem) -> str:
        calm = [
            "Где-то в зоне крыла сохраняем рабочий скепсис и делаем вид, что это все абсолютно нормально.",
            "Очень автоспортивная ситуация: вроде новость, а вроде очередная серия сериала, который никто не заказывал.",
            "Фиксируем, киваем, стараемся не смотреть на это слишком осуждающе. Получается средне.",
        ]
        spicy = [
            "Ну конечно. Потому что простые сюжеты в автоспорте, видимо, запретили регламентом.",
            "Где-то в зоне крыла это уже проходит по категории: красиво, нервно, слегка абсурдно.",
            "Официально сохраняем серьезное лицо. Неофициально - ну вы поняли.",
        ]
        pool = spicy if self.settings.voice_intensity >= 4 else calm
        index = int(sha256(item.id.encode("utf-8")).hexdigest(), 16) % len(pool)
        return pool[index]


class OpenAIComposer:
    def __init__(self, settings: Settings, fallback: Composer | None = None) -> None:
        self.settings = settings
        self.fallback = fallback or TemplateComposer(settings)

    async def compose(self, item: NewsItem) -> str:
        if not self.settings.openai_api_key:
            return await self.fallback.compose(item)

        prompt = self._build_user_prompt(item)
        payload: dict[str, Any] = {
            "model": self.settings.openai_model,
            "input": [
                {"role": "developer", "content": self._developer_prompt()},
                {"role": "user", "content": prompt},
            ],
            "max_output_tokens": 420,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.settings.openai_timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.settings.openai_base_url.rstrip('/')}/responses",
                    headers={
                        "Authorization": f"Bearer {self.settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise RuntimeError(f"OpenAI API error {response.status}: {body[:500]}")
                    data = json.loads(body)
                    text = extract_response_text(data)
                    if not text:
                        raise RuntimeError("OpenAI API returned no output text")
                    return self._with_source(text, item.url)
        except Exception:
            LOGGER.exception("OpenAI composition failed; falling back to template")
            return await self.fallback.compose(item)

    def _developer_prompt(self) -> str:
        profanity = (
            "редкая разговорная грубость допустима, но не делай ее основой стиля"
            if self.settings.allow_profanity
            else "мат и грубую разговорность не использовать"
        )
        return (
            f"Ты редактор Telegram-канала '{self.settings.channel_name}'. "
            f"Голос канала: {self.settings.channel_voice}. "
            f"Интенсивность: {self.settings.voice_intensity}/5; {profanity}. "
            "Пиши по-русски. Не выдумывай факты, цитаты, штрафы, позиции, тайминги или инсайды. "
            "Не трави людей и группы людей. Не пиши дисклеймеры. "
            "Сделай 1-3 коротких абзаца в стиле ироничного live-комментария, пригодных для Telegram."
        )

    def _build_user_prompt(self, item: NewsItem) -> str:
        return (
            "Сделай пост по новости.\n\n"
            f"Источник: {item.source}\n"
            f"Заголовок: {item.title}\n"
            f"Кратко: {item.summary or 'нет описания'}\n"
            f"Ссылка: {item.url}\n"
        )

    @staticmethod
    def _with_source(text: str, url: str) -> str:
        clean = text.strip()
        if url and url not in clean:
            clean = f"{clean}\n\n{url}"
        return clean


def extract_response_text(data: dict[str, Any]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    parts: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(part.strip() for part in parts if part.strip())


def create_composer(settings: Settings) -> Composer:
    return OpenAIComposer(settings)
