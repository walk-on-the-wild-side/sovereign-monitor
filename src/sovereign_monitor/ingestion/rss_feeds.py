"""RSS news adapters.

Licensing boundary (SPEC: news is link_only): we store headline metadata, the link,
and later our own summary — never the publisher's article body or feed description.
"""

import calendar
import hashlib
from typing import ClassVar

import feedparser
import httpx
import pandas as pd

from sovereign_monitor.ingestion.base import SourceAdapter

NEWS_ITEM_COLUMNS = [
    "source_id",
    "url_hash",
    "url",
    "title",
    "published_at",
    "outlet",
    "summary_own",
    "theme_tags",
    "country_iso3",
    "tone",
    "ingested_at",
    "batch_id",
]


class BloombergRssAdapter(SourceAdapter):
    """Bloomberg public markets feed: headlines and links only."""

    source_id: ClassVar[str] = "bloomberg_rss"
    table: ClassVar[str] = "news_items"
    raw_suffix: ClassVar[str] = ".xml"
    outlet: ClassVar[str] = "Bloomberg"

    def fetch(self) -> bytes:
        response = httpx.get(
            self.source.endpoint,
            timeout=self.settings.http_timeout_seconds,
            headers={"User-Agent": self.settings.http_user_agent},
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.content

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        feed = feedparser.parse(payload)
        rows = []
        for entry in feed.entries:
            link = entry.get("link")
            if not link:
                continue
            # feedparser's *_parsed structs are UTC; timegm (not mktime) preserves that.
            published_struct = entry.get("published_parsed")
            published_at = (
                pd.Timestamp(calendar.timegm(published_struct), unit="s", tz="UTC")
                if published_struct
                else pd.NaT
            )
            rows.append(
                {
                    "source_id": self.source_id,
                    "url_hash": hashlib.sha256(link.encode("utf-8")).hexdigest(),
                    "url": link,
                    "title": entry.get("title", ""),
                    "published_at": published_at,
                    "outlet": self.outlet,
                    # Our own summary is written later by a human or a free local LLM;
                    # the feed's description is publisher content and is not stored.
                    "summary_own": None,
                    "theme_tags": list(self.source.theme_tags),
                    "country_iso3": [],
                    "tone": None,
                    "ingested_at": ingested_at,
                    "batch_id": batch_id,
                }
            )
        frame = pd.DataFrame(rows, columns=NEWS_ITEM_COLUMNS)
        # Feeds repeat items across pulls of the same day; dedup inside the batch so
        # the primary-key uniqueness check reflects the source, not feed mechanics.
        frame = frame.drop_duplicates(subset=["source_id", "url_hash"], keep="first")
        # pandas infers coarser datetime units (s/us) from python objects; the store
        # standardizes on nanoseconds, which the schema enforces exactly.
        frame["published_at"] = pd.to_datetime(frame["published_at"], utc=True).astype(
            "datetime64[ns, UTC]"
        )
        frame["ingested_at"] = pd.to_datetime(frame["ingested_at"], utc=True).astype(
            "datetime64[ns, UTC]"
        )
        frame["tone"] = frame["tone"].astype("float64")
        return frame.reset_index(drop=True)
