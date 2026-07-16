# Model card — regime & anomaly signals (SPEC stage B3)

> Version 1.0, backtested 2026-07-16. This card reports what the signal layer does
> and, honestly, how well it does it. The headline: the signals have **modest
> recall, low precision, and no point forecast that beats a naive random walk**.
> They are a "what moved & why" attention layer, not a predictor — and this card
> exists so that limitation is stated, not buried.

## What this is

Two families of unsupervised flags over the monitor's own series:

- **Anomaly flags** — a value's trailing z-score (baseline: 252 trading days for
  daily series, 24 months for monthly, strictly ending the period before) reaches
  |z| ≥ 2.5 and holds there for 3+ consecutive observations.
- **Regime flags** — PELT change-point detection (`ruptures`, RBF cost, penalty 10,
  8-week minimum segment) on the weekly-resampled series flags a country when a
  break falls inside the trailing 60 days.

Scored series: the EM OAS spread proxy, each scored country's FX (as 21-day
momentum, not level), and each country's composite index. Current state ships
daily as `dashboard_export/signals.csv`.

## Intended use

Surfacing which countries and series are moving abnormally *right now*, to steer
the weekly research note's "what moved" section and the (future) dashboard alert
log. A flag is a prompt for a human to look, nothing more.

## Out of scope

Not a probability of default, not an early-warning system, not a trading signal.
Probability-of-distress modelling is the separate `sovereign-pd` project. Nothing
here is investment advice.

## Evaluation

**Ground truth:** a hand-curated list of 34 sovereign-stress events across the
twelve countries (`docs/stress_events.yaml`); 30 fall inside the 2010-present
evaluation window. **Metric:** a flag onset "matches" an event if the two fall
within a symmetric tolerance window. Anomaly flags are point-in-time by
construction; regime detection is re-run on an expanding quarterly grid so a break
is only credited when it would actually have been visible (no full-sample
hindsight). Full backtest reproduces with `make backtest` (~minutes; runs logged
to a local MLflow SQLite store).

### Detection metrics

| Tolerance | Precision | Recall | Flag onsets | Events |
|---|---|---|---|---|
| ±30 days | 0.073 | 0.367 | 164 | 30 |
| ±90 days | 0.128 | 0.433 | 164 | 30 |

Read honestly: at a 90-day tolerance the signals catch **43% of documented stress
events** but only **13% of flag onsets land near a documented event**. The low
precision has two causes, and the card does not hide either: (1) genuine noise —
z-score and change-point flags fire on ordinary volatility; and (2) an incomplete
reference list — many onsets sit on real stress (e.g. COVID-March-2020 hit every
EM currency) that simply is not among the 34 curated events. Precision here is
therefore a *loose lower bound* on usefulness, not a false-positive rate.

### Point-forecast comparison (the naive-beat test)

One-step composite forecasts, mean absolute error, 2015-present:

| Forecast | MAE |
|---|---|
| Naive random walk (last value) | **1.217** |
| Trailing 3-month mean | 1.794 |

The naive random walk **wins**. The composite index is close to a random walk
month-to-month, so a trailing-mean smoother does worse than just carrying the last
value forward. This is the SPEC's honest-metrics clause made concrete: **we have no
point forecast that beats naive, and we say so.** The signals earn their place as
a descriptive attention layer, not by predicting the next value.

## Known limitations

- **Reference-list bias.** Precision/recall are only as good as a hand-built,
  admittedly incomplete event list; both numbers move as it grows. It is a
  judgment artifact, not ground physical truth.
- **Pegged currencies distort z-scores.** The Maldivian rufiyaa is tightly pegged,
  so a tiny move produces `z ≈ 23`; such flags are noise, not signal.
- **Central-Asia FX coverage gaps.** No usable Yahoo pair for the Kyrgyz Republic,
  Tajikistan, or Mongolia, so those countries carry no FX-based flag.
- **Spread proxy is global.** The EM OAS series is one index shared across all
  twelve countries; it cannot distinguish country-specific credit stress.
- **Regime timing is coarse in the backtest.** The expanding re-run uses a 4-week
  change-point grid for tractability, so a backtested break date can sit up to ~28
  days from the true break (inside the 90-day window; live detection uses the exact
  1-week grid).

## Reproducibility

`make signals` writes the current flags; `make backtest` reproduces every number
above and logs parameters, metrics, and the per-event hit table to
`mlflow.db` (local, gitignored). Parameters: z-threshold 2.5, sustained 3,
PELT penalty 10, tolerances (30, 90) days, evaluation start 2010-01-01.

---

*This is a research and educational project. Nothing here is investment advice.*
