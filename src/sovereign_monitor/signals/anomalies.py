"""Anomaly flags: trailing z-scores, sustained past a threshold (SPEC B3).

Point-in-time by construction: the baseline for the z-score at time t is the
trailing window ending at t-1, so a value never scores against itself and
future data can never move a past flag (the CI mutation test relies on this).
"""

import numpy as np
import pandas as pd

Z_THRESHOLD = 2.5
SUSTAINED_OBSERVATIONS = 3

ROLLING_WINDOW = {"daily": 252, "monthly": 24}
MINIMUM_PERIODS = {"daily": 126, "monthly": 18}


def trailing_zscores(values: pd.Series, frequency: str) -> pd.Series:
    """Z-score of each value against the strictly-trailing rolling baseline."""
    window = ROLLING_WINDOW[frequency]
    minimum = MINIMUM_PERIODS[frequency]
    baseline = values.shift(1)
    mean = baseline.rolling(window, min_periods=minimum).mean()
    std = baseline.rolling(window, min_periods=minimum).std().replace(0.0, np.nan)
    return (values - mean) / std


def anomaly_flags(zscores: pd.Series) -> pd.Series:
    """True where |z| has held at or above the threshold for 3+ observations."""
    extreme = (zscores.abs() >= Z_THRESHOLD).astype(float)
    sustained = extreme.rolling(SUSTAINED_OBSERVATIONS, min_periods=SUSTAINED_OBSERVATIONS).sum()
    return sustained.eq(SUSTAINED_OBSERVATIONS)


def flag_onsets(flags: pd.Series) -> pd.DatetimeIndex:
    """The dates a flag turns on — the unit the backtest scores."""
    onsets = flags & ~flags.shift(1, fill_value=False)
    return pd.DatetimeIndex(flags.index[onsets])
