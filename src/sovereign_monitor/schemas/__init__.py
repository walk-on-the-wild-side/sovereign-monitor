"""Pandera schemas guarding every storage boundary (SPEC: validation rules, fail-loud)."""

from sovereign_monitor.schemas.tables import (
    NEWS_ITEM_KEY,
    NEWS_ITEM_SCHEMA,
    OBSERVATION_KEY,
    OBSERVATION_SCHEMA,
    TABLES,
    TableSpecification,
)

__all__ = [
    "NEWS_ITEM_KEY",
    "NEWS_ITEM_SCHEMA",
    "OBSERVATION_KEY",
    "OBSERVATION_SCHEMA",
    "TABLES",
    "TableSpecification",
]
