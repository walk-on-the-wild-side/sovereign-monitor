# NEWS — user-visible changes, newest first

## Unreleased

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
