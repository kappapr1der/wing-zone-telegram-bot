from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str | None = None
    telegram_channel_id: str | None = None
    telegram_review_chat_id: str | None = None
    admin_user_ids: list[int] = Field(default_factory=list)

    auto_publish: bool = False
    check_interval_seconds: int = 300
    max_items_per_run: int = 5
    post_cooldown_minutes: int = 10

    channel_name: str = "где-то в зоне крыла"
    channel_voice: str = (
        "Живой русскоязычный F1/NASCAR-канал: иронично, саркастично, смешно, "
        "с ощущением лайв-реакции, "
        "но без травли, выдуманных фактов и занудства."
    )
    voice_intensity: int = 3
    allow_profanity: bool = False

    news_feeds: list[str] = Field(
        default_factory=lambda: [
            "https://racer.com/category/f1/feed/",
            "https://racer.com/category/nascar/feed/",
            "https://www.motorsport.com/rss/f1/news/",
        ]
    )

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.2"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: int = 45

    database_path: Path = Path("data/wingzone.sqlite3")
    log_level: str = "INFO"
    user_agent: str = "wing-zone-telegram-bot/0.1"

    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: Any) -> list[int]:
        return [int(part) for part in _split_csv(value)]

    @field_validator("news_feeds", mode="before")
    @classmethod
    def parse_news_feeds(cls, value: Any) -> list[str]:
        return _split_csv(value)

    @field_validator("voice_intensity")
    @classmethod
    def clamp_voice_intensity(cls, value: int) -> int:
        return min(5, max(1, value))
