# Surveillance layer — the alert log (SPEC stage B4)

> Each scheduled run writes `dashboard_export/alerts.csv`: a flat log the dashboard
> reads, one row per fired alert with a severity (info / warning / critical). The
> layer watches the inputs and the index for four kinds of trouble.

## Alert rules

| Rule | Fires when | Severity |
|---|---|---|
| `input_drift` | PSI of a market series' recent daily-return distribution vs its prior-year baseline crosses a band | warning ≥ 0.5, critical ≥ 1.0 |
| `index_jump` | a country's composite index moves ≥ 10 points month-over-month | warning ≥ 10, critical ≥ 15 |
| `anomaly` | a B3 anomaly flag is currently active (|z| ≥ 2.5, sustained) | critical |
| `regime_shift` | a B3 change-point break landed inside the trailing 60 days | warning |
| `staleness` | a source's newest record is older than its freshness threshold | warning; critical past 3× |

## Why drift watches *returns*, and why the bands are non-standard

Population Stability Index (PSI) compares a recent distribution to a reference one.
It is only meaningful on a **stationary** quantity, and two honest calibration
decisions follow from the data:

- **Returns, not levels.** A currency level trends (it depreciates over years), so a
  recent window sits almost entirely outside the baseline's range and PSI would fire
  every day forever. Daily percent change is stationary — flat under a steady trend,
  widening only when a series genuinely starts moving abnormally. That is the drift
  worth an alert.
- **Bands above the textbook 0.10 / 0.25.** Those bands were derived for large,
  stable machine-learning feature populations. A 63-day window of heavy-tailed
  emerging-market daily returns naturally scores PSI ≈ 0.1–0.7 from ordinary
  volatility clustering, so textbook bands would flag nearly every currency every
  day. The layer uses **0.5 (warning) / 1.0 (critical)**, which surface only a real
  volatility-regime change. This is a deliberate, stated trade-off, not a default.
- **The composite index is excluded from drift.** It is monthly but driven by annual
  data, so its month-over-month change is mostly zeros with a once-a-year step; PSI
  would merely detect whether that step fell in the window. The composite is watched
  by `index_jump` and the anomaly flags instead.

## Reproducing

`make surveil` runs every rule against the current store and exports and writes
`alerts.csv`. The B4 acceptance test (`tests/test_surveillance.py`) plants a
deliberately shifted input and asserts a drift alert fires end to end.

---

*This is a research and educational project. Nothing here is investment advice.*
