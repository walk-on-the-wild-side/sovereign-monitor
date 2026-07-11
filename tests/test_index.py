"""Index math: the hand-recompute guarantee behind the methodology page."""

import numpy as np
import pandas as pd

from sovereign_monitor.index import compose_scores, score_indicators, winsorized_minmax


def test_winsorized_minmax_pure_minmax_with_wide_quantiles() -> None:
    values = pd.Series([10.0, 20.0, 30.0])
    scaled = winsorized_minmax(values, lower_quantile=0.0, upper_quantile=1.0)
    assert list(scaled) == [0.0, 50.0, 100.0]


def test_winsorized_minmax_clips_outliers() -> None:
    # 101 evenly spaced values: the 1st/99th percentiles are 1 and 99, so the
    # extremes clip to those bounds and everything rescales inside them.
    values = pd.Series(np.arange(101, dtype=float))
    scaled = winsorized_minmax(values)
    assert scaled.iloc[0] == 0.0  # 0 clipped to 1 -> lower bound
    assert scaled.iloc[100] == 100.0  # 100 clipped to 99 -> upper bound
    assert scaled.iloc[50] == (50 - 1) / 98 * 100  # interior value, exact arithmetic


def test_constant_column_maps_to_neutral_50() -> None:
    values = pd.Series([7.0, 7.0, np.nan])
    scaled = winsorized_minmax(values)
    assert list(scaled[:2]) == [50.0, 50.0]
    assert np.isnan(scaled.iloc[2])


def test_hand_recomputed_composite_matches_exactly() -> None:
    """Two countries, four pillars, values chosen so every step is hand-checkable.

    With two observations per column, winsorize(1%,99%) clips to [q01, q99] and
    min-max then maps the smaller value to 0 and the larger to 100. Directions:
    growth is protective (inverted). Hand result: PAK = (0+0+0+0)/4 = 0,
    LKA = (100+100+100+100)/4 = 100.
    """
    panel = pd.DataFrame(
        {
            "as_of": [pd.Timestamp("2026-06-30")] * 2,
            "country_iso3": ["PAK", "LKA"],
            "em_oas_level": [0.0, 100.0],  # market: higher = stress
            "external_debt_gni": [50.0, 100.0],  # debt: higher = stress
            "real_gdp_growth": [2.0, -2.0],  # macro: LOWER = stress (inverted)
            "climate_vulnerability": [30.0, 70.0],  # climate: higher = stress
        }
    )
    composed = compose_scores(score_indicators(panel))

    pak = composed[composed.country_iso3 == "PAK"].iloc[0]
    lka = composed[composed.country_iso3 == "LKA"].iloc[0]
    assert (pak["market"], pak["external_debt"], pak["macro"], pak["climate"]) == (
        0.0,
        0.0,
        0.0,
        0.0,
    )
    assert (lka["market"], lka["external_debt"], lka["macro"], lka["climate"]) == (
        100.0,
        100.0,
        100.0,
        100.0,
    )
    assert pak["composite"] == 0.0
    assert lka["composite"] == 100.0


def test_composite_requires_two_pillars() -> None:
    # Only the market pillar has data: pillar score exists, composite must not.
    panel = pd.DataFrame(
        {
            "as_of": [pd.Timestamp("2026-06-30")] * 2,
            "country_iso3": ["PAK", "LKA"],
            "em_oas_level": [1.0, 2.0],
        }
    )
    composed = compose_scores(score_indicators(panel))
    assert composed["market"].notna().all()
    assert composed["composite"].isna().all()
