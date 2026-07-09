"""News-layer adapters: recorded feeds parse into schema-valid, link-only rows."""

import json

import pandas as pd
import pytest

from sovereign_monitor.configuration import Settings
from sovereign_monitor.ingestion import (
    CentralBankPressAdapter,
    GdeltAdapter,
    IgoPressAdapter,
    IngestionRuntimeError,
    OccrpAdapter,
    SourceAdapter,
)
from sovereign_monitor.registry import Registry
from tests.conftest import FIXTURES_DIRECTORY


def _envelope(outlet: str, fixture_name: str) -> bytes:
    """Wrap a recorded feed body the way MultiFeedRssAdapter.fetch does."""
    body = (FIXTURES_DIRECTORY / fixture_name).read_text(encoding="utf-8")
    return json.dumps([{"outlet": outlet, "url": "https://recorded.test", "body": body}]).encode(
        "utf-8"
    )


MULTI_FEED_CASES = [
    (OccrpAdapter, "OCCRP", "occrp_feed.xml"),
    (CentralBankPressAdapter, "Reserve Bank of India", "rbi_press.xml"),
    (IgoPressAdapter, "Asian Development Bank", "adb_news.xml"),
]


@pytest.mark.parametrize(("adapter_class", "outlet", "fixture_name"), MULTI_FEED_CASES)
def test_multi_feed_adapters_land_link_only_rows(
    adapter_class: type[SourceAdapter],
    outlet: str,
    fixture_name: str,
    registry: Registry,
    settings: Settings,
) -> None:
    adapter = adapter_class(registry.sources[adapter_class.source_id], settings)
    result = adapter.run(payload=_envelope(outlet, fixture_name))
    assert not result.quarantined
    assert result.rows_in_batch > 0

    curated = pd.read_parquet(settings.data_directory / "curated" / "news_items.parquet")
    assert (curated["outlet"] == outlet).all()
    assert curated["url"].str.startswith("http").all()
    # link_only: our summary slot stays empty at ingestion time.
    assert curated["summary_own"].isna().all()


def test_gdelt_rows_carry_query_country_tags(registry: Registry, settings: Settings) -> None:
    payload = (FIXTURES_DIRECTORY / "gdelt_artlist_envelope.json").read_bytes()
    adapter = GdeltAdapter(registry.sources["gdelt"], settings)
    result = adapter.run(payload=payload)
    assert not result.quarantined
    assert result.rows_in_batch == 3

    curated = pd.read_parquet(settings.data_directory / "curated" / "news_items.parquet")
    tags = {tuple(row) for row in curated["country_iso3"]}
    assert tags == {("PAK",), ("LKA",)}
    assert curated["published_at"].notna().all()
    assert curated["summary_own"].isna().all()


def test_gdelt_rate_limit_text_fails_loudly(registry: Registry, settings: Settings) -> None:
    # GDELT signals throttling as HTTP 200 with a plain-text body; that must be a
    # loud error, never a silently empty batch.
    payload = json.dumps(
        [{"country_iso3": "PAK", "body": "Please limit requests to one every 5 seconds"}]
    ).encode("utf-8")
    adapter = GdeltAdapter(registry.sources["gdelt"], settings)
    with pytest.raises(IngestionRuntimeError, match="rate limited"):
        adapter.run(payload=payload)
