# sovereign-monitor

Open, reproducible monitor of sovereign debt, currency, and bond markets across South &
Central Asia, China's sphere of influence, and the major economies that shape them — built
entirely from free, public data.

Status: Phase 0 scaffold complete — tooling, CI, validated Parquet store, and the first
two ingestion adapters (Bloomberg RSS, FRED). See SPEC.md for the full plan. Full README
(architecture diagram, methodology, reproduction steps) lands once the pipeline is live.

Quick start: `make setup`, then `make ingest SOURCE=bloomberg_rss`. FRED needs a free API
key in `.env` (see `.env.example`).
