from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .config import Settings
from .text import telegram_chunks

LOGGER = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def base_url(self) -> str:
        if not self.settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"

    async def request(self, method: str, payload: dict[str, Any]) -> Any:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/{method}", json=payload) as response:
                data = await response.json(content_type=None)
                if response.status >= 400 or not data.get("ok"):
                    raise RuntimeError(f"Telegram API error {response.status}: {data}")
                return data.get("result")

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool = False,
    ) -> None:
        chunks = telegram_chunks(text)
        for index, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": disable_web_page_preview,
            }
            if reply_markup and index == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            await self.request("sendMessage", payload)

    async def send_photo(
        self,
        chat_id: str | int,
        photo: str,
        caption: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "photo": photo}
        if caption:
            payload["caption"] = caption[:1024]
        if reply_markup:
            payload["reply_markup"] = reply_markup
        await self.request("sendPhoto", payload)

    async def get_updates(self, offset: int | None = None, timeout: int = 20) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "edited_message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        result = await self.request("getUpdates", payload)
        return list(result or [])

    async def answer_callback_query(self, callback_query_id: str, text: str) -> None:
        await self.request(
            "answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": text},
        )

    async def edit_message_reply_markup(
        self,
        chat_id: str | int,
        message_id: int,
        reply_markup: dict[str, Any],
    ) -> None:
        await self.request(
            "editMessageReplyMarkup",
            {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup},
        )
