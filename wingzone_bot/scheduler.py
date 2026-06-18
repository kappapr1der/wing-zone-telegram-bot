from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .composer import create_composer
from .config import Settings
from .models import NewsItem
from .sources import fetch_news_items
from .storage import Storage
from .telegram import TelegramClient
from .text import format_draft_list, format_review_message

LOGGER = logging.getLogger(__name__)


class WingZoneApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = Storage(settings.database_path)
        self.telegram = TelegramClient(settings)
        self.composer = create_composer(settings)
        self._update_offset: int | None = None

    async def run_once(self, dry_run: bool = False) -> None:
        self.storage.initialize()
        items = await fetch_news_items(self.settings)
        new_count = 0

        for item in items:
            if new_count >= self.settings.max_items_per_run:
                break
            if not dry_run and self.storage.is_seen(item.id):
                continue

            draft_text = await self.composer.compose(item)
            new_count += 1

            if dry_run:
                print(f"\n--- dry-run draft #{new_count}: {item.title} ---\n{draft_text}\n")
                continue

            self.storage.mark_seen(item)
            draft_id = self.storage.save_draft(item, draft_text)

            if self.settings.auto_publish:
                await self.publish_draft(draft_id)
            else:
                await self.send_review(draft_id)

        LOGGER.info("run_once complete: %s new drafts", new_count)

    async def run_worker(self) -> None:
        self.storage.initialize()
        LOGGER.info("starting worker; check interval=%ss", self.settings.check_interval_seconds)

        while True:
            started = time.monotonic()
            await self.run_once(dry_run=False)

            while time.monotonic() - started < self.settings.check_interval_seconds:
                await self.poll_updates_once(timeout=20)

    async def poll_updates_once(self, timeout: int = 20) -> None:
        if not self.settings.telegram_bot_token:
            await asyncio.sleep(min(timeout, 5))
            return

        updates = await self.telegram.get_updates(offset=self._update_offset, timeout=timeout)
        for update in updates:
            self._update_offset = max(self._update_offset or 0, update["update_id"] + 1)
            await self.handle_update(update)

    async def send_review(self, draft_id: int) -> None:
        if not self.settings.telegram_review_chat_id:
            LOGGER.warning("TELEGRAM_REVIEW_CHAT_ID is empty; draft #%s saved but not sent", draft_id)
            return

        draft = self.storage.get_draft(draft_id)
        if draft is None:
            return

        await self.telegram.send_message(
            self.settings.telegram_review_chat_id,
            format_review_message(draft),
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "Publish", "callback_data": f"publish:{draft.id}"},
                        {"text": "Drop", "callback_data": f"drop:{draft.id}"},
                    ]
                ]
            },
        )
        self.storage.set_draft_status(draft_id, "sent_review")

    async def create_manual_draft(self, note: str) -> int:
        item = NewsItem(
            id=f"manual:{int(time.time())}",
            source="manual",
            title=note[:120],
            url="",
            summary=note,
        )
        draft_text = await self.composer.compose(item)
        draft_id = self.storage.save_draft(item, draft_text)
        await self.send_review(draft_id)
        return draft_id

    async def publish_draft(self, draft_id: int) -> None:
        if not self.settings.telegram_channel_id:
            raise RuntimeError("TELEGRAM_CHANNEL_ID is required to publish")
        draft = self.storage.get_draft(draft_id)
        if draft is None:
            raise RuntimeError(f"Draft #{draft_id} not found")

        await self.telegram.send_message(self.settings.telegram_channel_id, draft.text)
        self.storage.set_draft_status(draft_id, "published")
        LOGGER.info("published draft #%s", draft_id)

    async def drop_draft(self, draft_id: int) -> None:
        self.storage.set_draft_status(draft_id, "dropped")
        LOGGER.info("dropped draft #%s", draft_id)

    async def send_test(self, text: str) -> None:
        chat_id = self.settings.telegram_review_chat_id or self.settings.telegram_channel_id
        if not chat_id:
            raise RuntimeError("Set TELEGRAM_REVIEW_CHAT_ID or TELEGRAM_CHANNEL_ID")
        await self.telegram.send_message(chat_id, text)

    async def handle_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            await self.handle_callback(update["callback_query"])
            return

        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        if not self._is_admin_message(message):
            return

        text = message.get("text") or ""
        if not text.startswith("/"):
            return

        chat_id = str(message["chat"]["id"])
        command, args = parse_command(text)

        try:
            if command == "/ping":
                await self.telegram.send_message(chat_id, "жив, шины прогреты")
            elif command == "/help":
                await self.telegram.send_message(chat_id, command_help())
            elif command == "/once":
                await self.telegram.send_message(chat_id, "собираю свежак")
                await self.run_once(dry_run=False)
            elif command == "/draft":
                draft_id = await self.create_manual_draft(require_text(args))
                await self.telegram.send_message(chat_id, f"draft #{draft_id} sent to review")
            elif command == "/drafts":
                drafts = self.storage.recent_drafts(limit=10)
                await self.telegram.send_message(chat_id, format_draft_list(drafts))
            elif command == "/post":
                draft_id = require_draft_id(args)
                await self.publish_draft(draft_id)
                await self.telegram.send_message(chat_id, f"draft #{draft_id} published")
            elif command == "/drop":
                draft_id = require_draft_id(args)
                await self.drop_draft(draft_id)
                await self.telegram.send_message(chat_id, f"draft #{draft_id} dropped")
        except Exception as exc:
            LOGGER.exception("command failed: %s", command)
            await self.telegram.send_message(chat_id, f"command failed: {exc}")

    async def handle_callback(self, callback: dict[str, Any]) -> None:
        user_id = callback.get("from", {}).get("id")
        callback_id = callback.get("id")
        if not self._is_admin_user(user_id):
            if callback_id:
                await self.telegram.answer_callback_query(callback_id, "Not allowed")
            return

        data = callback.get("data", "")
        action, _, raw_id = data.partition(":")
        if not raw_id.isdigit():
            return
        draft_id = int(raw_id)

        if action == "publish":
            await self.publish_draft(draft_id)
            answer = f"Published #{draft_id}"
        elif action == "drop":
            await self.drop_draft(draft_id)
            answer = f"Dropped #{draft_id}"
        else:
            return

        if callback_id:
            await self.telegram.answer_callback_query(callback_id, answer)

        message = callback.get("message")
        if message:
            await self.telegram.edit_message_reply_markup(
                chat_id=message["chat"]["id"],
                message_id=message["message_id"],
                reply_markup={"inline_keyboard": []},
            )

    def _is_admin_message(self, message: dict[str, Any]) -> bool:
        user_id = message.get("from", {}).get("id")
        if self._is_admin_user(user_id):
            return True
        chat_id = message.get("chat", {}).get("id")
        LOGGER.warning("ignored non-admin update from user=%s chat=%s", user_id, chat_id)
        return False

    def _is_admin_user(self, user_id: Any) -> bool:
        if user_id is None:
            return False
        return int(user_id) in self.settings.admin_user_ids


def parse_command(text: str) -> tuple[str, str]:
    parts = text.strip().split(maxsplit=1)
    command = parts[0].split("@", maxsplit=1)[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return command, args


def require_draft_id(args: str) -> int:
    raw = args.strip().split(maxsplit=1)[0] if args.strip() else ""
    if not raw.isdigit():
        raise ValueError("draft id is required")
    return int(raw)


def require_text(args: str) -> str:
    text = args.strip()
    if not text:
        raise ValueError("text is required")
    return text


def command_help() -> str:
    return "\n".join(
        [
            "/ping - check bot",
            "/once - fetch news now",
            "/draft <text> - create live draft from a manual note",
            "/drafts - show recent drafts",
            "/post <id> - publish draft",
            "/drop <id> - drop draft",
        ]
    )
