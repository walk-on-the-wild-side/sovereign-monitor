"""Normalization and composition — the arithmetic the methodology page documents.

The published promise (SPEC B2 acceptance) is hand-recomputability: winsorize at
the 1st/99th percentile pooled across the whole panel, min-max to [0, 100],
invert protective indicators, average available indicators per pillar, average
available pillars into the composite (minimum two pillars).
"""

import numpy as np
import pandas as pd

from sovereign_monitor.index.specification import INDICATORS, PILLARS

KEY_COLUMNS = ["as_of", "country_iso3"]
WINSOR_LOWER_QUANTILE = 0.01
WINSOR_UPPER_QUANTILE = 0.99
MINIMUM_PILLARS_FOR_COMPOSITE = 2


def winsorized_minmax(
    values: pd.Series,
    lower_quantile: float = WINSOR_LOWER_QUANTILE,
    upper_quantile: float = WINSOR_UPPER_QUANTILE,
) -> pd.Series:
    """Clip to pooled quantiles, then scale to [0, 100]; a constant column maps to 50."""
    observed = values.dropna()
    if observed.empty:
        return values * np.nan
    lower, upper = observed.quantile(lower_quantile), observed.quantile(upper_quantile)
    if upper == lower:
        return values.where(values.isna(), 50.0)
    clipped = values.clip(lower, upper)
    return (clipped - lower) / (upper - lower) * 100.0


def score_indicators(panel: pd.DataFrame) -> pd.DataFrame:
    """Turn raw indicator columns into stress scores in [0, 100]."""
    scores = panel[KEY_COLUMNS].copy()
    for specification in INDICATORS:
        if specification.name not in panel.columns:
            continue
        scaled = winsorized_minmax(panel[specification.name])
        scores[specification.name] = scaled if specification.higher_is_stress else 100.0 - scaled
    return scores


def compose_scores(scores: pd.DataFrame) -> pd.DataFrame:
    """Pillar scores (mean of available indicators) and the equal-weight composite."""
    composed = scores[KEY_COLUMNS].copy()
    for pillar in PILLARS:
        indicator_names = [
            spec.name
            for spec in INDICATORS
            if spec.pillar == pillar and spec.name in scores.columns
        ]
        if indicator_names:
            composed[pillar] = scores[indicator_names].mean(axis=1)
        else:
            composed[pillar] = np.nan
    pillar_frame = composed[list(PILLARS)]
    enough_coverage = pillar_frame.notna().sum(axis=1) >= MINIMUM_PILLARS_FOR_COMPOSITE
    composed["composite"] = pillar_frame.mean(axis=1).where(enough_coverage)
    return composed
