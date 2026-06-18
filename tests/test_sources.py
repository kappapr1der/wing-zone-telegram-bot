from pathlib import Path

from wingzone_bot.config import Settings
from wingzone_bot.source_config import SourceDefinition, load_source_policy
from wingzone_bot.sources import classify_editorial_mode, should_skip_entry


def test_load_source_policy_reads_yaml() -> None:
    settings = Settings(sources_config_path=Path("sources.yml"))
    policy = load_source_policy(settings)

    assert "f1" in policy.allowed_series
    assert "nascar" in policy.allowed_series
    assert "motogp" in policy.blocked_series
    assert any(source.series == "nascar" for source in policy.sources)


def test_should_skip_motogp_item_from_f1_feed() -> None:
    source = SourceDefinition(
        name="Motorsport F1",
        url="https://www.motorsport.com/rss/f1/news/",
        series="f1",
        score=80,
        block_keywords=["motogp", "/motogp/"],
    )

    assert should_skip_entry("Fabio Quartararo still wants F1 test /motogp/news/", source, ["motogp"])


def test_classify_nascar_mode() -> None:
    source = SourceDefinition(
        name="RACER NASCAR",
        url="https://racer.com/category/nascar/feed/",
        series="nascar",
        score=85,
    )

    assert classify_editorial_mode("Cup restart chaos", "", source) == "nascar"


def test_classify_breaking_mode() -> None:
    source = SourceDefinition(
        name="RACER F1",
        url="https://racer.com/category/f1/feed/",
        series="f1",
        score=85,
    )

    assert classify_editorial_mode("Ferrari announces driver change", "", source) == "breaking"
