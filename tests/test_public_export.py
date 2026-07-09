"""The licensing boundary in code: restricted rows never reach public_data/."""

from pathlib import Path

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.ingestion import BloombergRssAdapter, FrankfurterAdapter, FredAdapter
from sovereign_monitor.registry import Registry
from sovereign_monitor.storage import export_public_subset, seed_curated_from_public
from tests.conftest import FIXTURES_DIRECTORY, PROJECT_ROOT, IsolatedSettings


def _populate_store(registry: Registry, settings: Settings) -> None:
    FrankfurterAdapter(registry.sources["frankfurter"], settings).run(
        payload=(FIXTURES_DIRECTORY / "frankfurter_usd.json").read_bytes()
    )
    FredAdapter(registry.sources["fred"], settings).run(
        payload=(FIXTURES_DIRECTORY / "fred_observations.json").read_bytes()
    )
    BloombergRssAdapter(registry.sources["bloomberg_rss"], settings).run(
        payload=(FIXTURES_DIRECTORY / "bloomberg_markets_news.xml").read_bytes()
    )


def test_restricted_observations_never_exported(registry: Registry, settings: Settings) -> None:
    _populate_store(registry, settings)
    exported = export_public_subset(settings)
    assert exported["observations"] > 0
    assert exported["news_items"] > 0

    public = pd.read_parquet(settings.public_data_directory / "observations.parquet")
    # fred is `restricted` in the registry: its raw values must never be committed.
    assert set(public["source_id"]) == {"frankfurter"}

    news = pd.read_parquet(settings.public_data_directory / "news_items.parquet")
    assert len(news) > 0  # metadata + links only, publishable by construction


def test_seed_restores_curated_store_from_public(
    registry: Registry, settings: Settings, tmp_path: Path
) -> None:
    _populate_store(registry, settings)
    export_public_subset(settings)

    fresh_runner = IsolatedSettings(
        fred_api_key=None,
        data_directory=tmp_path / "fresh_data",
        public_data_directory=settings.public_data_directory,
        registry_path=PROJECT_ROOT / "data_sources.yaml",
        countries_path=PROJECT_ROOT / "config" / "countries.yaml",
        feeds_path=PROJECT_ROOT / "config" / "feeds.yaml",
    )
    seeded = seed_curated_from_public(fresh_runner)
    assert seeded["observations"] > 0
    curated = pd.read_parquet(fresh_runner.data_directory / "curated" / "observations.parquet")
    assert set(curated["source_id"]) == {"frankfurter"}
