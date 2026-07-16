"""Surveillance layer (SPEC stage B4): watch the inputs and the index for trouble.

Three alert families feed one committed log (dashboard_export/alerts.csv):
input drift (PSI on the series that feed the index), threshold breaches (large
month-over-month index moves and the B3 anomaly/regime flags), and staleness
(a source that has stopped updating). The dashboard reads the log; a deliberately
shifted input fires a drift alert end to end.
"""

from sovereign_monitor.surveillance.build import build_surveillance_exports
from sovereign_monitor.surveillance.freshness import (
    CADENCE_MAX_AGE_DAYS,
    FRESHNESS_MAX_AGE_OVERRIDES,
    StaleSource,
    stale_sources,
)
from sovereign_monitor.surveillance.metrics import (
    PSI_CRITICAL,
    PSI_WARNING,
    population_stability_index,
)

__all__ = [
    "CADENCE_MAX_AGE_DAYS",
    "FRESHNESS_MAX_AGE_OVERRIDES",
    "PSI_CRITICAL",
    "PSI_WARNING",
    "StaleSource",
    "build_surveillance_exports",
    "population_stability_index",
    "stale_sources",
]
