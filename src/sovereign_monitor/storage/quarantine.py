"""Quarantine for batches that fail validation.

Bad batches are preserved with a machine-readable reason instead of being ingested
or discarded, so failures stay debuggable (SPEC: validation rules, fail-loud).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def quarantine_batch(
    frame: pd.DataFrame,
    data_directory: Path,
    source_id: str,
    batch_id: str,
    reason: str,
) -> Path:
    """Write the offending batch plus reason.json; return the quarantine directory."""
    quarantine_directory = data_directory / "quarantine" / source_id / batch_id
    quarantine_directory.mkdir(parents=True, exist_ok=True)

    try:
        frame.to_parquet(quarantine_directory / "batch.parquet", index=False)
    except Exception:  # a malformed frame is exactly what lands here; keep it anyway
        # Parquet needs consistent column types; a corrupted batch may not have them.
        frame.to_csv(quarantine_directory / "batch.csv", index=False)

    reason_record = {
        "source_id": source_id,
        "batch_id": batch_id,
        "quarantined_at": datetime.now(tz=UTC).isoformat(),
        "reason": reason,
    }
    (quarantine_directory / "reason.json").write_text(
        json.dumps(reason_record, indent=2), encoding="utf-8"
    )
    return quarantine_directory
