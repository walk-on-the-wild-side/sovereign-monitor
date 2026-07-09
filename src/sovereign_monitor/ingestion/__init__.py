"""Ingestion adapters: one per registry source, all sharing the base contract."""

from sovereign_monitor.ingestion.base import (
    IngestionConfigurationError,
    IngestionResult,
    SourceAdapter,
)
from sovereign_monitor.ingestion.fred import FredAdapter
from sovereign_monitor.ingestion.rss_feeds import BloombergRssAdapter

# Wired adapters, keyed by registry source id. The CLI and tests index this map;
# every key must exist in data_sources.yaml (enforced by tests/test_registry.py).
ADAPTERS: dict[str, type[SourceAdapter]] = {
    BloombergRssAdapter.source_id: BloombergRssAdapter,
    FredAdapter.source_id: FredAdapter,
}

__all__ = [
    "ADAPTERS",
    "BloombergRssAdapter",
    "FredAdapter",
    "IngestionConfigurationError",
    "IngestionResult",
    "SourceAdapter",
]
