"""GDELT adapter — the monitoring backbone for the news layer.

Two transports, selected in config/feeds.yaml:

- "bulk" (the working default): the raw 15-minute event export files — plain
  downloads with no rate limit. Events are filtered to the scored countries and
  emitted as link-only news rows carrying GDELT's average tone.
- "doc": the DOC API per-country query plan. Kept for the day the API recovers —
  as of 2026-07-10 it 429s every request from every IP we tested, even through
  hard exponential backoff.

Licensing (SPEC register): GDELT-derived fields are open and storable; the
underlying articles' text is not, so rows carry metadata and links only.
"""

import csv
import hashlib
import io
import json
import time
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, cast
from urllib.parse import urlparse

import httpx
import pandas as pd
import yaml

from sovereign_monitor.ingestion.base import (
    IngestionConfigurationError,
    IngestionRuntimeError,
    SourceAdapter,
)
from sovereign_monitor.ingestion.rss_feeds import finalize_news_frame

REQUEST_SPACING_SECONDS = 6.0  # the DOC API's published limit is one request per 5s

# Backoff schedule for DOC API 429s. GDELT limits per IP, and shared CI egress
# IPs are saturated by other users' scrapers. One query that exhausts its
# retries aborts the whole batch, so the worst-case wait stays bounded.
RETRY_DELAYS_SECONDS = (30.0, 75.0, 150.0)

# Event export layout: tab-separated, 61 fields, no header (GDELT 2.0 codebook).
EXPORT_FIELD_COUNT = 61
FIELD_AVERAGE_TONE = 34
FIELD_ACTION_GEO_COUNTRY = 53  # FIPS 10-4 two-letter code, not ISO
FIELD_DATE_ADDED = 59  # YYYYMMDDHHMMSS, UTC
FIELD_SOURCE_URL = 60

# FIPS 10-4 → ISO3 for the scored set (SPEC scope).
FIPS_TO_ISO3 = {
    "PK": "PAK",
    "CE": "LKA",
    "BG": "BGD",
    "NP": "NPL",
    "MV": "MDV",
    "IN": "IND",
    "KZ": "KAZ",
    "UZ": "UZB",
    "KG": "KGZ",
    "TI": "TJK",
    "MG": "MNG",
    "LA": "LAO",
}


def _get_with_backoff(
    client: httpx.Client, url: str, params: dict[str, Any], log: Any
) -> httpx.Response:
    """GET with hard backoff on 429; any other error surfaces immediately."""
    for delay in RETRY_DELAYS_SECONDS:
        response = client.get(url, params=params)
        if response.status_code != httpx.codes.TOO_MANY_REQUESTS:
            response.raise_for_status()
            return response
        log.warning("gdelt rate limited; backing off", wait_seconds=delay)
        time.sleep(delay)
    response = client.get(url, params=params)
    response.raise_for_status()
    return response


def _title_from_url(url: str) -> str:
    """Bulk events carry no headline; derive a readable label from the URL slug."""
    path = urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    slug = slug.rsplit(".", 1)[0]
    words = [w for w in slug.replace("_", "-").split("-") if w and not w.isdigit()]
    if not words:
        return urlparse(url).netloc
    return " ".join(words).capitalize()


def rows_from_export_csv(data: bytes) -> list[dict[str, Any]]:
    """Filter one export file to scored-country events — GDELT-derived fields only."""
    rows: list[dict[str, Any]] = []
    text = data.decode("utf-8", errors="replace")
    for record in csv.reader(io.StringIO(text), delimiter="\t"):
        if len(record) != EXPORT_FIELD_COUNT:
            continue
        iso3 = FIPS_TO_ISO3.get(record[FIELD_ACTION_GEO_COUNTRY])
        if iso3 is None:
            continue
        url = record[FIELD_SOURCE_URL]
        if not url.startswith("http"):
            continue
        try:
            tone: float | None = float(record[FIELD_AVERAGE_TONE])
        except ValueError:
            tone = None
        rows.append(
            {
                "country_iso3": iso3,
                "url": url,
                "date_added": record[FIELD_DATE_ADDED],
                "tone": tone,
            }
        )
    return rows


class GdeltAdapter(SourceAdapter):
    """Runs the configured GDELT plan (bulk exports or DOC API queries)."""

    source_id: ClassVar[str] = "gdelt"
    table: ClassVar[str] = "news_items"
    raw_suffix: ClassVar[str] = ".json"

    def _plan(self) -> dict[str, Any]:
        config = yaml.safe_load(self.settings.feeds_path.read_text(encoding="utf-8"))
        plan = config.get("gdelt")
        if not plan:
            raise IngestionConfigurationError(
                f"no gdelt plan configured in {self.settings.feeds_path}"
            )
        return cast(dict[str, Any], plan)

    def fetch(self) -> bytes:
        plan = self._plan()
        if plan.get("mode", "doc") == "bulk":
            return self._fetch_bulk(plan)
        return self._fetch_doc_api(plan)

    def _fetch_bulk(self, plan: dict[str, Any]) -> bytes:
        bulk = plan.get("bulk") or {}
        base_url = bulk.get("base_url", "http://data.gdeltproject.org/gdeltv2")
        files_per_run = int(bulk.get("files_per_run", 96))

        # Export files land on a 15-minute grid with ~15 minutes of publish lag.
        now = datetime.now(tz=UTC)
        newest = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0) - timedelta(
            minutes=15
        )

        collected: list[dict[str, Any]] = []
        files_found = 0
        with httpx.Client(
            timeout=max(self.settings.http_timeout_seconds, 120.0),
            headers={"User-Agent": self.settings.http_user_agent},
            follow_redirects=True,
        ) as client:
            for index in range(files_per_run):
                stamp = (newest - timedelta(minutes=15 * index)).strftime("%Y%m%d%H%M%S")
                response = client.get(f"{base_url}/{stamp}.export.CSV.zip")
                if response.status_code == httpx.codes.NOT_FOUND:
                    continue  # GDELT occasionally skips a window
                response.raise_for_status()
                archive = zipfile.ZipFile(io.BytesIO(response.content))
                for name in archive.namelist():
                    collected.extend(rows_from_export_csv(archive.read(name)))
                files_found += 1
        if files_found == 0:
            raise IngestionRuntimeError("gdelt bulk: no export files found on the 15-minute grid")
        self.log.info("gdelt bulk fetched", files=files_found, event_rows=len(collected))
        # The raw payload keeps only GDELT-derived fields (open license), already
        # filtered — persisting ~100 zips per day verbatim buys nothing.
        return json.dumps({"mode": "bulk", "rows": collected}).encode("utf-8")

    def _fetch_doc_api(self, plan: dict[str, Any]) -> bytes:
        if not plan.get("queries"):
            raise IngestionConfigurationError(
                f"no gdelt query plan configured in {self.settings.feeds_path}"
            )
        envelope = []
        with httpx.Client(
            timeout=self.settings.http_timeout_seconds,
            headers={"User-Agent": self.settings.http_user_agent},
        ) as client:
            for position, item in enumerate(plan["queries"]):
                if position:
                    time.sleep(REQUEST_SPACING_SECONDS)
                response = _get_with_backoff(
                    client,
                    self.source.endpoint,
                    {
                        "query": item["query"],
                        "mode": "artlist",
                        "format": "json",
                        "maxrecords": plan.get("max_records", 75),
                        "timespan": plan.get("timespan", "3d"),
                    },
                    self.log,
                )
                envelope.append({"country_iso3": item["country_iso3"], "body": response.text})
        return json.dumps(envelope).encode("utf-8")

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        body = json.loads(payload)
        if isinstance(body, dict) and body.get("mode") == "bulk":
            return self._parse_bulk(body, batch_id, ingested_at)
        return self._parse_doc_api(body, batch_id, ingested_at)

    def _parse_bulk(
        self, body: dict[str, Any], batch_id: str, ingested_at: pd.Timestamp
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for item in body["rows"]:
            url = item["url"]
            date_added = item.get("date_added")
            published_at = (
                pd.to_datetime(date_added, format="%Y%m%d%H%M%S", utc=True)
                if date_added
                else pd.NaT
            )
            rows.append(
                {
                    "source_id": self.source_id,
                    "url_hash": hashlib.sha256(url.encode("utf-8")).hexdigest(),
                    "url": url,
                    "title": _title_from_url(url),
                    "published_at": published_at,
                    "outlet": urlparse(url).netloc,
                    "summary_own": None,
                    "theme_tags": list(self.source.theme_tags),
                    "country_iso3": [item["country_iso3"]],
                    "tone": item.get("tone"),
                    "ingested_at": ingested_at,
                    "batch_id": batch_id,
                }
            )
        return finalize_news_frame(rows)

    def _parse_doc_api(
        self, body: list[dict[str, Any]], batch_id: str, ingested_at: pd.Timestamp
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for item in body:
            try:
                articles = json.loads(item["body"])
            except json.JSONDecodeError as error:
                # GDELT signals throttling as a 200 with a plain-text message.
                raise IngestionRuntimeError(
                    f"gdelt returned non-JSON for {item['country_iso3']} "
                    f"(rate limited?): {item['body'][:120]!r}"
                ) from error
            for article in articles.get("articles", []):
                url = article.get("url")
                if not url:
                    continue
                seendate = article.get("seendate")
                published_at = (
                    pd.to_datetime(seendate, format="%Y%m%dT%H%M%SZ", utc=True)
                    if seendate
                    else pd.NaT
                )
                rows.append(
                    {
                        "source_id": self.source_id,
                        "url_hash": hashlib.sha256(url.encode("utf-8")).hexdigest(),
                        "url": url,
                        "title": article.get("title", ""),
                        "published_at": published_at,
                        "outlet": article.get("domain", ""),
                        "summary_own": None,
                        "theme_tags": list(self.source.theme_tags),
                        # The query that surfaced the article tags its country; an
                        # article matching several queries keeps the first tag.
                        "country_iso3": [item["country_iso3"]],
                        "tone": None,
                        "ingested_at": ingested_at,
                        "batch_id": batch_id,
                    }
                )
        return finalize_news_frame(rows)
