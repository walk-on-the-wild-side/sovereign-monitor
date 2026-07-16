# dashboard_export/ — committed derived outputs

Everything in this directory is **derived** (index scores and charts, never raw
source values), so it is re-publishable even where an underlying series is
redistribution-restricted (FRED ICE BofA, Yahoo Finance). Methodology:
[docs/methodology.md](../docs/methodology.md).

| File | Contents |
|---|---|
| `index_monthly.csv` | month-end composite + four pillar scores per country, 0–100 |
| `market_daily.csv` | business-day market-pillar score per country (the overlay) |
| `index_heatmap.png` | trailing 24 months of the composite, countries × months |
| `signals.csv` | latest anomaly/regime state per series (z-scores, flags, break dates) |

Refreshed by the scheduled ingest workflows via `sovereign-monitor build-index`.
Scores are pooled-scaled over full history, so past values can shift slightly as
new data arrives (see methodology, "Scoring arithmetic").

Sources: FRED® (ICE BofA index data © ICE Data Indices, LLC), Yahoo Finance,
World Bank WDI/IDS (CC BY-4.0), ND-GAIN. **Not investment advice.**
