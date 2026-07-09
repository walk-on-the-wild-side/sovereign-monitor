"""FRED adapter: recorded response parses into a schema-valid observation panel."""

import pandas as pd
import pytest

from sovereign_monitor.configuration import Settings
from sovereign_monitor.ingestion import FredAdapter, IngestionConfigurationError
from sovereign_monitor.registry import Registry
from tests.conftest import FIXTURES_DIRECTORY


def test_recorded_response_lands_in_curated_store(registry: Registry, settings: Settings) -> None:
    payload = (FIXTURES_DIRECTORY / "fred_observations.json").read_bytes()
    adapter = FredAdapter(registry.sources["fred"], settings)
    result = adapter.run(payload=payload)
    assert not result.quarantined
    curated = pd.read_parquet(settings.data_directory / "curated" / "observations.parquet")

    # The fixture holds 10 observations of which 2 are "." holiday placeholders;
    # placeholders carry no information and must be dropped, not stored as nulls.
    assert len(curated) == 8
    assert curated["value"].notna().all()
    assert set(curated["series_id"]) == {"BAMLEMCBPIOAS", "DTWEXBGS"}
    assert set(curated["country_iso3"]) == {"GLB", "USA"}


def test_availability_is_lagged_one_day(registry: Registry, settings: Settings) -> None:
    # Leakage rule: a daily market print is not knowable on its reference date.
    payload = (FIXTURES_DIRECTORY / "fred_observations.json").read_bytes()
    adapter = FredAdapter(registry.sources["fred"], settings)
    adapter.run(payload=payload)
    curated = pd.read_parquet(settings.data_directory / "curated" / "observations.parquet")
    assert ((curated["available_at"] - curated["date"]) == pd.Timedelta(days=1)).all()


def test_missing_api_key_fails_with_clear_error(registry: Registry, settings: Settings) -> None:
    adapter = FredAdapter(registry.sources["fred"], settings)
    with pytest.raises(IngestionConfigurationError, match="FRED_API_KEY"):
        adapter.fetch()
