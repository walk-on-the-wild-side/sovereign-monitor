# Makefile — common development and pipeline tasks for sovereign-monitor.
# Run `make help` for a summary of targets.

.DEFAULT_GOAL := help

help:  ## list available targets
	@grep -E '^[a-z-]+( [a-z-]+)*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup:  ## install dependencies and pre-commit hooks
	uv sync
	uv run pre-commit install

lint:  ## ruff check, format check, and mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

test:  ## run the test suite (no network calls)
	uv run pytest

ingest:  ## ingest one source: make ingest SOURCE=<registry id>
	@test -n "$(SOURCE)" || { echo "sovereign-monitor: SOURCE is required, e.g. make ingest SOURCE=fred" >&2; exit 2; }
	uv run python -m sovereign_monitor ingest --source $(SOURCE)

validate:  ## re-validate the curated store against the Pandera schemas
	uv run python -m sovereign_monitor validate

export-public:  ## write the re-publishable subset of the store to public_data/
	uv run python -m sovereign_monitor export-public

build-index:  ## compute the composite index and write dashboard_export/
	uv run python -m sovereign_monitor build-index

signals:  ## compute anomaly/regime flags and write dashboard_export/signals.csv
	uv run python -m sovereign_monitor signals

backtest:  ## evaluate signals against docs/stress_events.yaml (logs to local MLflow)
	uv run python -m sovereign_monitor backtest

surveil:  ## run drift/threshold/staleness checks into dashboard_export/alerts.csv
	uv run python -m sovereign_monitor surveil

# Later lifecycle stages (SPEC.md): fail loudly instead of pretending to work.
dashboard issue-pack:  ## not implemented until their lifecycle stage
	@echo "sovereign-monitor: $@ is not implemented until its lifecycle stage (see SPEC.md)" >&2; exit 2

.PHONY: help setup lint test ingest validate export-public build-index signals backtest surveil dashboard issue-pack
