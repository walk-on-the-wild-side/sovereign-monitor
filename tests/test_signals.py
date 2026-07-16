"""Signal layer: z-flag logic, sustained rule, regime breaks, backtest arithmetic."""

import numpy as np
import pandas as pd

from sovereign_monitor.signals import (
    anomaly_flags,
    flag_onsets,
    last_change_point,
    trailing_zscores,
    weekly_series,
)
from sovereign_monitor.signals.backtest import _match_counts


def _daily_series(values: list[float], start: str = "2020-01-01") -> pd.Series:
    index = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=index)


def test_zscore_baseline_is_strictly_trailing() -> None:
    # A huge value must not shrink its own z-score by inflating the baseline,
    # and mutating the future must never move a past z (leakage rule).
    calm = [10.0 + 0.01 * (i % 5) for i in range(300)]
    series = _daily_series([*calm, 25.0, 25.0])
    zscores = trailing_zscores(series, "daily")
    assert zscores.iloc[-2] > 100  # the spike scores against the calm baseline only

    mutated = series.copy()
    mutated.iloc[-1] = 500.0
    pd.testing.assert_series_equal(trailing_zscores(mutated, "daily").iloc[:-1], zscores.iloc[:-1])


def test_anomaly_requires_three_sustained_observations() -> None:
    calm = [10.0 + 0.01 * (i % 5) for i in range(300)]
    two_high = _daily_series([*calm, 25.0, 25.0, 10.0])
    three_high = _daily_series([*calm, 25.0, 25.0, 25.0])

    assert not anomaly_flags(trailing_zscores(two_high, "daily")).any()
    flags = anomaly_flags(trailing_zscores(three_high, "daily"))
    assert flags.iloc[-1]
    onsets = flag_onsets(flags)
    assert len(onsets) == 1 and onsets[0] == flags.index[-1]


def test_regime_break_found_at_level_shift() -> None:
    rng = np.random.default_rng(7)
    calm = rng.normal(10.0, 0.3, 120)
    # The post-break segment must span more than PELT's min_size (8 weeks),
    # or no boundary can legally be placed there.
    shifted = rng.normal(14.0, 0.3, 70)
    daily = _daily_series(list(calm) + list(shifted), start="2023-01-02")
    weekly = weekly_series(daily)

    break_date = last_change_point(weekly)
    assert break_date is not None
    expected_shift = daily.index[len(calm)]
    assert abs(break_date - expected_shift) <= pd.Timedelta(days=14)


def test_regime_none_without_break_or_history() -> None:
    rng = np.random.default_rng(7)
    steady = _daily_series(list(rng.normal(10.0, 0.3, 150)), start="2023-01-02")
    assert last_change_point(weekly_series(steady)) is None
    assert last_change_point(weekly_series(steady.iloc[:40])) is None  # too short


def test_backtest_match_counts_by_hand() -> None:
    onsets = [pd.Timestamp("2022-03-15"), pd.Timestamp("2022-08-01"), pd.Timestamp("2023-01-10")]
    events = [pd.Timestamp("2022-04-01"), pd.Timestamp("2023-06-01")]
    matched_onsets, hit_events = _match_counts(onsets, events, pd.Timedelta(days=30))
    # Only the March onset sits within 30 days of the April event.
    assert (matched_onsets, hit_events) == (1, 1)
    matched_onsets, hit_events = _match_counts(onsets, events, pd.Timedelta(days=180))
    # 180d: Aug-01 also reaches the April event; the June-2023 event reaches Jan-10.
    assert (matched_onsets, hit_events) == (3, 2)
