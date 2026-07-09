"""IMF adapter — new data portal SDMX 2.1 API (flow IRFCL, monthly reserves).

Endpoint verified 2026-07-09; the legacy dataservices API is dead and IFS was
decommissioned. Coverage is per-country (IND/KAZ report IRFCL, PAK does not) —
missing countries are logged and skipped, and absence shows up in freshness
warnings rather than being papered over. Licensing: attribution.
"""

import json
from typing import Any, ClassVar, cast

import pandas as pd
import yaml

from sovereign_monitor.ingestion.base import SourceAdapter
from sovereign_monitor.ingestion.worldbank import _scored_countries
from sovereign_monitor.schemas import OBSERVATION_COLUMNS


class ImfSdmxAdapter(SourceAdapter):
    """Pulls the configured IRFCL indicator family for every scored country."""

    source_id: ClassVar[str] = "imf"
    table: ClassVar[str] = "observations"
    raw_suffix: ClassVar[str] = ".json"

    def _flow_config(self) -> dict[str, str]:
        config = yaml.safe_load(self.settings.countries_path.read_text(encoding="utf-8"))
        return cast(dict[str, str], config["series"]["imf"])

    def fetch(self) -> bytes:
        import sdmx  # heavy import, deferred to fetch time

        flow = self._flow_config()
        client = sdmx.Client("IMF_DATA")
        collected: list[dict[str, Any]] = []
        for iso3 in _scored_countries(self.settings.countries_path):
            try:
                message = client.data(
                    flow["flow"], key={"COUNTRY": iso3}, params={"startPeriod": "2000"}
                )
                frame = sdmx.to_pandas(message).reset_index()  # type: ignore[no-untyped-call]
            except Exception as error:  # per-country coverage gaps are expected
                self.log.warning(
                    "imf country skipped", country=iso3, error=f"{type(error).__name__}"
                )
                continue
            keep = frame[
                (frame["FREQUENCY"] == flow["frequency"])
                & frame["INDICATOR"].str.startswith(flow["indicator_prefix"])
            ]
            collected.extend(
                {
                    "country_iso3": iso3,
                    "indicator": record.INDICATOR,
                    "period": record.TIME_PERIOD,
                    "value": float(record.value),
                }
                for record in keep.itertuples()
            )
        return json.dumps({"rows": collected}).encode("utf-8")

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        body = json.loads(payload)
        rows: list[dict[str, Any]] = []
        for record in body["rows"]:
            # Monthly periods arrive as "2025-M01": normalize to the month end.
            period = pd.Period(record["period"].replace("-M", "-"), freq="M")
            date = period.end_time.normalize()
            rows.append(
                {
                    "source_id": self.source_id,
                    "series_id": record["indicator"],
                    "country_iso3": record["country_iso3"],
                    "date": date,
                    "value": record["value"],
                    "ingested_at": ingested_at,
                    # IRFCL publishes with roughly a one-month lag.
                    "available_at": date + pd.Timedelta(days=45),
                    "batch_id": batch_id,
                }
            )
        return pd.DataFrame(rows, columns=OBSERVATION_COLUMNS)
