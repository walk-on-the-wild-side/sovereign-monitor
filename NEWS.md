# NEWS — user-visible changes, newest first

## Unreleased

- B4 surveillance layer: a committed alert log (`dashboard_export/alerts.csv`) with
  four rule families — input drift (PSI on market-return distributions), index
  jumps (composite Δ ≥ 10 pts/month), the B3 anomaly/regime flags, and source
  staleness. `make surveil` / the `surveil` command run it; the daily workflow
  refreshes it. Drift honestly watches stationary returns (not trending levels)
  with bands recalibrated above the textbook PSI thresholds for financial data —
  rationale in `docs/surveillance.md`. A deliberately shifted input fires a drift
  alert end to end (the B4 DoD test).

- B3 regime/anomaly signals: trailing z-score anomaly flags (2.5 sigma sustained
  three observations) and PELT change-point regime flags on the OAS proxy, each
  country's FX, and the composite index; `signals.csv` joins the daily exports.
  Backtested against a hand-curated stress-event list (`docs/stress_events.yaml`)
  with detection precision/recall at 30/90-day tolerances and a naive-forecast
  comparison, tracked in local MLflow (SQLite); honest results in
  `docs/model_card.md` (recall ~0.4, no point forecast beats naive).
- News: Bloomberg public RSS retired (all feed paths 404 as of 2026-07-16);
  `markets_news_rss` (CNBC markets + economy) replaces it in the daily workflow.

- B2 composite sovereign-stress index: twelve indicators in four equal-weighted
  pillars (market, external debt, macro, climate), scored 0-100 with pooled
  winsorized min-max scaling; monthly index plus a daily market overlay, exported
  to committed `dashboard_export/` (CSV + heatmap) by `build-index` and refreshed
  by the scheduled workflows. Methodology published at `docs/methodology.md`
  (hand-recomputable; held to the code by a unit test). Point-in-time features
  layer with the leakage mutation test now in CI (v1 DoD item).

- GDELT ingestion switched to the raw 15-minute bulk export files (no rate limit,
  carries tone) because the DOC API currently 429s every request from every IP
  tested; the DOC query plan remains configured for whenever the API recovers.
- B1 ingestion layer: eleven new adapters (OCCRP, central-bank and IGO press feeds,
  GDELT, Frankfurter FX, Yahoo Finance, World Bank WDI + IDS China-creditor series,
  IMF SDMX reserves, ND-GAIN, AidData GCDF); volume guardrails via a batch log;
  staleness warnings in `validate`; `export-public` writes the re-publishable subset
  of the store to `public_data/`; scheduled daily market/news and weekly macro
  GitHub Actions workflows commit that subset back. Registry endpoints re-verified
  2026-07-09 (OCCRP corrected; Reuters-via-Google-News marked broken; IMF moved to
  the new api.imf.org SDMX portal).

- Track A1 newsletter kit: locked issue template and per-issue checklist in
  `newsletter/`, plus `notebooks/issue_data_pull.ipynb`, which builds the weekly
  issue pack (what-moved table with FX staleness flags, market summary, candidate
  links from the news store, chart of the week).

- Phase 0 scaffold: uv-managed project with ruff, mypy, pytest, pre-commit, and CI;
  typed configuration and structured logging; Parquet store with quarantine for bad
  batches; first two ingestion adapters (Bloomberg RSS headlines, FRED series) wired
  to `make ingest SOURCE=<id>`.
