from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

import aiohttp

from .config import Settings
from .models import Draft, NewsItem
from .text import normalize_spaces

LOGGER = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt_file(name: str) -> str:
    path = PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        LOGGER.warning("Prompt file is missing: %s", path)
        return ""


CHANNEL_VOICE_GUIDE = load_prompt_file("channel_voice.md")
RACING_GLOSSARY = load_prompt_file("glossary.md")


class Composer(Protocol):
    async def compose(self, item: NewsItem) -> str:
        """Return a Telegram-ready draft for a news item."""

    async def revise(self, draft: Draft, action: DraftRevisionAction) -> str:
        """Return an edited version of an existing draft."""


@dataclass(frozen=True)
class DraftRevisionAction:
    key: str
    label: str
    instruction: str
    requires_model: bool = True


DRAFT_REVISION_ACTIONS: dict[str, DraftRevisionAction] = {
    "rewrite": DraftRevisionAction(
        key="rewrite",
        label="Rewrite",
        instruction=(
            "Перепиши черновик вкуснее и естественнее для канала: живее, плотнее, без воды, "
            "с теми же фактами и без новых непроверенных деталей."
        ),
    ),
    "shorter": DraftRevisionAction(
        key="shorter",
        label="Shorter",
        instruction="Сократи черновик примерно на треть, оставив главное, источник и нерв новости.",
        requires_model=False,
    ),
    "context": DraftRevisionAction(
        key="context",
        label="Context",
        instruction=(
            "Добавь контекст: почему эта новость важна для F1/NASCAR, команд, гонщиков или гонки. "
            "Не добавляй фактов, которых нет в черновике."
        ),
    ),
    "irony": DraftRevisionAction(
        key="irony",
        label="Irony",
        instruction=(
            "Сделай тон чуть более ироничным и разговорным, но не токсичным. "
            "Факты, осторожность к слухам и ссылка должны сохраниться."
        ),
    ),
}


def get_draft_revision_action(key: str) -> DraftRevisionAction | None:
    return DRAFT_REVISION_ACTIONS.get(key)


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

    async def revise(self, draft: Draft, action: DraftRevisionAction) -> str:
        if action.key == "shorter":
            return shorten_draft_text(draft.text, draft.url)
        return draft.text

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


def shorten_draft_text(text: str, source_url: str = "", max_chars: int = 900) -> str:
    clean = text.strip()
    if len(clean) <= max_chars:
        return clean

    body, source = split_source_link(clean, source_url)
    paragraphs = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]
    target = max(320, int(max_chars * 0.82))
    selected: list[str] = []

    for paragraph in paragraphs:
        candidate = paragraph if not selected else "\n\n".join([*selected, paragraph])
        if len(candidate) > target:
            break
        selected.append(paragraph)

    shortened = "\n\n".join(selected).strip()
    if not shortened or len(shortened) > target:
        shortened = trim_at_word_boundary(body, target)

    if source and source not in shortened:
        shortened = f"{shortened}\n\n{source}"
    return shortened.strip()


def split_source_link(text: str, source_url: str) -> tuple[str, str]:
    source = source_url.strip()
    body = text.strip()
    if source and source in body:
        body = body.replace(source, "").strip()
    return body, source


def trim_at_word_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text.strip()
    trimmed = text[:limit].rsplit(" ", maxsplit=1)[0].strip()
    return f"{trimmed}..." if trimmed else f"{text[:limit].strip()}..."


class OpenAIComposer:
    def __init__(self, settings: Settings, fallback: Composer | None = None) -> None:
        self.settings = settings
        self.fallback = fallback or TemplateComposer(settings)

    async def compose(self, item: NewsItem) -> str:
        if not self.settings.openai_api_key:
            return await self.fallback.compose(item)

        try:
            text = await self._request_response_text(self._build_user_prompt(item), max_output_tokens=720)
            return self._with_source(text, item.url)
        except Exception:
            LOGGER.exception("OpenAI composition failed; falling back to template")
            return await self.fallback.compose(item)

    async def revise(self, draft: Draft, action: DraftRevisionAction) -> str:
        if not self.settings.openai_api_key:
            return await self.fallback.revise(draft, action)

        try:
            text = await self._request_response_text(
                self._build_revision_prompt(draft, action),
                max_output_tokens=650,
            )
            return self._with_source(text, draft.url)
        except Exception:
            LOGGER.exception("OpenAI revision failed; falling back to template")
            return await self.fallback.revise(draft, action)

    async def _request_response_text(self, user_prompt: str, max_output_tokens: int) -> str:
        payload: dict[str, Any] = {
            "model": self.settings.openai_model,
            "input": [
                {"role": "developer", "content": self._developer_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            "max_output_tokens": max_output_tokens,
        }
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
                return text

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
            "Не копируй конкретного комментатора и не имитируй человека один-в-один. Не пиши дисклеймеры.\n\n"
            f"Гайд по голосу:\n{CHANNEL_VOICE_GUIDE}\n\n"
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

    def _build_revision_prompt(self, draft: Draft, action: DraftRevisionAction) -> str:
        return (
            "Перепиши уже готовый Telegram-черновик.\n\n"
            f"Кнопка редактора: {action.label}\n"
            f"Задача: {action.instruction}\n"
            f"Заголовок/тема: {draft.title}\n"
            f"Ссылка источника: {draft.url or 'нет'}\n\n"
            "Правила:\n"
            "- сохрани все факты и уровень уверенности исходного черновика;\n"
            "- не добавляй цитаты, цифры, штрафы, тайминги, инсайды или новые утверждения;\n"
            "- если это слух, оставь подачу как слух, а не как подтвержденный факт;\n"
            "- верни только готовый текст поста без пояснений редактора;\n"
            "- не удаляй ссылку на источник, если она была в черновике.\n\n"
            f"Черновик:\n<<<\n{draft.text}\n>>>"
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
