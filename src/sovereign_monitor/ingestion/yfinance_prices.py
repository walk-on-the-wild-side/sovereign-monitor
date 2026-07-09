"""Yahoo Finance adapter (via yfinance): EM bond ETFs and scored-country FX.

Licensing (SPEC register): restricted — unofficial source, best-effort quality.
Raw values live only in the gitignored data/ tree; only derived statistics may
be committed or published. Known data quirk: Yahoo silently stops updating some
EM pairs (KGS=X since 2025-09) — staleness surfaces via freshness warnings.
"""

import json
from typing import Any, ClassVar

import pandas as pd
import yaml

from sovereign_monitor.ingestion.base import IngestionRuntimeError, SourceAdapter
from sovereign_monitor.schemas import OBSERVATION_COLUMNS


class YfinancePricesAdapter(SourceAdapter):
    """Daily closes for the tickers configured in countries.yaml."""

    source_id: ClassVar[str] = "yfinance"
    table: ClassVar[str] = "observations"
    raw_suffix: ClassVar[str] = ".json"

    def _ticker_config(self) -> tuple[list[dict[str, str]], str]:
        config = yaml.safe_load(self.settings.countries_path.read_text(encoding="utf-8"))
        return config["series"]["yfinance"]["tickers"], config["observation_start"]

    def fetch(self) -> bytes:
        import yfinance  # heavy import, deferred to fetch time

        tickers, observation_start = self._ticker_config()
        symbols = [item["ticker"] for item in tickers]
        downloaded = yfinance.download(
            symbols,
            start=observation_start,
            interval="1d",
            progress=False,
            auto_adjust=True,
            group_by="column",
        )
        if downloaded is None or downloaded.empty:
            raise IngestionRuntimeError("yfinance returned no data for any ticker")
        closes = downloaded["Close"]
        payload = {
            ticker: {
                index.strftime("%Y-%m-%d"): float(value)
                for index, value in closes[ticker].dropna().items()
            }
            for ticker in closes.columns
        }
        return json.dumps(payload).encode("utf-8")

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        body = json.loads(payload)
        tickers, _ = self._ticker_config()
        country_by_ticker = {item["ticker"]: item["country_iso3"] for item in tickers}

        rows: list[dict[str, Any]] = []
        for ticker, series in body.items():
            for date_text, value in series.items():
                date = pd.Timestamp(date_text)
                rows.append(
                    {
                        "source_id": self.source_id,
                        "series_id": ticker,
                        "country_iso3": country_by_ticker.get(ticker, "GLB"),
                        "date": date,
                        "value": float(value),
                        "ingested_at": ingested_at,
                        # Daily closes are knowable the next calendar day.
                        "available_at": date + pd.Timedelta(days=1),
                        "batch_id": batch_id,
                    }
                )
        return pd.DataFrame(rows, columns=OBSERVATION_COLUMNS)
