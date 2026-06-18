import asyncio

import pytest

from wingzone_bot.composer import DRAFT_REVISION_ACTIONS, TemplateComposer
from wingzone_bot.config import Settings
from wingzone_bot.models import Draft, NewsItem
from wingzone_bot.scheduler import WingZoneApp, review_keyboard


def test_review_keyboard_includes_editor_actions() -> None:
    markup = review_keyboard(42)
    callback_data = [button["callback_data"] for row in markup["inline_keyboard"] for button in row]

    assert "publish:42" in callback_data
    assert "drop:42" in callback_data
    assert "edit:42:rewrite" in callback_data
    assert "edit:42:shorter" in callback_data
    assert "edit:42:context" in callback_data
    assert "edit:42:irony" in callback_data


def test_review_keyboard_can_disable_editor_actions() -> None:
    markup = review_keyboard(42, editor_buttons_enabled=False)
    callback_data = [button["callback_data"] for row in markup["inline_keyboard"] for button in row]

    assert callback_data == ["publish:42", "drop:42"]


def test_template_shorter_revision_preserves_source_url() -> None:
    source_url = "https://example.com/f1/story"
    text = (
        "Opening paragraph with the main racing news. " * 10
        + "\n\n"
        + "Second paragraph with extra context about pace, strategy and paddock noise. " * 10
        + "\n\n"
        + source_url
    )
    draft = Draft(
        id=1,
        item_id="item-1",
        title="F1 story",
        url=source_url,
        text=text,
        status="sent_review",
        created_at="2026-06-18T00:00:00+00:00",
        updated_at="2026-06-18T00:00:00+00:00",
    )

    revised = asyncio.run(TemplateComposer(Settings()).revise(draft, DRAFT_REVISION_ACTIONS["shorter"]))

    assert len(revised) < len(text)
    assert source_url in revised


def test_model_backed_revision_requires_openai_key(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "wingzone.sqlite3",
        admin_user_ids=[123],
        openai_api_key=None,
    )
    app = WingZoneApp(settings)
    app.storage.initialize()
    draft_id = app.storage.save_draft(
        NewsItem(id="item-1", source="test", title="F1 story", url="https://example.com/f1/story"),
        "Short factual draft.\n\nhttps://example.com/f1/story",
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        asyncio.run(app.revise_draft(draft_id, "rewrite"))
