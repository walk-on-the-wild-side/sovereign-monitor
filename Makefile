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

# Later lifecycle stages (SPEC.md): fail loudly instead of pretending to work.
build-index backtest dashboard issue-pack:  ## not implemented until their lifecycle stage
	@echo "sovereign-monitor: $@ is not implemented until its lifecycle stage (see SPEC.md)" >&2; exit 2

.PHONY: help setup lint test ingest validate build-index backtest dashboard issue-pack
