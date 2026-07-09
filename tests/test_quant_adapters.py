"""Quant-layer adapters: recorded/handcrafted payloads parse into valid observations."""

import json

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.ingestion import (
    FrankfurterAdapter,
    ImfSdmxAdapter,
    WorldBankIdsAdapter,
    WorldBankWdiAdapter,
    YfinancePricesAdapter,
)
from sovereign_monitor.registry import Registry
from tests.conftest import FIXTURES_DIRECTORY


def _curated(settings: Settings) -> pd.DataFrame:
    return pd.read_parquet(settings.data_directory / "curated" / "observations.parquet")


def test_frankfurter_parses_usd_crosses(registry: Registry, settings: Settings) -> None:
    payload = (FIXTURES_DIRECTORY / "frankfurter_usd.json").read_bytes()
    adapter = FrankfurterAdapter(registry.sources["frankfurter"], settings)
    result = adapter.run(payload=payload)
    assert not result.quarantined
    curated = _curated(settings)
    assert set(curated["series_id"]) == {"USDINR", "USDCNY", "USDJPY"}
    assert set(curated["country_iso3"]) == {"IND", "CHN", "JPN"}
    assert ((curated["available_at"] - curated["date"]) == pd.Timedelta(days=1)).all()


def test_yfinance_parses_handcrafted_payload(registry: Registry, settings: Settings) -> None:
    payload = json.dumps(
        {
            "EMB": {"2026-07-06": 91.21, "2026-07-07": 91.35},
            "PKR=X": {"2026-07-06": 278.0, "2026-07-07": 278.1},
        }
    ).encode("utf-8")
    adapter = YfinancePricesAdapter(registry.sources["yfinance"], settings)
    result = adapter.run(payload=payload)
    assert not result.quarantined
    curated = _curated(settings)
    assert len(curated) == 4
    by_series = curated.set_index("series_id")["country_iso3"].to_dict()
    assert by_series == {"EMB": "GLB", "PKR=X": "PAK"}


def test_worldbank_wdi_applies_annual_availability_lag(
    registry: Registry, settings: Settings
) -> None:
    body = json.loads((FIXTURES_DIRECTORY / "wb_wdi_reserves.json").read_bytes())
    payload = json.dumps({"FI.RES.TOTL.MO": body}).encode("utf-8")
    adapter = WorldBankWdiAdapter(registry.sources["worldbank_wdi"], settings)
    result = adapter.run(payload=payload)
    assert not result.quarantined
    curated = _curated(settings)
    assert curated["value"].notna().all()
    # Leakage rule: year Y reference dates become available mid-year Y+1.
    sample = curated.iloc[0]
    assert sample["date"].month == 12
    assert sample["available_at"] == pd.Timestamp(year=sample["date"].year + 1, month=7, day=1)


def test_worldbank_ids_parses_counterpart_records(registry: Registry, settings: Settings) -> None:
    body = json.loads((FIXTURES_DIRECTORY / "wb_ids_china.json").read_bytes())
    payload = json.dumps({"DT.DOD.BLAT.CD.CHN": body["source"]["data"]}).encode("utf-8")
    adapter = WorldBankIdsAdapter(registry.sources["worldbank_ids"], settings)
    result = adapter.run(payload=payload)
    assert not result.quarantined
    curated = _curated(settings)
    assert (curated["series_id"] == "DT.DOD.BLAT.CD.CHN").all()
    assert (curated["date"].dt.year >= 2000).all()  # registry floor applied
    assert curated["country_iso3"].isin(["PAK", "LKA"]).all()


def test_imf_normalizes_monthly_periods(registry: Registry, settings: Settings) -> None:
    payload = json.dumps(
        {
            "rows": [
                {
                    "country_iso3": "IND",
                    "indicator": "IRFCLDT1_IRFCL121_USD",
                    "period": "2026-M01",
                    "value": 12345.0,
                },
                {
                    "country_iso3": "KAZ",
                    "indicator": "IRFCLDT1_IRFCL121_USD",
                    "period": "2026-M02",
                    "value": 678.0,
                },
            ]
        }
    ).encode("utf-8")
    adapter = ImfSdmxAdapter(registry.sources["imf"], settings)
    result = adapter.run(payload=payload)
    assert not result.quarantined
    curated = _curated(settings)
    assert list(curated["date"]) == [pd.Timestamp("2026-01-31"), pd.Timestamp("2026-02-28")]
