"""Regime/anomaly signals (SPEC stage B3): the "what moved & why" layer.

Descriptive detection, not prediction: trailing z-score anomaly flags and
change-point regime flags on the market series and the composite index,
evaluated honestly against a hand-curated stress-event list.
"""

from sovereign_monitor.signals.anomalies import anomaly_flags, flag_onsets, trailing_zscores
from sovereign_monitor.signals.backtest import evaluate_signals, load_stress_events
from sovereign_monitor.signals.build import build_signal_exports
from sovereign_monitor.signals.regimes import last_change_point, weekly_series
from sovereign_monitor.signals.series import SignalSeries, assemble_signal_series

__all__ = [
    "SignalSeries",
    "anomaly_flags",
    "assemble_signal_series",
    "build_signal_exports",
    "evaluate_signals",
    "flag_onsets",
    "last_change_point",
    "load_stress_events",
    "trailing_zscores",
    "weekly_series",
]
