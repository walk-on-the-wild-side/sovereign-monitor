"""World Bank adapters: WDI macro indicators and IDS creditor-dimension series.

Licensing: CC BY-4.0 (attribution) — storable and re-publishable with citation.
Leakage rule (SPEC): annual data for year Y is treated as available mid-year Y+1;
features must join on available_at, never the reference date.
"""

import json
from datetime import UTC, datetime
from typing import Any, ClassVar, cast

import httpx
import pandas as pd
import yaml

from sovereign_monitor.ingestion.base import IngestionRuntimeError, SourceAdapter
from sovereign_monitor.schemas import OBSERVATION_COLUMNS


def _scored_countries(countries_path: Any) -> list[str]:
    config = yaml.safe_load(countries_path.read_text(encoding="utf-8"))
    scored = config["scored"]
    return [iso3 for group in scored.values() for iso3 in group]


def _annual_row(
    source_id: str,
    series_id: str,
    iso3: str,
    year: int,
    value: float,
    ingested_at: pd.Timestamp,
    batch_id: str,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "series_id": series_id,
        "country_iso3": iso3,
        "date": pd.Timestamp(year=year, month=12, day=31),
        "value": value,
        "ingested_at": ingested_at,
        # Annual releases lag: year Y becomes publicly knowable ~mid-year Y+1.
        "available_at": pd.Timestamp(year=year + 1, month=7, day=1),
        "batch_id": batch_id,
    }


class WorldBankWdiAdapter(SourceAdapter):
    """Annual WDI indicators for the scored country set."""

    source_id: ClassVar[str] = "worldbank_wdi"
    table: ClassVar[str] = "observations"
    raw_suffix: ClassVar[str] = ".json"

    def _indicator_codes(self) -> list[str]:
        config = yaml.safe_load(self.settings.countries_path.read_text(encoding="utf-8"))
        return [item["code"] for item in config["series"]["worldbank_wdi"]["indicators"]]

    def fetch(self) -> bytes:
        countries = ";".join(_scored_countries(self.settings.countries_path))
        current_year = datetime.now(tz=UTC).year
        envelope: dict[str, Any] = {}
        # The WDI API intermittently stalls for tens of seconds; be patient rather
        # than flaky — a scheduled run that times out fails the whole workflow.
        with httpx.Client(
            timeout=max(self.settings.http_timeout_seconds, 300.0),
            headers={"User-Agent": self.settings.http_user_agent},
        ) as client:
            for code in self._indicator_codes():
                response = client.get(
                    f"{self.source.endpoint}/country/{countries}/indicator/{code}",
                    params={
                        "format": "json",
                        "per_page": 20000,
                        "date": f"2000:{current_year}",
                    },
                )
                response.raise_for_status()
                envelope[code] = response.json()
        return json.dumps(envelope).encode("utf-8")

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        envelope = json.loads(payload)
        rows: list[dict[str, Any]] = []
        for code, body in envelope.items():
            if not isinstance(body, list) or len(body) < 2 or body[1] is None:
                raise IngestionRuntimeError(
                    f"unexpected World Bank response for {code}: {str(body)[:160]}"
                )
            for record in body[1]:
                if record.get("value") is None:
                    continue  # trailing not-yet-reported years carry no information
                rows.append(
                    _annual_row(
                        self.source_id,
                        code,
                        record["countryiso3code"],
                        int(record["date"]),
                        float(record["value"]),
                        ingested_at,
                        batch_id,
                    )
                )
        return pd.DataFrame(rows, columns=OBSERVATION_COLUMNS)


class WorldBankIdsAdapter(SourceAdapter):
    """IDS creditor-dimension series — bilateral debt owed to China (counterpart 730)."""

    source_id: ClassVar[str] = "worldbank_ids"
    table: ClassVar[str] = "observations"
    raw_suffix: ClassVar[str] = ".json"

    def _counterpart_series(self) -> list[dict[str, str]]:
        config = yaml.safe_load(self.settings.countries_path.read_text(encoding="utf-8"))
        return cast(list[dict[str, str]], config["series"]["worldbank_ids"]["counterpart_series"])

    def fetch(self) -> bytes:
        countries = ";".join(_scored_countries(self.settings.countries_path))
        envelope: dict[str, list[Any]] = {}
        with httpx.Client(
            timeout=max(self.settings.http_timeout_seconds, 120.0),
            headers={"User-Agent": self.settings.http_user_agent},
        ) as client:
            for item in self._counterpart_series():
                series_id = f"{item['series']}.{item['suffix']}"
                url = (
                    f"{self.source.endpoint}/sources/6/country/{countries}"
                    f"/series/{item['series']}/counterpart-area/{item['counterpart']}"
                    "/time/all"
                )
                records: list[Any] = []
                page, pages = 1, 1
                while page <= pages:
                    response = client.get(
                        url, params={"format": "json", "per_page": 5000, "page": page}
                    )
                    response.raise_for_status()
                    body = response.json()
                    pages = int(body.get("pages", 1))
                    records.extend(body.get("source", {}).get("data", []))
                    page += 1
                envelope[series_id] = records
        return json.dumps(envelope).encode("utf-8")

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        envelope = json.loads(payload)
        rows: list[dict[str, Any]] = []
        for series_id, records in envelope.items():
            for record in records:
                if record.get("value") is None:
                    continue
                concepts = {item["concept"]: item for item in record.get("variable", [])}
                if "Country" not in concepts or "Time" not in concepts:
                    raise IngestionRuntimeError(
                        f"unexpected IDS record shape for {series_id}: {str(record)[:160]}"
                    )
                year = int(concepts["Time"]["value"])
                if year < 2000:
                    continue  # registry floor; IDS reaches back to 1970
                rows.append(
                    _annual_row(
                        self.source_id,
                        series_id,
                        concepts["Country"]["id"],
                        year,
                        float(record["value"]),
                        ingested_at,
                        batch_id,
                    )
                )
        return pd.DataFrame(rows, columns=OBSERVATION_COLUMNS)
