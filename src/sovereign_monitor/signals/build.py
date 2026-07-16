"""The signals CLI: current flags for every scoreable series → dashboard_export/.

Derived values only (z-scores, booleans, dates) — committable regardless of the
underlying series' redistribution flags.
"""

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.signals.anomalies import anomaly_flags, flag_onsets, trailing_zscores
from sovereign_monitor.signals.regimes import (
    last_change_point,
    regime_break_is_recent,
    weekly_series,
)
from sovereign_monitor.signals.series import assemble_signal_series


def build_signal_exports(settings: Settings) -> dict[str, int]:
    """Compute latest anomaly/regime state per series; write signals.csv."""
    rows = []
    for signal in assemble_signal_series(settings):
        zscores = trailing_zscores(signal.values, signal.frequency)
        flags = anomaly_flags(zscores)
        onsets = flag_onsets(flags)
        as_of = pd.Timestamp(signal.values.index.max())
        break_date = last_change_point(weekly_series(signal.values))
        rows.append(
            {
                "series": signal.name,
                "country_iso3": signal.country_iso3 or "GLB",
                "frequency": signal.frequency,
                "as_of": as_of.date(),
                "latest_z": round(float(zscores.iloc[-1]), 2) if zscores.notna().any() else None,
                "anomaly_now": bool(flags.iloc[-1]),
                "last_anomaly_onset": onsets.max().date() if len(onsets) else None,
                "regime_break_recent": regime_break_is_recent(break_date, as_of),
                "last_regime_break": break_date.date() if break_date is not None else None,
            }
        )
    signals = pd.DataFrame(rows).sort_values(["country_iso3", "series"]).reset_index(drop=True)
    settings.dashboard_export_directory.mkdir(parents=True, exist_ok=True)
    signals.to_csv(settings.dashboard_export_directory / "signals.csv", index=False)
    return {"signals": len(signals)}
