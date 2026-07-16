"""Backtest: signals scored against the hand-curated stress-event list.

These are DETECTION metrics, not early-warning proof: a flag onset matches an
event when the two fall within a symmetric tolerance window (30/90 days) of
each other. Anomaly flags are point-in-time by construction, so their full
history is a valid backtest as-is; regime detection is re-run on an expanding
quarterly grid because PELT locates breaks using everything it sees, and
handing it the full sample would leak the future into the past.

Runs log to local MLflow when it is installed (dev dependency); the scheduled
workflows never call this module.
"""

from pathlib import Path
from typing import Any

import pandas as pd
import structlog
import yaml

from sovereign_monitor.configuration import Settings
from sovereign_monitor.signals.anomalies import anomaly_flags, flag_onsets, trailing_zscores
from sovereign_monitor.signals.regimes import (
    BACKTEST_JUMP,
    RECENT_BREAK_DAYS,
    last_change_point,
    weekly_series,
)
from sovereign_monitor.signals.series import SignalSeries, assemble_signal_series

TOLERANCE_DAYS = (30, 90)
EVALUATION_START = pd.Timestamp("2010-01-01")
REGIME_GRID_FREQUENCY = "QE"  # expanding PELT re-runs, quarterly
FORECAST_START = pd.Timestamp("2015-01-01")

log = structlog.get_logger()


def load_stress_events(path: Path) -> pd.DataFrame:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    events = pd.DataFrame(raw["events"])
    events["date"] = pd.to_datetime(events["date"])
    return events


def _regime_detection_dates(signal: SignalSeries) -> list[pd.Timestamp]:
    """When an expanding re-run would first have flagged each regime break."""
    weekly_values = weekly_series(signal.values)
    if weekly_values.empty:
        return []
    grid = pd.date_range(
        max(EVALUATION_START, weekly_values.index.min()),
        weekly_values.index.max(),
        freq=REGIME_GRID_FREQUENCY,
    )
    detections: list[pd.Timestamp] = []
    already_seen: set[pd.Timestamp] = set()
    for as_of in grid:
        window = weekly_values.loc[:as_of]
        break_date = last_change_point(window, jump=BACKTEST_JUMP)
        if break_date is None or break_date in already_seen:
            continue
        already_seen.add(break_date)
        # Only a break still fresh at evaluation time counts as a detection.
        if (as_of - break_date) <= pd.Timedelta(days=RECENT_BREAK_DAYS + 92):
            detections.append(as_of)
    return detections


def _match_counts(
    onsets: list[pd.Timestamp], events: list[pd.Timestamp], tolerance: pd.Timedelta
) -> tuple[int, int]:
    matched_onsets = sum(
        1 for onset in onsets if any(abs(onset - event) <= tolerance for event in events)
    )
    hit_events = sum(
        1 for event in events if any(abs(onset - event) <= tolerance for onset in onsets)
    )
    return matched_onsets, hit_events


def evaluate_signals(settings: Settings, events_path: Path) -> dict[str, Any]:
    """Precision/recall per tolerance window, plus the naive-forecast comparison."""
    events = load_stress_events(events_path)
    events = events[events["date"] >= EVALUATION_START]
    signals = assemble_signal_series(settings)

    onsets_by_country: dict[str, list[pd.Timestamp]] = {}
    for signal in signals:
        if signal.country_iso3 is None:
            continue  # the global OAS series has no single country to score against
        zscores = trailing_zscores(signal.values, signal.frequency)
        anomaly_onsets = [
            onset for onset in flag_onsets(anomaly_flags(zscores)) if onset >= EVALUATION_START
        ]
        regime_detections = _regime_detection_dates(signal) if signal.frequency == "daily" else []
        bucket = onsets_by_country.setdefault(signal.country_iso3, [])
        bucket.extend(anomaly_onsets)
        bucket.extend(regime_detections)
        log.info(
            "signal evaluated",
            series=signal.name,
            anomaly_onsets=len(anomaly_onsets),
            regime_detections=len(regime_detections),
        )

    metrics: dict[str, Any] = {}
    per_event_rows = []
    for tolerance_days in TOLERANCE_DAYS:
        tolerance = pd.Timedelta(days=tolerance_days)
        total_onsets, matched_onsets, total_events, hit_events = 0, 0, 0, 0
        for country, group in events.groupby("country_iso3"):
            onsets = sorted(onsets_by_country.get(str(country), []))
            event_dates = list(group["date"])
            matched, hits = _match_counts(onsets, event_dates, tolerance)
            total_onsets += len(onsets)
            matched_onsets += matched
            total_events += len(event_dates)
            hit_events += hits
            if tolerance_days == max(TOLERANCE_DAYS):
                for event_date in event_dates:
                    hit = any(abs(onset - event_date) <= tolerance for onset in onsets)
                    per_event_rows.append(
                        {"country_iso3": country, "date": event_date.date(), "hit": hit}
                    )
        metrics[f"precision_{tolerance_days}d"] = (
            round(matched_onsets / total_onsets, 3) if total_onsets else None
        )
        metrics[f"recall_{tolerance_days}d"] = (
            round(hit_events / total_events, 3) if total_events else None
        )
        metrics[f"flag_onsets_{tolerance_days}d"] = total_onsets
        metrics[f"events_{tolerance_days}d"] = total_events

    metrics.update(_naive_forecast_comparison(signals))

    _log_to_mlflow(metrics, pd.DataFrame(per_event_rows))
    return {"metrics": metrics, "per_event": pd.DataFrame(per_event_rows)}


def _naive_forecast_comparison(signals: list[SignalSeries]) -> dict[str, Any]:
    """One-step composite forecasts: random walk vs trailing-3-month mean.

    The honest-metrics clause (SPEC): if nothing beats naive, say so — this
    comparison exists to force that sentence into the model card.
    """
    naive_errors: list[float] = []
    mean3_errors: list[float] = []
    for signal in signals:
        if not signal.name.startswith("composite_"):
            continue
        values = signal.values[signal.values.index >= FORECAST_START]
        if len(values) < 6:
            continue
        naive_errors.extend((values - values.shift(1)).abs().dropna())
        mean3_errors.extend((values - values.rolling(3).mean().shift(1)).abs().dropna())
    return {
        "mae_naive_random_walk": round(float(pd.Series(naive_errors).mean()), 3),
        "mae_trailing_3m_mean": round(float(pd.Series(mean3_errors).mean()), 3),
    }


def _log_to_mlflow(metrics: dict[str, Any], per_event: pd.DataFrame) -> None:
    """Best-effort experiment tracking; a tracking failure never loses the science.

    The computed metrics are the product — they are already returned and printed
    before this runs — so any MLflow problem (missing dep, backend deprecation)
    is logged and swallowed rather than allowed to discard a multi-minute run.
    Uses the SQLite backend: recent MLflow disables the plain file store.
    """
    try:
        import mlflow  # dev dependency; absent on scheduled runners

        mlflow.set_tracking_uri("sqlite:///mlflow.db")
        mlflow.set_experiment("signals-backtest")
        with mlflow.start_run():
            mlflow.log_params(
                {
                    "z_threshold": 2.5,
                    "sustained_observations": 3,
                    "pelt_penalty": 10.0,
                    "backtest_jump": BACKTEST_JUMP,
                    "tolerances_days": str(TOLERANCE_DAYS),
                    "evaluation_start": str(EVALUATION_START.date()),
                }
            )
            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, int | float)})
            if not per_event.empty:
                mlflow.log_text(per_event.to_csv(index=False), "per_event_hits.csv")
    except Exception as error:  # tracking is optional; never fatal to the backtest
        log.warning("mlflow tracking skipped", error=f"{type(error).__name__}: {error}")
