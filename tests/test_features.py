"""The leakage discipline, held in CI (SPEC: non-negotiable).

The mutation test is the v1 Definition-of-Done item: build features, corrupt
every strictly-future observation, and prove no feature value at or before the
cutoff moves.
"""

import numpy as np
import pandas as pd
import pytest

from sovereign_monitor.features import (
    expanding_window_splits,
    month_end_grid,
    point_in_time_series,
    trailing_pct_change,
)


def _observation_rows(
    series_id: str,
    country_iso3: str,
    dates: list[str],
    values: list[float],
    availability_lag_days: int,
) -> pd.DataFrame:
    reference_dates = pd.to_datetime(dates)
    return pd.DataFrame(
        {
            "source_id": "synthetic",
            "series_id": series_id,
            "country_iso3": country_iso3,
            "date": reference_dates,
            "value": values,
            "ingested_at": pd.Timestamp("2026-01-01", tz="UTC"),
            "available_at": reference_dates + pd.Timedelta(days=availability_lag_days),
            "batch_id": "test",
        }
    )


def test_value_is_invisible_before_available_at() -> None:
    # Annual 2023 data published mid-2024 must not exist at any 2023 or early-2024
    # evaluation date — the exact leakage the available_at column prevents.
    observations = _observation_rows(
        "DEBT", "PAK", ["2023-12-31"], [42.0], availability_lag_days=183
    )
    grid = month_end_grid("2023-12-31", "2024-12-31")
    series = point_in_time_series(observations, "DEBT", "PAK", grid)

    assert np.isnan(series[pd.Timestamp("2024-05-31")])
    assert series[pd.Timestamp("2024-07-31")] == 42.0


def test_stale_republication_never_overrides_newer_reading() -> None:
    observations = pd.concat(
        [
            _observation_rows("DEBT", "PAK", ["2021-12-31"], [10.0], 183),
            # An older reference year re-published later must not win.
            _observation_rows("DEBT", "PAK", ["2020-12-31"], [99.0], 600),
        ]
    )
    grid = month_end_grid("2022-01-31", "2022-12-31")
    series = point_in_time_series(observations, "DEBT", "PAK", grid)
    assert (series.dropna() == 10.0).all()


def test_leakage_mutation_features_before_cutoff_never_move() -> None:
    """THE mutation test: corrupt the future, assert the past is untouched."""
    dates = [str(d.date()) for d in pd.date_range("2020-01-31", "2025-12-31", freq="ME")]
    values = [float(v) for v in np.linspace(100.0, 250.0, len(dates))]
    observations = _observation_rows("FX", "PAK", dates, values, availability_lag_days=1)

    grid = month_end_grid("2020-01-31", "2025-12-31")
    cutoff = pd.Timestamp("2023-06-30")

    def build_features(frame: pd.DataFrame) -> pd.DataFrame:
        level = point_in_time_series(frame, "FX", "PAK", grid)
        return pd.DataFrame({"level": level, "change_12m": trailing_pct_change(level, 12)})

    baseline = build_features(observations)

    corrupted = observations.copy()
    future = corrupted["available_at"] > cutoff
    assert future.any() and (~future).any()
    corrupted.loc[future, "value"] = corrupted.loc[future, "value"] * 10 + 123.0
    mutated = build_features(corrupted)

    pd.testing.assert_frame_equal(baseline.loc[:cutoff], mutated.loc[:cutoff])
    # Sanity: the mutation did change the future — the test can actually fail.
    assert not baseline.loc[cutoff + pd.Timedelta(days=40) :].equals(
        mutated.loc[cutoff + pd.Timedelta(days=40) :]
    )


def test_expanding_window_splits_never_leak() -> None:
    splits = list(expanding_window_splits(100, n_splits=4, minimum_train=40))
    assert len(splits) == 4

    previous_train_size = 0
    covered: list[int] = []
    for train, test in splits:
        assert train.max() < test.min()  # training strictly precedes its test block
        assert len(train) >= 40
        assert len(train) > previous_train_size or previous_train_size == 0
        previous_train_size = len(train)
        covered.extend(test.tolist())
    assert covered == list(range(40, 100))  # test blocks tile the region exactly


def test_expanding_window_splits_rejects_impossible_requests() -> None:
    with pytest.raises(ValueError):
        list(expanding_window_splits(10, n_splits=2, minimum_train=10))
    with pytest.raises(ValueError):
        list(expanding_window_splits(12, n_splits=5, minimum_train=10))
