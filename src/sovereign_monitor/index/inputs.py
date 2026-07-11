"""Raw indicator panels for the index, built point-in-time from the curated store.

Monthly panel feeds the composite; the business-day variant of the market pillar
feeds the daily overlay. All extraction goes through features.panel, so the
leakage discipline is inherited, not re-implemented.
"""

from typing import Any, cast

import pandas as pd
import yaml

from sovereign_monitor.configuration import Settings
from sovereign_monitor.features import (
    point_in_time_series,
    realized_volatility,
    sample_at,
    trailing_diff,
    trailing_pct_change,
)
from sovereign_monitor.features.panel import daily_value_series

EM_OAS_SERIES = "BAMLEMCBPIOAS"

# Grid steps per window: monthly grids use months, daily grids use trading days.
WINDOW_3M = {"monthly": 3, "daily": 63}
WINDOW_12M = {"monthly": 12, "daily": 252}


def _countries_config(settings: Settings) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        yaml.safe_load(settings.countries_path.read_text(encoding="utf-8")),
    )


def scored_countries(settings: Settings) -> list[str]:
    config = _countries_config(settings)
    return [iso3 for group in config["scored"].values() for iso3 in group]


def fx_ticker_by_country(settings: Settings) -> dict[str, str]:
    config = _countries_config(settings)
    return {
        item["country_iso3"]: item["ticker"]
        for item in config["series"]["yfinance"]["tickers"]
        if item["country_iso3"] != "GLB"
    }


def _market_columns(
    observations: pd.DataFrame,
    iso3: str,
    fx_ticker: str | None,
    grid: pd.DatetimeIndex,
    frequency: str,
) -> dict[str, pd.Series]:
    """The four market indicators on the given grid ('monthly' or 'daily')."""
    oas = point_in_time_series(observations, EM_OAS_SERIES, "GLB", grid)
    columns = {
        "em_oas_level": oas,
        # OAS is quoted in percent; the 3-month change stays in percentage points.
        "em_oas_change_3m": trailing_diff(oas, WINDOW_3M[frequency]),
    }
    if fx_ticker is not None:
        fx = point_in_time_series(observations, fx_ticker, iso3, grid)
        fx_daily = daily_value_series(observations, fx_ticker, iso3)
        columns["fx_depreciation_12m"] = trailing_pct_change(fx, WINDOW_12M[frequency])
        columns["fx_volatility_3m"] = sample_at(realized_volatility(fx_daily, 63), grid)
    return columns


def build_indicator_panel(
    observations: pd.DataFrame, settings: Settings, grid: pd.DatetimeIndex
) -> pd.DataFrame:
    """Monthly country-by-indicator panel; long frame keyed by (as_of, country_iso3)."""
    fx_tickers = fx_ticker_by_country(settings)
    frames = []
    for iso3 in scored_countries(settings):
        columns: dict[str, pd.Series] = _market_columns(
            observations, iso3, fx_tickers.get(iso3), grid, "monthly"
        )

        def annual(series_id: str, iso3: str = iso3) -> pd.Series:
            return point_in_time_series(observations, series_id, iso3, grid)

        debt_total = annual("DT.DOD.DECT.CD")
        debt_to_china = annual("DT.DOD.BLAT.CD.CHN")
        columns.update(
            {
                "external_debt_gni": annual("DT.DOD.DECT.GN.ZS"),
                "debt_service_exports": annual("DT.TDS.DPPG.XP.ZS"),
                "china_debt_share": (debt_to_china / debt_total * 100.0).where(debt_total > 0),
                "real_gdp_growth": annual("NY.GDP.MKTP.KD.ZG"),
                "cpi_inflation": annual("FP.CPI.TOTL.ZG"),
                "current_account_gdp": annual("BN.CAB.XOKA.GD.ZS"),
                "reserves_import_months": annual("FI.RES.TOTL.MO"),
                "climate_vulnerability": annual("ND_GAIN.vulnerability"),
            }
        )
        frame = pd.DataFrame(columns)
        frame.insert(0, "country_iso3", iso3)
        frame.insert(0, "as_of", grid)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def build_market_daily_panel(
    observations: pd.DataFrame, settings: Settings, grid: pd.DatetimeIndex
) -> pd.DataFrame:
    """Market-pillar indicators on a business-day grid, for the daily overlay."""
    fx_tickers = fx_ticker_by_country(settings)
    frames = []
    for iso3 in scored_countries(settings):
        columns = _market_columns(observations, iso3, fx_tickers.get(iso3), grid, "daily")
        frame = pd.DataFrame(columns)
        frame.insert(0, "country_iso3", iso3)
        frame.insert(0, "as_of", grid)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)
