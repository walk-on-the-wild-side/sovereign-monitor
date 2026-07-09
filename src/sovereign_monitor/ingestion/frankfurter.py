"""Frankfurter adapter: ECB reference FX rates (open, re-publishable).

EM coverage is nil — these are the driver-economy crosses (INR/CNY/JPY/EUR vs
USD). Scored-country FX comes from yfinance; central-bank rates arrive later.
"""

import json
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
import pandas as pd
import yaml

from sovereign_monitor.ingestion.base import SourceAdapter
from sovereign_monitor.schemas import OBSERVATION_COLUMNS


class FrankfurterAdapter(SourceAdapter):
    """Pulls the full USD-cross history for the configured quote currencies."""

    source_id: ClassVar[str] = "frankfurter"
    table: ClassVar[str] = "observations"
    raw_suffix: ClassVar[str] = ".json"

    def _series_config(self) -> tuple[str, list[dict[str, str]], str]:
        config = yaml.safe_load(self.settings.countries_path.read_text(encoding="utf-8"))
        frankfurter = config["series"]["frankfurter"]
        return frankfurter["base"], frankfurter["quotes"], config["observation_start"]

    def fetch(self) -> bytes:
        base, quotes, observation_start = self._series_config()
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        symbols = ",".join(quote["symbol"] for quote in quotes)
        response = httpx.get(
            f"{self.source.endpoint}/{observation_start}..{today}",
            params={"from": base, "to": symbols},
            timeout=max(self.settings.http_timeout_seconds, 120.0),
            headers={"User-Agent": self.settings.http_user_agent},
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.content

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        body = json.loads(payload)
        base, quotes, _ = self._series_config()
        country_by_symbol = {quote["symbol"]: quote["country_iso3"] for quote in quotes}

        rows: list[dict[str, Any]] = []
        for date_text, rates in body.get("rates", {}).items():
            date = pd.Timestamp(date_text)
            for symbol, value in rates.items():
                rows.append(
                    {
                        "source_id": self.source_id,
                        "series_id": f"{base}{symbol}",
                        "country_iso3": country_by_symbol.get(symbol, "GLB"),
                        "date": date,
                        "value": float(value),
                        "ingested_at": ingested_at,
                        # ECB reference rates publish ~16:00 CET the same day;
                        # +1 calendar day is the conservative availability floor.
                        "available_at": date + pd.Timedelta(days=1),
                        "batch_id": batch_id,
                    }
                )
        return pd.DataFrame(rows, columns=OBSERVATION_COLUMNS)
