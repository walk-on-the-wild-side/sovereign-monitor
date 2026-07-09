"""Ingestion adapters: one per registry source, all sharing the base contract."""

from sovereign_monitor.ingestion.base import (
    IngestionConfigurationError,
    IngestionResult,
    IngestionRuntimeError,
    SourceAdapter,
)
from sovereign_monitor.ingestion.bulk_csv import AidDataAdapter, NdGainAdapter
from sovereign_monitor.ingestion.frankfurter import FrankfurterAdapter
from sovereign_monitor.ingestion.fred import FredAdapter
from sovereign_monitor.ingestion.gdelt import GdeltAdapter
from sovereign_monitor.ingestion.imf_sdmx import ImfSdmxAdapter
from sovereign_monitor.ingestion.rss_feeds import (
    BloombergRssAdapter,
    CentralBankPressAdapter,
    IgoPressAdapter,
    OccrpAdapter,
)
from sovereign_monitor.ingestion.worldbank import WorldBankIdsAdapter, WorldBankWdiAdapter
from sovereign_monitor.ingestion.yfinance_prices import YfinancePricesAdapter

# Wired adapters, keyed by registry source id. The CLI and tests index this map;
# every key must exist in data_sources.yaml (enforced by tests/test_registry.py).
# reuters_via_gnews is deliberately absent: its workaround broke (see registry).
ADAPTERS: dict[str, type[SourceAdapter]] = {
    BloombergRssAdapter.source_id: BloombergRssAdapter,
    OccrpAdapter.source_id: OccrpAdapter,
    CentralBankPressAdapter.source_id: CentralBankPressAdapter,
    IgoPressAdapter.source_id: IgoPressAdapter,
    GdeltAdapter.source_id: GdeltAdapter,
    FredAdapter.source_id: FredAdapter,
    FrankfurterAdapter.source_id: FrankfurterAdapter,
    YfinancePricesAdapter.source_id: YfinancePricesAdapter,
    WorldBankWdiAdapter.source_id: WorldBankWdiAdapter,
    WorldBankIdsAdapter.source_id: WorldBankIdsAdapter,
    ImfSdmxAdapter.source_id: ImfSdmxAdapter,
    NdGainAdapter.source_id: NdGainAdapter,
    AidDataAdapter.source_id: AidDataAdapter,
}

__all__ = [
    "ADAPTERS",
    "AidDataAdapter",
    "BloombergRssAdapter",
    "CentralBankPressAdapter",
    "FrankfurterAdapter",
    "FredAdapter",
    "GdeltAdapter",
    "IgoPressAdapter",
    "ImfSdmxAdapter",
    "IngestionConfigurationError",
    "IngestionResult",
    "IngestionRuntimeError",
    "NdGainAdapter",
    "OccrpAdapter",
    "SourceAdapter",
    "WorldBankIdsAdapter",
    "WorldBankWdiAdapter",
    "YfinancePricesAdapter",
]
