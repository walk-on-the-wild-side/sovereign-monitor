"""Parquet-backed store with idempotent upserts.

Ingestion must be re-runnable and backfill-capable (SPEC/CLAUDE.md), so writes
merge on each table's natural key — replaying a batch is a no-op, and a refreshed
value for an existing key wins by newest ingested_at.
"""

from pathlib import Path

import pandas as pd


def upsert_table(frame: pd.DataFrame, table_path: Path, natural_key: tuple[str, ...]) -> int:
    """Merge frame into the table at table_path; return the net number of new keys."""
    if table_path.exists():
        existing = pd.read_parquet(table_path)
        rows_before = len(existing)
        combined = pd.concat([existing, frame], ignore_index=True)
    else:
        rows_before = 0
        combined = frame.copy()

    # Stable sort by ingestion time so keep="last" retains the freshest value per key.
    combined = combined.sort_values("ingested_at", kind="stable")
    deduped = combined.drop_duplicates(subset=list(natural_key), keep="last").reset_index(drop=True)

    table_path.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename so a crash mid-write cannot corrupt the table.
    temporary_path = table_path.with_name(table_path.name + ".tmp")
    deduped.to_parquet(temporary_path, index=False)
    temporary_path.replace(table_path)
    return len(deduped) - rows_before


def write_raw_payload(
    payload: bytes, data_directory: Path, source_id: str, batch_id: str, suffix: str
) -> Path:
    """Keep the raw payload for reproducibility and backfill.

    raw/ is gitignored: it may hold redistribution-restricted values that must never
    reach the public repository (SPEC: licensing register).
    """
    raw_directory = data_directory / "raw" / source_id
    raw_directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_directory / f"{batch_id}{suffix}"
    raw_path.write_bytes(payload)
    return raw_path
