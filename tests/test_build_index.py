"""build-index end-to-end on a synthetic store: CSVs and the heatmap land."""

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.index import build_index_exports


def _rows(
    series_id: str,
    country_iso3: str,
    dates: pd.DatetimeIndex,
    values: list[float],
    lag_days: int,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_id": "synthetic",
            "series_id": series_id,
            "country_iso3": country_iso3,
            "date": dates,
            "value": values,
            "ingested_at": pd.Timestamp("2026-01-01", tz="UTC"),
            "available_at": dates + pd.Timedelta(days=lag_days),
            "batch_id": "test",
        }
    )


def test_build_index_writes_exports(settings: Settings) -> None:
    months = pd.date_range("2023-01-31", "2025-12-31", freq="ME")
    oas_values = [2.0 + 0.01 * i for i in range(len(months))]
    years = pd.to_datetime(["2022-12-31", "2023-12-31", "2024-12-31"])

    observations = pd.concat(
        [
            _rows("BAMLEMCBPIOAS", "GLB", months, oas_values, lag_days=1),
            _rows("DT.DOD.DECT.GN.ZS", "PAK", years, [30.0, 35.0, 40.0], lag_days=183),
            _rows("DT.DOD.DECT.GN.ZS", "LKA", years, [60.0, 55.0, 50.0], lag_days=183),
        ],
        ignore_index=True,
    )
    curated = settings.data_directory / "curated"
    curated.mkdir(parents=True, exist_ok=True)
    observations.to_parquet(curated / "observations.parquet", index=False)

    built = build_index_exports(settings)
    assert built["index_monthly"] > 0
    assert built["market_daily"] > 0

    export_directory = settings.dashboard_export_directory
    monthly = pd.read_csv(export_directory / "index_monthly.csv")
    assert {"as_of", "country_iso3", "market", "external_debt", "composite"} <= set(monthly.columns)
    # PAK and LKA have market + debt pillars once the annual data is available:
    # composite coverage (>= 2 pillars) must exist for them.
    assert monthly[monthly.country_iso3.isin(["PAK", "LKA"])]["composite"].notna().any()

    daily = pd.read_csv(export_directory / "market_daily.csv")
    assert {"as_of", "country_iso3", "market_score"} == set(daily.columns)
    assert (export_directory / "index_heatmap.png").stat().st_size > 10_000
