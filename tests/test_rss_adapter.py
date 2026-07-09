"""Bloomberg RSS adapter: recorded feed parses into schema-valid, link-only rows."""

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.ingestion import BloombergRssAdapter
from sovereign_monitor.registry import Registry
from tests.conftest import FIXTURES_DIRECTORY


def _run_fixture(registry: Registry, settings: Settings) -> pd.DataFrame:
    payload = (FIXTURES_DIRECTORY / "bloomberg_markets_news.xml").read_bytes()
    adapter = BloombergRssAdapter(registry.sources["bloomberg_rss"], settings)
    result = adapter.run(payload=payload)
    assert not result.quarantined
    assert result.rows_in_batch > 0
    return pd.read_parquet(settings.data_directory / "curated" / "news_items.parquet")


def test_recorded_feed_lands_in_curated_store(registry: Registry, settings: Settings) -> None:
    curated = _run_fixture(registry, settings)
    assert len(curated) > 0
    assert curated["url_hash"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert curated["url"].str.startswith("http").all()
    assert (curated["outlet"] == "Bloomberg").all()


def test_no_publisher_content_is_stored(registry: Registry, settings: Settings) -> None:
    # link_only licensing: our summary slot stays empty at ingestion time, and no
    # column may carry the feed's description/body text.
    curated = _run_fixture(registry, settings)
    assert curated["summary_own"].isna().all()
    assert "description" not in curated.columns
    assert "summary" not in curated.columns


def test_raw_payload_is_kept_for_reproducibility(registry: Registry, settings: Settings) -> None:
    _run_fixture(registry, settings)
    raw_files = list((settings.data_directory / "raw" / "bloomberg_rss").glob("*.xml"))
    assert len(raw_files) == 1
