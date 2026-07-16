"""Signal input series, assembled point-in-time.

Three families (SPEC target definition): the EM OAS proxy, each scored
country's FX pair, and the composite index. FX enters as trailing 21-day
percent change — FX levels trend by construction (crawling pegs, inflation
differentials), so level z-scores would flag every long depreciation forever,
while momentum isolates devaluation episodes. Documented in the model card.
"""

from dataclasses import dataclass

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.features.panel import daily_value_series
from sovereign_monitor.index.inputs import EM_OAS_SERIES, fx_ticker_by_country

FX_MOMENTUM_WINDOW_DAYS = 21


@dataclass(frozen=True)
class SignalSeries:
    """One series the signal layer scores."""

    name: str
    country_iso3: str | None  # None marks a global series (the OAS proxy)
    frequency: str  # "daily" | "monthly"
    values: pd.Series


def assemble_signal_series(settings: Settings) -> list[SignalSeries]:
    """Everything scoreable given the current store and index exports."""
    observations = pd.read_parquet(settings.data_directory / "curated" / "observations.parquet")
    collected: list[SignalSeries] = []

    oas = daily_value_series(observations, EM_OAS_SERIES, "GLB")
    if not oas.empty:
        collected.append(SignalSeries("em_oas", None, "daily", oas))

    for iso3, ticker in sorted(fx_ticker_by_country(settings).items()):
        fx_levels = daily_value_series(observations, ticker, iso3)
        if fx_levels.empty:
            continue
        momentum = (fx_levels.pct_change(FX_MOMENTUM_WINDOW_DAYS) * 100.0).dropna()
        if not momentum.empty:
            collected.append(SignalSeries(f"fx_{iso3}", iso3, "daily", momentum))

    index_path = settings.dashboard_export_directory / "index_monthly.csv"
    if index_path.exists():
        monthly = pd.read_csv(index_path, parse_dates=["as_of"])
        for country, group in monthly.groupby("country_iso3"):
            composite = group.set_index("as_of")["composite"].dropna()
            if not composite.empty:
                collected.append(
                    SignalSeries(f"composite_{country}", str(country), "monthly", composite)
                )
    return collected
