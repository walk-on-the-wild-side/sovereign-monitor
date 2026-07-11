"""Build the index exports: monthly composite, daily market overlay, heatmap.

Outputs land in the committed dashboard_export/ tree. Everything written here is
derived (scores, not source values), so it is re-publishable regardless of the
underlying series' redistribution flags — stated in dashboard_export/README.md.
"""

from datetime import UTC, datetime

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.features import business_day_grid, month_end_grid
from sovereign_monitor.index.chart import write_index_heatmap
from sovereign_monitor.index.inputs import build_indicator_panel, build_market_daily_panel
from sovereign_monitor.index.scaling import compose_scores, score_indicators
from sovereign_monitor.index.specification import PILLARS

INDEX_START = "2000-01-31"


def build_index_exports(settings: Settings) -> dict[str, int]:
    """Compute the index from the curated store and write dashboard_export/."""
    observations = pd.read_parquet(settings.data_directory / "curated" / "observations.parquet")
    today = pd.Timestamp(datetime.now(tz=UTC).date())

    monthly_grid = month_end_grid(INDEX_START, today)
    indicator_panel = build_indicator_panel(observations, settings, monthly_grid)
    monthly = compose_scores(score_indicators(indicator_panel))
    # Keep only evaluation dates where at least one pillar exists at all.
    monthly = monthly.dropna(subset=list(PILLARS), how="all").reset_index(drop=True)
    score_columns = [*PILLARS, "composite"]
    monthly[score_columns] = monthly[score_columns].round(2)

    daily_grid = business_day_grid(INDEX_START, today)
    market_daily_panel = build_market_daily_panel(observations, settings, daily_grid)
    market_daily = compose_scores(score_indicators(market_daily_panel))
    market_daily = (
        market_daily[["as_of", "country_iso3", "market"]]
        .dropna(subset=["market"])
        .rename(columns={"market": "market_score"})
        .reset_index(drop=True)
    )
    market_daily["market_score"] = market_daily["market_score"].round(2)

    export_directory = settings.dashboard_export_directory
    export_directory.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(export_directory / "index_monthly.csv", index=False, date_format="%Y-%m-%d")
    market_daily.to_csv(export_directory / "market_daily.csv", index=False, date_format="%Y-%m-%d")
    write_index_heatmap(monthly, export_directory / "index_heatmap.png")

    return {"index_monthly": len(monthly), "market_daily": len(market_daily)}
