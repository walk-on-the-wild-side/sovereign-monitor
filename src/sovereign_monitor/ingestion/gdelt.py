"""GDELT DOC API adapter — the monitoring backbone for the news layer.

Licensing (SPEC register): GDELT-derived fields are open and storable; the
underlying articles' text is not, so rows carry metadata and links only.
GDELT enforces one request per 5 seconds per IP; the fetch loop spaces requests
and a violation surfaces as a loud runtime error, never silent partial data.
"""

import hashlib
import json
import time
from typing import Any, ClassVar, cast

import httpx
import pandas as pd
import yaml

from sovereign_monitor.ingestion.base import (
    IngestionConfigurationError,
    IngestionRuntimeError,
    SourceAdapter,
)
from sovereign_monitor.ingestion.rss_feeds import finalize_news_frame

REQUEST_SPACING_SECONDS = 6.0  # GDELT's published limit is one request per 5s


class GdeltAdapter(SourceAdapter):
    """Runs the per-country query plan from config/feeds.yaml against the DOC API."""

    source_id: ClassVar[str] = "gdelt"
    table: ClassVar[str] = "news_items"
    raw_suffix: ClassVar[str] = ".json"

    def _query_plan(self) -> dict[str, Any]:
        config = yaml.safe_load(self.settings.feeds_path.read_text(encoding="utf-8"))
        plan = config.get("gdelt")
        if not plan or not plan.get("queries"):
            raise IngestionConfigurationError(
                f"no gdelt query plan configured in {self.settings.feeds_path}"
            )
        return cast(dict[str, Any], plan)

    def fetch(self) -> bytes:
        plan = self._query_plan()
        envelope = []
        with httpx.Client(
            timeout=self.settings.http_timeout_seconds,
            headers={"User-Agent": self.settings.http_user_agent},
        ) as client:
            for position, item in enumerate(plan["queries"]):
                if position:
                    time.sleep(REQUEST_SPACING_SECONDS)
                response = client.get(
                    self.source.endpoint,
                    params={
                        "query": item["query"],
                        "mode": "artlist",
                        "format": "json",
                        "maxrecords": plan.get("max_records", 75),
                        "timespan": plan.get("timespan", "3d"),
                    },
                )
                response.raise_for_status()
                envelope.append({"country_iso3": item["country_iso3"], "body": response.text})
        return json.dumps(envelope).encode("utf-8")

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for item in json.loads(payload):
            try:
                body = json.loads(item["body"])
            except json.JSONDecodeError as error:
                # GDELT signals throttling as a 200 with a plain-text message.
                raise IngestionRuntimeError(
                    f"gdelt returned non-JSON for {item['country_iso3']} "
                    f"(rate limited?): {item['body'][:120]!r}"
                ) from error
            for article in body.get("articles", []):
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
