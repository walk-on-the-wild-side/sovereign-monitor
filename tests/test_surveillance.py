"""Surveillance layer: PSI math, the drift-alert DoD, and threshold rules."""

import numpy as np
import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.surveillance import build_surveillance_exports, population_stability_index
from sovereign_monitor.surveillance.metrics import PSI_CRITICAL, PSI_WARNING


def test_psi_is_near_zero_for_same_distribution() -> None:
    rng = np.random.default_rng(0)
    reference = rng.normal(100.0, 5.0, 2000)
    same = rng.normal(100.0, 5.0, 2000)
    assert population_stability_index(reference, same) < PSI_WARNING


def test_psi_grows_with_a_shifted_distribution() -> None:
    rng = np.random.default_rng(1)
    reference = rng.normal(100.0, 5.0, 2000)
    shifted = rng.normal(130.0, 5.0, 2000)  # a full 6-sigma mean shift
    assert population_stability_index(reference, shifted) > PSI_CRITICAL


def test_psi_handles_constant_reference() -> None:
    # A flat reference has no distribution to drift from — must not divide by zero.
    assert population_stability_index(pd.Series([7.0] * 100), pd.Series([9.0] * 20)) == 0.0


def _fx_observations(iso3: str, ticker: str, values: list[float], start: str) -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(values), freq="B")
    return pd.DataFrame(
        {
            "source_id": "yfinance",
            "series_id": ticker,
            "country_iso3": iso3,
            "date": dates,
            "value": values,
            "ingested_at": pd.Timestamp("2026-01-01", tz="UTC"),
            "available_at": dates + pd.Timedelta(days=1),
            "batch_id": "test",
        }
    )


def test_deliberately_shifted_input_fires_a_drift_alert(settings: Settings) -> None:
    """The B4 Definition of Done: a shifted input produces a drift alert end to end.

    A calm baseline year (a currency drifting gently, tiny daily returns) then a
    recent quarter of sharp daily moves — a devaluation episode. Drift watches the
    return distribution, so the widened recent returns trip PSI.
    """
    rng = np.random.default_rng(7)
    calm_levels = 100.0 * np.cumprod(1 + rng.normal(0.0003, 0.002, 320))
    # Recent quarter: an order-of-magnitude larger daily move (a crisis).
    volatile_levels = calm_levels[-1] * np.cumprod(1 + rng.normal(-0.001, 0.03, 70))
    levels = [*calm_levels, *volatile_levels]
    observations = _fx_observations("PAK", "PKR=X", levels, "2024-01-01")

    curated = settings.data_directory / "curated"
    curated.mkdir(parents=True, exist_ok=True)
    observations.to_parquet(curated / "observations.parquet", index=False)

    summary = build_surveillance_exports(settings)
    assert summary["alerts"] >= 1

    alerts = pd.read_csv(settings.dashboard_export_directory / "alerts.csv")
    drift = alerts[(alerts["rule"] == "input_drift") & (alerts["scope"] == "fx_PAK")]
    assert len(drift) == 1
    assert drift.iloc[0]["severity"] in {"warning", "critical"}
    assert drift.iloc[0]["metric"] >= PSI_WARNING


def test_no_drift_alert_for_a_gently_trending_input(settings: Settings) -> None:
    # A currency that trends steadily (constant small daily depreciation) must NOT
    # drift: its return distribution is unchanged even as the level marches up.
    rng = np.random.default_rng(9)
    trending = list(100.0 * np.cumprod(1 + rng.normal(0.0004, 0.002, 400)))
    observations = _fx_observations("PAK", "PKR=X", trending, "2024-01-01")
    curated = settings.data_directory / "curated"
    curated.mkdir(parents=True, exist_ok=True)
    observations.to_parquet(curated / "observations.parquet", index=False)

    build_surveillance_exports(settings)
    alerts = pd.read_csv(settings.dashboard_export_directory / "alerts.csv")
    assert alerts[alerts["rule"] == "input_drift"].empty


def test_large_index_jump_fires_a_threshold_alert(settings: Settings) -> None:
    settings.dashboard_export_directory.mkdir(parents=True, exist_ok=True)
    (settings.data_directory / "curated").mkdir(parents=True, exist_ok=True)
    # Minimal empty observations so the drift pass finds nothing and only the
    # index-jump rule can fire.
    pd.DataFrame(
        columns=[
            "source_id",
            "series_id",
            "country_iso3",
            "date",
            "value",
            "ingested_at",
            "available_at",
            "batch_id",
        ]
    ).to_parquet(settings.data_directory / "curated" / "observations.parquet", index=False)
    pd.DataFrame(
        {
            "as_of": ["2026-05-31", "2026-06-30"],
            "country_iso3": ["LKA", "LKA"],
            "composite": [30.0, 48.0],  # +18 pts in a month
        }
    ).to_csv(settings.dashboard_export_directory / "index_monthly.csv", index=False)

    build_surveillance_exports(settings)
    alerts = pd.read_csv(settings.dashboard_export_directory / "alerts.csv")
    jump = alerts[(alerts["rule"] == "index_jump") & (alerts["scope"] == "LKA")]
    assert len(jump) == 1
    assert jump.iloc[0]["severity"] == "critical"  # 18 >= 15
    assert jump.iloc[0]["metric"] == 18.0
