"""Batch history log backing the volume check.

Every adapter run appends one record; the volume check compares an incoming
batch's row count against the trailing median of non-quarantined batches for
the same source (SPEC: validation rules — volume).
"""

from pathlib import Path

import pandas as pd

BATCH_LOG_FILE = "batch_log.parquet"


def _batch_log_path(data_directory: Path) -> Path:
    return data_directory / "curated" / BATCH_LOG_FILE


def append_batch_record(
    data_directory: Path,
    source_id: str,
    batch_id: str,
    ingested_at: pd.Timestamp,
    rows_in_batch: int,
    quarantined: bool,
) -> None:
    """Record one adapter run; replaying a batch overwrites its earlier record."""
    record = pd.DataFrame(
        {
            "source_id": [source_id],
            "batch_id": [batch_id],
            "ingested_at": [ingested_at],
            "rows_in_batch": [rows_in_batch],
            "quarantined": [quarantined],
        }
    )
    log_path = _batch_log_path(data_directory)
    if log_path.exists():
        combined = pd.concat([pd.read_parquet(log_path), record], ignore_index=True)
        combined = combined.sort_values("ingested_at", kind="stable").drop_duplicates(
            subset=["source_id", "batch_id"], keep="last"
        )
    else:
        combined = record
    log_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = log_path.with_name(log_path.name + ".tmp")
    combined.reset_index(drop=True).to_parquet(temporary_path, index=False)
    temporary_path.replace(log_path)


def trailing_median_rows(data_directory: Path, source_id: str, window: int = 10) -> float | None:
    """Median rows of the source's recent healthy batches; None without history."""
    log_path = _batch_log_path(data_directory)
    if not log_path.exists():
        return None
    log = pd.read_parquet(log_path)
    healthy = log[(log.source_id == source_id) & (~log.quarantined)]
    if healthy.empty:
        return None
    recent = healthy.sort_values("ingested_at").tail(window)
    return float(recent.rows_in_batch.median())
