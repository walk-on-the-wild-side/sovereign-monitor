"""Assemble the surveillance alert log (SPEC B4) → dashboard_export/alerts.csv.

Four rule families, one flat log the dashboard reads:
  drift      — PSI of a recent window vs a reference window, per input series
  threshold  — large month-over-month composite-index moves
  signal     — the B3 anomaly/regime flags promoted to alerts
  freshness  — a source that has stopped updating

Every row: fired_at, severity (info|warning|critical), rule, scope, metric, detail.
Alerts are derived values (scores, booleans, dates), committable regardless of a
source's redistribution flag.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, cast

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.features.panel import daily_value_series
from sovereign_monitor.index.inputs import EM_OAS_SERIES, fx_ticker_by_country
from sovereign_monitor.surveillance.freshness import stale_sources
from sovereign_monitor.surveillance.metrics import population_stability_index

# Drift window: the recent quarter of daily returns against the prior year.
DRIFT_WINDOWS = {
    "daily": {"recent": 63, "baseline": 252, "min_recent": 30, "min_baseline": 120},
}

# Alert bands for return-drift, deliberately ABOVE the textbook PSI bands
# (0.10 / 0.25). Those were calibrated for large, stable ML feature populations;
# 63-day windows of heavy-tailed EM daily returns naturally sit around 0.1-0.7
# from ordinary volatility clustering, so textbook bands would fire on almost
# every currency every day. These bands surface only a genuine volatility-regime
# change. Rationale is documented in docs/surveillance.md.
DRIFT_WARNING = 0.5
DRIFT_CRITICAL = 1.0

COMPOSITE_MONTHLY_JUMP_WARNING = 10.0  # SPEC: index Δ ≥ 10 points/month
COMPOSITE_MONTHLY_JUMP_CRITICAL = 15.0


@dataclass(frozen=True)
class Alert:
    fired_at: str
    severity: str  # info | warning | critical
    rule: str
    scope: str
    metric: float | None
    detail: str


def _psi_severity(psi: float) -> str | None:
    if psi >= DRIFT_CRITICAL:
        return "critical"
    if psi >= DRIFT_WARNING:
        return "warning"
    return None


def _drift_series(settings: Settings) -> list[tuple[str, str, pd.Series]]:
    """(name, frequency, returns) for the daily market series drift watches.

    PSI is only meaningful on a STATIONARY quantity. Levels here trend — a currency
    depreciates over years — so the recent window sits outside the baseline range
    and PSI would fire perpetually. Daily percent change is stationary: flat under a
    trend, widening only when a series genuinely starts moving abnormally (a
    devaluation, a spread blowout). Scale-free, so it compares across currencies.

    The composite index is deliberately NOT here: it is monthly but driven by annual
    data, so its month-over-month change is mostly zeros with a once-a-year step, and
    PSI would just detect whether that step fell inside the window. The composite is
    watched by the index-jump threshold and the B3 anomaly flags instead.
    """
    series: list[tuple[str, str, pd.Series]] = []
    observations_path = settings.data_directory / "curated" / "observations.parquet"
    if not observations_path.exists():
        return series
    observations = pd.read_parquet(observations_path)
    oas = daily_value_series(observations, EM_OAS_SERIES, "GLB").pct_change()
    if oas.notna().any():
        series.append(("em_oas", "daily", oas.dropna()))
    for iso3, ticker in sorted(fx_ticker_by_country(settings).items()):
        fx_returns = daily_value_series(observations, ticker, iso3).pct_change().dropna()
        if not fx_returns.empty:
            series.append((f"fx_{iso3}", "daily", fx_returns))
    return series


def _drift_alerts(settings: Settings, fired_at: str) -> list[Alert]:
    alerts: list[Alert] = []
    for name, frequency, raw in _drift_series(settings):
        window = DRIFT_WINDOWS[frequency]
        values = raw.dropna()
        if len(values) < window["recent"] + window["min_baseline"]:
            continue
        recent = values.iloc[-window["recent"] :]
        baseline = values.iloc[-(window["recent"] + window["baseline"]) : -window["recent"]]
        if len(baseline) < window["min_baseline"] or len(recent) < window["min_recent"]:
            continue
        psi = population_stability_index(baseline, recent)
        severity = _psi_severity(psi)
        if severity is None:
            continue
        alerts.append(
            Alert(
                fired_at,
                severity,
                "input_drift",
                name,
                round(psi, 3),
                f"PSI {psi:.2f} on {name} (recent vs baseline window)",
            )
        )
    return alerts


def _threshold_alerts(settings: Settings, fired_at: str) -> list[Alert]:
    index_path = settings.dashboard_export_directory / "index_monthly.csv"
    if not index_path.exists():
        return []
    monthly = pd.read_csv(index_path, parse_dates=["as_of"])
    alerts: list[Alert] = []
    for country, group in monthly.groupby("country_iso3"):
        composite = group.sort_values("as_of").set_index("as_of")["composite"].dropna()
        if len(composite) < 2:
            continue
        change = float(composite.iloc[-1] - composite.iloc[-2])
        magnitude = abs(change)
        if magnitude < COMPOSITE_MONTHLY_JUMP_WARNING:
            continue
        severity = "critical" if magnitude >= COMPOSITE_MONTHLY_JUMP_CRITICAL else "warning"
        direction = "rose" if change > 0 else "fell"
        alerts.append(
            Alert(
                fired_at,
                severity,
                "index_jump",
                str(country),
                round(change, 2),
                f"{country} composite {direction} {magnitude:.1f} pts month-over-month",
            )
        )
    return alerts


def _signal_alerts(settings: Settings, fired_at: str) -> list[Alert]:
    signals_path = settings.dashboard_export_directory / "signals.csv"
    if not signals_path.exists():
        return []
    signals = pd.read_csv(signals_path)
    alerts: list[Alert] = []
    for row in signals.itertuples():
        if bool(row.anomaly_now):
            alerts.append(
                Alert(
                    fired_at,
                    "critical",
                    "anomaly",
                    str(row.series),
                    float(cast(Any, row.latest_z)) if pd.notna(row.latest_z) else None,
                    f"{row.series} anomaly active (z={row.latest_z})",
                )
            )
        if bool(row.regime_break_recent):
            alerts.append(
                Alert(
                    fired_at,
                    "warning",
                    "regime_shift",
                    str(row.series),
                    None,
                    f"{row.series} regime break at {row.last_regime_break}",
                )
            )
    return alerts


def _freshness_alerts(settings: Settings, fired_at: str) -> list[Alert]:
    alerts: list[Alert] = []
    for stale in stale_sources(settings):
        # Far past the threshold is a real outage; just over it is a warning.
        severity = "critical" if stale.age_days > 3 * stale.threshold_days else "warning"
        alerts.append(
            Alert(
                fired_at,
                severity,
                "staleness",
                stale.source_id,
                float(stale.age_days),
                f"{stale.source_id} newest record is {stale.age_days}d old "
                f"(threshold {stale.threshold_days}d)",
            )
        )
    return alerts


def build_surveillance_exports(settings: Settings) -> dict[str, int]:
    """Run every rule against the current store/exports; write alerts.csv."""
    fired_at = datetime.now(tz=UTC).date().isoformat()
    alerts = [
        *_drift_alerts(settings, fired_at),
        *_threshold_alerts(settings, fired_at),
        *_signal_alerts(settings, fired_at),
        *_freshness_alerts(settings, fired_at),
    ]
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (severity_order.get(a.severity, 9), a.rule, a.scope))

    frame = pd.DataFrame(
        [asdict(a) for a in alerts],
        columns=["fired_at", "severity", "rule", "scope", "metric", "detail"],
    )
    settings.dashboard_export_directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(settings.dashboard_export_directory / "alerts.csv", index=False)
    return {
        "alerts": len(frame),
        "critical": int((frame["severity"] == "critical").sum()) if not frame.empty else 0,
    }
