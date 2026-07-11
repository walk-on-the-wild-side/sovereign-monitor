"""Point-in-time panel primitives (SPEC: leakage prevention, non-negotiable).

Every join here uses available_at — the date a value became publicly knowable —
never the reference date, and every window is trailing. The leakage mutation
test in tests/test_features.py holds this module to that contract: altering any
strictly-future observation must leave every earlier feature value unchanged.
"""

import math

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def month_end_grid(start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
    """Month-end evaluation dates from start to end inclusive."""
    return pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="ME")


def business_day_grid(start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
    """Business-day evaluation dates for the daily market overlay."""
    return pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="B")


def point_in_time_series(
    observations: pd.DataFrame,
    series_id: str,
    country_iso3: str,
    grid: pd.DatetimeIndex,
) -> pd.Series:
    """The newest value knowable at each grid date (as-of join on available_at).

    Rows whose reference date is older than an already-published one are dropped
    first, so a late republication of stale data can never override a newer
    reading at any evaluation date.
    """
    subset = observations.loc[
        (observations["series_id"] == series_id) & (observations["country_iso3"] == country_iso3),
        ["date", "available_at", "value"],
    ].sort_values(["available_at", "date"])
    if subset.empty:
        return pd.Series(np.nan, index=grid, name=series_id)
    subset = subset[subset["date"] >= subset["date"].cummax()]
    right = subset.rename(columns={"available_at": "as_of"})[["as_of", "value"]].copy()
    # Parquet round-trips can downgrade timestamps to microsecond precision while
    # grids are nanosecond; merge_asof refuses mixed units.
    right["as_of"] = right["as_of"].astype("datetime64[ns]")
    merged = pd.merge_asof(
        pd.DataFrame({"as_of": pd.DatetimeIndex(grid).astype("datetime64[ns]")}),
        right,
        on="as_of",
        direction="backward",
    )
    return pd.Series(merged["value"].to_numpy(), index=grid, name=series_id)


def daily_value_series(observations: pd.DataFrame, series_id: str, country_iso3: str) -> pd.Series:
    """A daily series indexed by availability date, for trailing-window transforms."""
    subset = observations.loc[
        (observations["series_id"] == series_id) & (observations["country_iso3"] == country_iso3),
        ["available_at", "value"],
    ].sort_values("available_at")
    return pd.Series(
        subset["value"].to_numpy(),
        index=pd.DatetimeIndex(subset["available_at"]).astype("datetime64[ns]"),
        name=series_id,
    )


def trailing_pct_change(series: pd.Series, periods: int) -> pd.Series:
    """Trailing percentage change over `periods` steps of the series' own grid."""
    return series.pct_change(periods=periods) * 100.0


def trailing_diff(series: pd.Series, periods: int) -> pd.Series:
    """Trailing arithmetic change over `periods` steps of the series' own grid."""
    return series.diff(periods=periods)


def realized_volatility(daily_series: pd.Series, window: int = 63) -> pd.Series:
    """Annualized trailing standard deviation of daily percentage changes, in percent."""
    daily_returns = daily_series.pct_change()
    annualization = math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0
    return daily_returns.rolling(window=window, min_periods=window // 2).std() * annualization


def sample_at(series: pd.Series, grid: pd.DatetimeIndex) -> pd.Series:
    """Last known value of a finer-grained series at each grid date (trailing ffill)."""
    return series.reindex(series.index.union(grid)).ffill().reindex(grid)
