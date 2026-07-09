"""The adapter contract every source follows.

run() is the one pipeline: fetch raw → keep raw → volume check → parse →
validate → upsert. Subclasses implement only fetch() and parse(); a batch that
fails the volume check or schema validation quarantines instead of ingesting,
and replaying a batch is a no-op (idempotency).
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
from sovereign_monitor.storage import (
    append_batch_record,
    quarantine_batch,
    trailing_median_rows,
    upsert_table,
    write_raw_payload,
)

# Volume guardrails (SPEC: validation rules): a batch outside these ratios of the
# source's trailing-median row count is quarantined as a probable fetch regression.
VOLUME_LOWER_RATIO = 0.2
VOLUME_UPPER_RATIO = 5.0
VOLUME_HISTORY_WINDOW = 10


class IngestionConfigurationError(Exception):
    """Raised when an adapter cannot run because required configuration is missing."""


class IngestionRuntimeError(Exception):
    """Raised when a source misbehaves at run time (rate limit, malformed response)."""


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
        # Pulls are daily snapshots; a same-day rerun replays the same batch and
        # dedups to a no-op. True incremental windows can refine this later.
        window = ingested_at.strftime("%Y-%m-%d")
        batch_id = self.make_batch_id(window)

        if payload is None:
            payload = self.fetch()
        write_raw_payload(
            payload, self.settings.data_directory, self.source_id, batch_id, self.raw_suffix
        )

        frame = self.parse(payload, batch_id=batch_id, ingested_at=ingested_at)

        median = trailing_median_rows(
            self.settings.data_directory, self.source_id, VOLUME_HISTORY_WINDOW
        )
        volume_in_bounds = (
            median is None
            or median == 0
            or VOLUME_LOWER_RATIO * median <= len(frame) <= VOLUME_UPPER_RATIO * median
        )
        if not volume_in_bounds:
            reason = (
                f"volume anomaly: batch has {len(frame)} rows against a trailing "
                f"median of {median:.0f}"
            )
            return self._quarantine(frame, batch_id, ingested_at, reason)

        specification = TABLES[self.table]
        try:
            validated = specification.schema.validate(frame, lazy=True)
        except pandera.errors.SchemaErrors as error:
            return self._quarantine(frame, batch_id, ingested_at, error.failure_cases.to_string())

        table_path = self.settings.data_directory / "curated" / specification.file_name
        rows_added = upsert_table(validated, table_path, specification.natural_key)
        append_batch_record(
            self.settings.data_directory,
            self.source_id,
            batch_id,
            ingested_at,
            len(validated),
            quarantined=False,
        )
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

    def _quarantine(
        self, frame: pd.DataFrame, batch_id: str, ingested_at: pd.Timestamp, reason: str
    ) -> IngestionResult:
        quarantine_directory = quarantine_batch(
            frame, self.settings.data_directory, self.source_id, batch_id, reason
        )
        append_batch_record(
            self.settings.data_directory,
            self.source_id,
            batch_id,
            ingested_at,
            len(frame),
            quarantined=True,
        )
        self.log.error(
            "batch quarantined",
            batch_id=batch_id,
            rows_in_batch=len(frame),
            quarantine_directory=str(quarantine_directory),
        )
        return IngestionResult(self.source_id, batch_id, len(frame), 0, quarantined=True)
