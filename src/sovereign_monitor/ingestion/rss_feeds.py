"""RSS news adapters.

Licensing boundary (SPEC: news is link_only): we store headline metadata, the link,
and later our own summary — never the publisher's article body or feed description.

Two shapes: BloombergRssAdapter pulls the registry endpoint directly; the
multi-feed adapters (OCCRP, central banks, IGO press) read their verified feed
lists from config/feeds.yaml because one registry entry covers several outlets.
"""

import calendar
import hashlib
import json
from typing import Any, ClassVar, cast

import feedparser
import httpx
import pandas as pd
import yaml

from sovereign_monitor.ingestion.base import IngestionConfigurationError, SourceAdapter

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


def entries_to_rows(
    entries: list[Any],
    outlet: str,
    source_id: str,
    theme_tags: list[str],
    batch_id: str,
    ingested_at: pd.Timestamp,
) -> list[dict[str, Any]]:
    """Map feedparser entries to news_item rows — metadata and link only."""
    rows = []
    for entry in entries:
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
                "source_id": source_id,
                "url_hash": hashlib.sha256(link.encode("utf-8")).hexdigest(),
                "url": link,
                "title": entry.get("title", ""),
                "published_at": published_at,
                "outlet": outlet,
                # Our own summary is written later by a human or a free local LLM;
                # the feed's description is publisher content and is not stored.
                "summary_own": None,
                "theme_tags": list(theme_tags),
                "country_iso3": [],
                "tone": None,
                "ingested_at": ingested_at,
                "batch_id": batch_id,
            }
        )
    return rows


def finalize_news_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the news_items frame with exact store dtypes and in-batch dedup."""
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
        rows = entries_to_rows(
            feed.entries,
            self.outlet,
            self.source_id,
            self.source.theme_tags,
            batch_id,
            ingested_at,
        )
        return finalize_news_frame(rows)


class MultiFeedRssAdapter(SourceAdapter):
    """Shared machinery for sources whose feed list lives in config/feeds.yaml.

    The raw payload is a JSON envelope of per-feed bodies so a batch stays
    replayable even though it spans several HTTP fetches.
    """

    table: ClassVar[str] = "news_items"
    raw_suffix: ClassVar[str] = ".json"

    def _feed_list(self) -> list[dict[str, str]]:
        config = yaml.safe_load(self.settings.feeds_path.read_text(encoding="utf-8"))
        feeds = config.get(self.source_id)
        if not feeds:
            raise IngestionConfigurationError(
                f"no feeds configured for {self.source_id} in {self.settings.feeds_path}"
            )
        return cast(list[dict[str, str]], feeds)

    def fetch(self) -> bytes:
        envelope = []
        with httpx.Client(
            timeout=self.settings.http_timeout_seconds,
            headers={"User-Agent": self.settings.http_user_agent},
            follow_redirects=True,
        ) as client:
            for feed in self._feed_list():
                response = client.get(feed["url"])
                response.raise_for_status()
                envelope.append(
                    {"outlet": feed["outlet"], "url": feed["url"], "body": response.text}
                )
        return json.dumps(envelope).encode("utf-8")

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for feed in json.loads(payload):
            parsed = feedparser.parse(feed["body"])
            rows.extend(
                entries_to_rows(
                    parsed.entries,
                    feed["outlet"],
                    self.source_id,
                    self.source.theme_tags,
                    batch_id,
                    ingested_at,
                )
            )
        return finalize_news_frame(rows)


class MarketsNewsAdapter(MultiFeedRssAdapter):
    """Markets & economy news feeds (CNBC; verified list in config/feeds.yaml).

    Replaces the dead Bloomberg public RSS as the markets-news source.
    """

    source_id: ClassVar[str] = "markets_news_rss"


class OccrpAdapter(MultiFeedRssAdapter):
    """OCCRP investigations feed."""

    source_id: ClassVar[str] = "occrp"


class CentralBankPressAdapter(MultiFeedRssAdapter):
    """National central bank press feeds (verified list in config/feeds.yaml)."""

    source_id: ClassVar[str] = "central_banks_rss"


class IgoPressAdapter(MultiFeedRssAdapter):
    """IMF / World Bank / ADB / BIS press feeds (verified list in config/feeds.yaml)."""

    source_id: ClassVar[str] = "igo_press_rss"
