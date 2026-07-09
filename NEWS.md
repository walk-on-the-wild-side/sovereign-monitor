# NEWS — user-visible changes, newest first

## Unreleased

- Track A1 newsletter kit: locked issue template and per-issue checklist in
  `newsletter/`, plus `notebooks/issue_data_pull.ipynb`, which builds the weekly
  issue pack (what-moved table with FX staleness flags, market summary, candidate
  links from the news store, chart of the week).

- Phase 0 scaffold: uv-managed project with ruff, mypy, pytest, pre-commit, and CI;
  typed configuration and structured logging; Parquet store with quarantine for bad
  batches; first two ingestion adapters (Bloomberg RSS headlines, FRED series) wired
  to `make ingest SOURCE=<id>`.
