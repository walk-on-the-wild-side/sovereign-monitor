"""Licensing-aware export of the curated store to the committed public_data/ tree.

The repo is public, so only re-publishable rows may be committed: observations
from sources whose registry flag is open or attribution. News items are always
exportable because the store holds only metadata + links by construction
(link_only). Restricted raw values (FRED ICE BofA, yfinance) never leave data/.

public_data/ doubles as durable state for scheduled runs: an ephemeral CI runner
seeds its curated store from it, ingests, and commits the refreshed subset back.
"""

from pathlib import Path

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.registry import load_registry
from sovereign_monitor.schemas import TABLES

PUBLIC_REDISTRIBUTION_FLAGS = {"open", "attribution"}


def export_public_subset(settings: Settings) -> dict[str, int]:
    """Write the re-publishable subset; return exported row counts per table."""
    registry = load_registry(settings.registry_path)
    public_sources = {
        source_id
        for source_id, source in registry.sources.items()
        if source.redistribution in PUBLIC_REDISTRIBUTION_FLAGS
    }

    settings.public_data_directory.mkdir(parents=True, exist_ok=True)
    exported: dict[str, int] = {}
    for specification in TABLES.values():
        curated_path = settings.data_directory / "curated" / specification.file_name
        if not curated_path.exists():
            continue
        frame = pd.read_parquet(curated_path)
        if specification.name == "observations":
            frame = frame[frame.source_id.isin(public_sources)].reset_index(drop=True)
        _write_atomically(frame, settings.public_data_directory / specification.file_name)
        exported[specification.name] = len(frame)
    return exported


def seed_curated_from_public(settings: Settings) -> dict[str, int]:
    """Load committed public data into an empty curated store (CI runner startup)."""
    seeded: dict[str, int] = {}
    for specification in TABLES.values():
        public_path = settings.public_data_directory / specification.file_name
        curated_path = settings.data_directory / "curated" / specification.file_name
        if not public_path.exists() or curated_path.exists():
            continue
        frame = pd.read_parquet(public_path)
        curated_path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomically(frame, curated_path)
        seeded[specification.name] = len(frame)
    return seeded


def _write_atomically(frame: pd.DataFrame, path: Path) -> None:
    temporary_path = path.with_name(path.name + ".tmp")
    frame.to_parquet(temporary_path, index=False)
    temporary_path.replace(path)
