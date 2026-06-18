from wingzone_bot.text import clean_feed_text, normalize_spaces, telegram_chunks


def test_normalize_spaces_compacts_whitespace() -> None:
    assert normalize_spaces("  hello \n\n  world\t ") == "hello world"


def test_telegram_chunks_preserves_short_text() -> None:
    assert telegram_chunks("short", limit=10) == ["short"]


def test_telegram_chunks_splits_on_paragraphs() -> None:
    text = "aaa\n\nbbb\n\nccc"
    assert telegram_chunks(text, limit=8) == ["aaa\n\nbbb", "ccc"]


def test_clean_feed_text_strips_html() -> None:
    assert clean_feed_text("A<br />B &amp; C <a href='x'>Keep reading</a>") == "A B & C"


def test_clean_feed_text_repairs_missing_sentence_space() -> None:
    assert clean_feed_text("Critics.Hamilton won.") == "Critics. Hamilton won."
