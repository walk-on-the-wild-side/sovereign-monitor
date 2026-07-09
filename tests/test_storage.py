"""Store behavior: idempotent upserts, freshest-value wins, bad batches quarantine."""

import json

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.ingestion import BloombergRssAdapter, FredAdapter
from sovereign_monitor.registry import Registry
from sovereign_monitor.storage import upsert_table
from tests.conftest import FIXTURES_DIRECTORY


def test_replaying_a_batch_is_a_no_op(registry: Registry, settings: Settings) -> None:
    payload = (FIXTURES_DIRECTORY / "bloomberg_markets_news.xml").read_bytes()
    adapter = BloombergRssAdapter(registry.sources["bloomberg_rss"], settings)
    first = adapter.run(payload=payload)
    second = adapter.run(payload=payload)
    assert first.rows_added == first.rows_in_batch
    assert second.rows_added == 0
    curated = pd.read_parquet(settings.data_directory / "curated" / "news_items.parquet")
    assert len(curated) == first.rows_in_batch


def test_freshest_value_wins_per_key(settings: Settings) -> None:
    table_path = settings.data_directory / "curated" / "observations.parquet"
    key = ("source_id", "series_id", "country_iso3", "date")

    def make_frame(value: float, ingested_at: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "source_id": ["fred"],
                "series_id": ["VIXCLS"],
                "country_iso3": ["USA"],
                "date": [pd.Timestamp("2026-07-01")],
                "value": [value],
                "ingested_at": [pd.Timestamp(ingested_at, tz="UTC")],
                "available_at": [pd.Timestamp("2026-07-02")],
                "batch_id": ["abc123"],
            }
        )

    upsert_table(make_frame(17.0, "2026-07-02T03:00:00"), table_path, key)
    net_new = upsert_table(make_frame(17.5, "2026-07-03T03:00:00"), table_path, key)
    stored = pd.read_parquet(table_path)
    assert net_new == 0
    assert len(stored) == 1
    assert stored.loc[0, "value"] == 17.5


def test_bad_batch_is_quarantined_not_ingested(registry: Registry, settings: Settings) -> None:
    # A negative ICE BofA spread violates the range check: the batch must land in
    # quarantine with a reason, and the curated table must not be created.
    corrupted = {
        "BAMLEMCBPIOAS": {
            "observations": [
                {"date": "2026-07-01", "value": "-5.0"},
                {"date": "2026-07-02", "value": "2.4"},
            ]
        }
    }
    adapter = FredAdapter(registry.sources["fred"], settings)
    result = adapter.run(payload=json.dumps(corrupted).encode("utf-8"))

    assert result.quarantined
    assert result.rows_added == 0
    assert not (settings.data_directory / "curated" / "observations.parquet").exists()

    quarantine_directories = list((settings.data_directory / "quarantine" / "fred").iterdir())
    assert len(quarantine_directories) == 1
    reason = json.loads((quarantine_directories[0] / "reason.json").read_text(encoding="utf-8"))
    assert reason["source_id"] == "fred"
    assert "reason" in reason
