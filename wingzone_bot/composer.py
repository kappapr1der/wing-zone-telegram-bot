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

RACING_GLOSSARY = """
F1 vocabulary:
- race pace -> гоночный темп
- qualifying pace -> темп в квалификации
- long run -> длинный отрезок
- stint -> стинт / отрезок
- dirty air -> грязный воздух
- clean air -> чистый воздух
- undercut -> андеркат / подрезка
- overcut -> оверкат
- power unit -> силовая установка
- floor upgrade -> обновление днища
- parc ferme -> закрытый парк
- stewards -> стюарды
- race control -> дирекция гонки
- safety car -> сейфти-кар
- silly season -> трансферная возня / сезон слухов

NASCAR vocabulary:
- car -> машина
- restart -> рестарт
- stage racing -> гонка по стадиям
- drafting -> слипстрим / драфтинг
- playoff bubble -> граница плей-офф
- crew chief -> крю-чиф
- pit road -> пит-роуд
- caution -> желтые флаги / caution
""".strip()


class Composer(Protocol):
    async def compose(self, item: NewsItem) -> str:
        """Return a Telegram-ready draft for a news item."""


class TemplateComposer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def compose(self, item: NewsItem) -> str:
        title = normalize_spaces(item.title)
        summary = normalize_spaces(item.summary)
        if item.editorial_mode == "breaking":
            return self._breaking(item, title, summary)
        if item.editorial_mode == "live":
            return self._live(item, title, summary)
        return self._single_story(item, title, summary)

    def _single_story(self, item: NewsItem, title: str, summary: str) -> str:
        context = summary or "Подробностей пока немного, так что держимся фактов и не изображаем телеметрию из кофейной гущи."
        label = "NASCAR" if item.series == "nascar" else "F1"
        return (
            f"{title}\n\n"
            f"Что случилось: {context}\n\n"
            f"Почему это важно: для {label} это тот самый тип новости, где главное не только заголовок, "
            "но и последствия для темпа, состава, стратегии или общей нервной системы паддока.\n\n"
            f"{self._punchline(item)}\n\n"
            f"{item.url}"
        ).strip()

    def _breaking(self, item: NewsItem, title: str, summary: str) -> str:
        details = summary or "детали еще подъезжают, но новость уже стоит держать на радаре"
        return (
            f"Срочно по гоночной линии: {title}\n\n"
            f"{details}\n\n"
            "Коротко: фиксируем факт, ждем развитие и не делаем вид, что уже видели внутренний чат команды.\n\n"
            f"{item.url}"
        ).strip()

    def _live(self, item: NewsItem, title: str, summary: str) -> str:
        note = summary or title
        return f"{note}\n\n{self._punchline(item)}".strip()

    def _punchline(self, item: NewsItem) -> str:
        calm = [
            "Где-то в зоне крыла сохраняем рабочий скепсис и делаем вид, что это все абсолютно нормально.",
            "Очень гоночная ситуация: вроде новость, а вроде очередная серия сезона, который никто не заказывал.",
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

        payload: dict[str, Any] = {
            "model": self.settings.openai_model,
            "input": [
                {"role": "developer", "content": self._developer_prompt()},
                {"role": "user", "content": self._build_user_prompt(item)},
            ],
            "max_output_tokens": 720,
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
            "Пиши в традиции хорошего русскоязычного гоночного комментария: легко, живо, информативно, "
            "с иронией, но без токсичности. Не копируй конкретного комментатора и не имитируй человека один-в-один. "
            "Переводи не дословно, а редакторски: нормальным русским гоночным языком, с контекстом и профессиональными терминами. "
            "Не калькируй английские заголовки. Не выдумывай факты, цитаты, штрафы, позиции, тайминги или инсайды. "
            "Если это слух, подавай как слух: 'пишут', 'по данным', 'если подтвердится', 'пока это уровень паддок-дыма'. "
            "Не трави пилотов, команды, журналистов и болельщиков по защищенным признакам. Не пиши дисклеймеры. "
            f"Глоссарий:\n{RACING_GLOSSARY}"
        )

    def _build_user_prompt(self, item: NewsItem) -> str:
        mode_instruction = mode_instruction_for(item)
        return (
            "Сделай Telegram-пост по новости.\n\n"
            f"Режим подачи: {item.editorial_mode}\n"
            f"Серия: {item.series}\n"
            f"Тип источника: {item.source_kind}\n"
            f"Score источника: {item.source_score}\n"
            f"Теги: {', '.join(item.source_tags) or 'нет'}\n"
            f"Источник: {item.source}\n"
            f"Заголовок: {item.title}\n"
            f"Кратко: {item.summary or 'нет описания'}\n"
            f"Ссылка: {item.url}\n\n"
            f"{mode_instruction}"
        )

    @staticmethod
    def _with_source(text: str, url: str) -> str:
        clean = text.strip()
        if url and url not in clean:
            clean = f"{clean}\n\n{url}"
        return clean


def mode_instruction_for(item: NewsItem) -> str:
    if item.editorial_mode == "breaking":
        return (
            "Формат breaking: 1-2 коротких абзаца. Сначала факт, потом почему это важно. "
            "Без долгой раскачки и без лишнего стендапа."
        )
    if item.editorial_mode == "live":
        return (
            "Формат live: короткая реакция в моменте. Можно иронично, но главное - ясно и быстро. "
            "Не добавляй фактов, которых нет во входной заметке."
        )
    if item.editorial_mode == "nascar":
        return (
            "Формат NASCAR: отдельный американский вайб. Используй NASCAR-термины естественно: рестарт, "
            "caution, пит-роуд, крю-чиф, stage racing, drafting. Не называй машину болидом."
        )
    return (
        "Формат single_story: одна вкусная новость на русском. Структура свободная, но обязательно: "
        "что случилось, почему это важно, какой контекст у темы, и легкая ироничная финальная нота. "
        "Не делай сухой дайджест и не растягивай воду."
    )


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
