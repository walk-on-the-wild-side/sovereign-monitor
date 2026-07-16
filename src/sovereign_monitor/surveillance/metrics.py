"""Population Stability Index — the input-drift metric (SPEC B4).

PSI compares a recent distribution against a reference ("expected") one over
fixed buckets. Standard interpretation bands: < 0.10 stable, 0.10-0.25 moderate
drift, > 0.25 major drift. Buckets are cut on the reference distribution's
deciles, so the reference is the yardstick the recent window is measured against.
"""

import numpy as np
import pandas as pd

# Standard PSI interpretation thresholds.
PSI_WARNING = 0.10
PSI_CRITICAL = 0.25

_SMOOTHING = 1e-4  # keeps empty buckets out of the log/division


def population_stability_index(
    expected: pd.Series | np.ndarray, actual: pd.Series | np.ndarray, buckets: int = 10
) -> float:
    """PSI of `actual` against the `expected` reference distribution."""
    expected_values = pd.Series(expected).dropna().to_numpy(dtype=float)
    actual_values = pd.Series(actual).dropna().to_numpy(dtype=float)
    if expected_values.size == 0 or actual_values.size == 0:
        return float("nan")

    # Bucket edges from the reference deciles; open the ends so out-of-range
    # recent values still fall in the first/last bucket rather than vanishing.
    edges = np.quantile(expected_values, np.linspace(0.0, 1.0, buckets + 1))
    edges = np.unique(edges)
    if edges.size < 3:
        return 0.0  # a (near-)constant reference has no distribution to drift from
    edges[0], edges[-1] = -np.inf, np.inf

    expected_share = _bucket_share(expected_values, edges)
    actual_share = _bucket_share(actual_values, edges)
    return float(np.sum((actual_share - expected_share) * np.log(actual_share / expected_share)))


def _bucket_share(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    counts, _ = np.histogram(values, bins=edges)
    share = counts / counts.sum()
    clipped: np.ndarray = np.clip(share, _SMOOTHING, None)
    return clipped
