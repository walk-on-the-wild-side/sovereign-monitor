"""The adapter contract every source follows.

run() is the one pipeline: fetch raw → keep raw → parse → validate → upsert.
Subclasses implement only fetch() and parse(); validation failure quarantines the
batch instead of ingesting it, and replaying a batch is a no-op (idempotency).
"""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

import pandas as pd
import pandera.errors
import structlog

from sovereign_monitor.configuration import Settings
from sovereign_monitor.registry import Source
from sovereign_monitor.schemas import TABLES
from sovereign_monitor.storage import quarantine_batch, upsert_table, write_raw_payload


class IngestionConfigurationError(Exception):
    """Raised when an adapter cannot run because required configuration is missing."""


@dataclass(frozen=True)
class IngestionResult:
    """Outcome of one adapter run, for logging and CLI exit codes."""

    source_id: str
    batch_id: str
    rows_in_batch: int
    rows_added: int
    quarantined: bool


class SourceAdapter(ABC):
    """Base class for all ingestion adapters.

    Class attributes bind the adapter to its registry entry and curated table;
    the constructor refuses a mismatched registry Source so endpoints can never
    silently come from the wrong entry.
    """

    source_id: ClassVar[str]
    table: ClassVar[str]  # key into schemas.TABLES
    raw_suffix: ClassVar[str]  # file extension for the raw payload, e.g. ".xml"

    def __init__(self, source: Source, settings: Settings) -> None:
        if source.id != self.source_id:
            raise ValueError(
                f"adapter {type(self).__name__} expects registry source "
                f"{self.source_id!r}, got {source.id!r}"
            )
        self.source = source
        self.settings = settings
        self.log = structlog.get_logger().bind(source_id=self.source_id)

    @abstractmethod
    def fetch(self) -> bytes:
        """Pull the raw payload from the source endpoint."""

    @abstractmethod
    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        """Turn a raw payload into rows matching this adapter's table schema."""

    def make_batch_id(self, window: str) -> str:
        """Batch identity is (source, request window): same window → same batch."""
        return hashlib.sha256(f"{self.source_id}:{window}".encode()).hexdigest()[:16]

    def run(self, payload: bytes | None = None) -> IngestionResult:
        """Execute the full pipeline; pass payload to replay a batch without fetching."""
        ingested_at = pd.Timestamp(datetime.now(tz=UTC))
        # Phase 0 pulls are daily snapshots; a same-day rerun replays the same batch
        # and dedups to a no-op. B1 adds true incremental windows.
        window = ingested_at.strftime("%Y-%m-%d")
        batch_id = self.make_batch_id(window)

        if payload is None:
            payload = self.fetch()
        write_raw_payload(
            payload, self.settings.data_directory, self.source_id, batch_id, self.raw_suffix
        )

        frame = self.parse(payload, batch_id=batch_id, ingested_at=ingested_at)
        specification = TABLES[self.table]
        try:
            validated = specification.schema.validate(frame, lazy=True)
        except pandera.errors.SchemaErrors as error:
            reason = error.failure_cases.to_string()
            quarantine_directory = quarantine_batch(
                frame, self.settings.data_directory, self.source_id, batch_id, reason
            )
            self.log.error(
                "batch quarantined",
                batch_id=batch_id,
                rows_in_batch=len(frame),
                quarantine_directory=str(quarantine_directory),
            )
            return IngestionResult(self.source_id, batch_id, len(frame), 0, quarantined=True)

        table_path = self.settings.data_directory / "curated" / specification.file_name
        rows_added = upsert_table(validated, table_path, specification.natural_key)
        self.log.info(
            "batch ingested",
            batch_id=batch_id,
            rows_in_batch=len(validated),
            rows_added=rows_added,
            table=str(table_path),
        )
        return IngestionResult(
            self.source_id, batch_id, len(validated), rows_added, quarantined=False
        )
