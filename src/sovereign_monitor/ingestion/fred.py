"""FRED adapter (St. Louis Fed).

Licensing boundary (SPEC: register): FRED-served ICE BofA series are
redistribution-restricted — raw values land only in the gitignored data/ tree;
only derived statistics may ever be committed.
"""

import json
from typing import Any, ClassVar

import httpx
import pandas as pd
import yaml

from sovereign_monitor.ingestion.base import IngestionConfigurationError, SourceAdapter


class FredAdapter(SourceAdapter):
    """Pulls the FRED series listed in config/countries.yaml as one daily batch."""

    source_id: ClassVar[str] = "fred"
    table: ClassVar[str] = "observations"
    raw_suffix: ClassVar[str] = ".json"

    def _series_plan(self) -> tuple[list[dict[str, str]], str]:
        """The series to pull and the observation-start floor, from countries.yaml."""
        config = yaml.safe_load(self.settings.countries_path.read_text(encoding="utf-8"))
        return config["series"]["fred"], config["observation_start"]

    def fetch(self) -> bytes:
        if not self.settings.fred_api_key:
            raise IngestionConfigurationError(
                "FRED_API_KEY is not set; get a free key at "
                "https://fred.stlouisfed.org/docs/api/api_key.html and add it to .env"
            )
        plan, observation_start = self._series_plan()
        payloads: dict[str, Any] = {}
        with httpx.Client(
            timeout=self.settings.http_timeout_seconds,
            headers={"User-Agent": self.settings.http_user_agent},
        ) as client:
            for item in plan:
                response = client.get(
                    f"{self.source.endpoint}/series/observations",
                    params={
                        "series_id": item["series_id"],
                        "api_key": self.settings.fred_api_key,
                        "file_type": "json",
                        "observation_start": observation_start,
                    },
                )
                response.raise_for_status()
                payloads[item["series_id"]] = response.json()
        return json.dumps(payloads).encode("utf-8")

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        payloads = json.loads(payload)
        plan, _ = self._series_plan()
        country_by_series = {item["series_id"]: item["country_iso3"] for item in plan}

        rows = []
        for series_id, body in payloads.items():
            for observation in body.get("observations", []):
                # FRED encodes market holidays and gaps as "."; those rows carry no
                # information and are dropped rather than stored as nulls.
                if observation["value"] == ".":
                    continue
                date = pd.Timestamp(observation["date"])
                rows.append(
                    {
                        "source_id": self.source_id,
                        "series_id": series_id,
                        "country_iso3": country_by_series.get(series_id, "GLB"),
                        "date": date,
                        "value": float(observation["value"]),
                        "ingested_at": ingested_at,
                        # Daily market series publish next day; calendar-day +1 is the
                        # conservative availability floor until B2 refines per-series lags.
                        "available_at": date + pd.Timedelta(days=1),
                        "batch_id": batch_id,
                    }
                )
        return pd.DataFrame(
            rows,
            columns=[
                "source_id",
                "series_id",
                "country_iso3",
                "date",
                "value",
                "ingested_at",
                "available_at",
                "batch_id",
            ],
        )
