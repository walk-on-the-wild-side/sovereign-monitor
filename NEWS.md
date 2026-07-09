# NEWS — user-visible changes, newest first

## Unreleased

- Phase 0 scaffold: uv-managed project with ruff, mypy, pytest, pre-commit, and CI;
  typed configuration and structured logging; Parquet store with quarantine for bad
  batches; first two ingestion adapters (Bloomberg RSS headlines, FRED series) wired
  to `make ingest SOURCE=<id>`.
