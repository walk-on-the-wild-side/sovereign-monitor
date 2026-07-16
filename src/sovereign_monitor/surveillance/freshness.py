"""Source freshness — how stale each source's newest record is.

Shared by the `validate` command (prints warnings, B1) and the surveillance
alert log (B4). Centralized here so the cadence thresholds have one home.
"""

from dataclasses import dataclass

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.registry import load_registry

# Freshness thresholds per registry cadence, in days. Low-frequency sources get
# slack for publication lag: annual datasets (WDI, IDS, ND-GAIN) normally trail
# their reference year by 12-20 months, monthly reserves by 1-2 months.
# on_release / ad_hoc sources have no cadence entry and are never called stale.
CADENCE_MAX_AGE_DAYS = {
    "15min-hourly": 2,
    "hourly": 2,
    "daily": 4,
    "weekly": 10,
    "monthly": 75,
    "quarterly": 800,
    "annual": 800,
}

# Per-source overrides where the data's own frequency differs from the registry's
# cadence field (the *pull* cadence): WDI is pulled monthly but publishes annually,
# so the monthly threshold would warn forever.
FRESHNESS_MAX_AGE_OVERRIDES = {"worldbank_wdi": 800}


@dataclass(frozen=True)
class StaleSource:
    """A source whose newest record is older than its freshness threshold."""

    source_id: str
    cadence: str
    newest_date: pd.Timestamp
    age_days: int
    threshold_days: int


def _newest_record_by_source(settings: Settings) -> dict[str, pd.Timestamp]:
    newest: dict[str, pd.Timestamp] = {}
    observations_path = settings.data_directory / "curated" / "observations.parquet"
    if observations_path.exists():
        observations = pd.read_parquet(observations_path)
        by_source = observations.groupby("source_id")["date"].max()
        newest.update({str(s): pd.Timestamp(when) for s, when in by_source.items()})
    news_path = settings.data_directory / "curated" / "news_items.parquet"
    if news_path.exists():
        news_items = pd.read_parquet(news_path)
        by_source = news_items.groupby("source_id")["published_at"].max().dt.tz_localize(None)
        newest.update({str(s): pd.Timestamp(when) for s, when in by_source.items()})
    return newest


def stale_sources(settings: Settings) -> list[StaleSource]:
    """Every source whose newest record exceeds its cadence-based threshold."""
    registry = load_registry(settings.registry_path)
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    stale: list[StaleSource] = []
    for source_id, newest_date in sorted(_newest_record_by_source(settings).items()):
        source = registry.sources.get(source_id)
        if source is None or pd.isna(newest_date):
            continue
        threshold = FRESHNESS_MAX_AGE_OVERRIDES.get(
            source_id, CADENCE_MAX_AGE_DAYS.get(source.cadence)
        )
        if threshold is None:
            continue
        age_days = (today - newest_date.normalize()).days
        if age_days > threshold:
            stale.append(StaleSource(source_id, source.cadence, newest_date, age_days, threshold))
    return stale
