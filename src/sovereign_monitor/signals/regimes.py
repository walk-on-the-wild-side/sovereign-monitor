"""Regime flags: PELT change-point detection (SPEC B3: ruptures, RBF cost).

Series are resampled to weekly before detection — RBF's quadratic cost makes
daily FX history expensive to re-run inside the expanding backtest, and weekly
sampling changes break locations by at most a few days, well inside the
backtest's tolerance windows.

Point-in-time caveat, stated rather than hidden: PELT locates breaks using the
whole series it is given. The live flag only ever sees history (fine), but the
backtest must re-run detection on data ≤ t to know when a break would actually
have been noticed — full-sample break dates would leak the future.
"""

import pandas as pd

PENALTY = 10.0
MINIMUM_SEGMENT_WEEKS = 8
RECENT_BREAK_DAYS = 60

# Change-point grid resolution. Live detection uses jump=1 for an exact break
# date (one fit per series — speed is irrelevant). The backtest re-fits on an
# expanding grid hundreds of times, where PELT's O(n^2) RBF cost dominates, so it
# passes a coarser jump: candidate breaks land on 4-week multiples, shifting a
# located break by at most ~28 days — inside the 90-day tolerance and a ~jump^2
# speedup (hours to minutes).
LIVE_JUMP = 1
BACKTEST_JUMP = 4


def weekly_series(values: pd.Series) -> pd.Series:
    """Friday-sampled weekly series (last observation of each week)."""
    return values.resample("W-FRI").last().dropna()


def last_change_point(weekly_values: pd.Series, jump: int = LIVE_JUMP) -> pd.Timestamp | None:
    """Date the most recent regime began, or None if no break is detectable."""
    if len(weekly_values) < 3 * MINIMUM_SEGMENT_WEEKS:
        return None
    import ruptures  # heavy import, deferred to call time

    algorithm = ruptures.Pelt(model="rbf", min_size=MINIMUM_SEGMENT_WEEKS, jump=jump)
    algorithm.fit(weekly_values.to_numpy().reshape(-1, 1))
    # predict() returns end-exclusive segment boundaries, the final one = length.
    boundaries = algorithm.predict(pen=PENALTY)
    interior = [boundary for boundary in boundaries if boundary < len(weekly_values)]
    if not interior:
        return None
    return pd.Timestamp(weekly_values.index[interior[-1]])


def regime_break_is_recent(break_date: pd.Timestamp | None, as_of: pd.Timestamp) -> bool:
    """SPEC rule: a break inside the trailing 60 days flags a regime shift."""
    if break_date is None:
        return False
    return bool((as_of - break_date) <= pd.Timedelta(days=RECENT_BREAK_DAYS))
