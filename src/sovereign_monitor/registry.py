"""Loader for data_sources.yaml — the single source of truth for every data source.

Adapters must take endpoints, cadence, and licensing flags from here rather than
hard-coding them, so the registry stays authoritative (SPEC: data sources).
"""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

Redistribution = Literal["open", "attribution", "link_only", "restricted"]
Access = Literal["api", "rss", "sdmx", "bulk_csv", "scrape"]
Layer = Literal["news", "quant"]
Auth = Literal["none", "free_key", "apply", "registration"]


class Source(BaseModel):
    """One registry entry; field meanings are documented in data_sources.yaml itself."""

    id: str
    name: str
    layer: Layer
    category: str
    provides: str
    access: Access
    endpoint: str
    auth: Auth
    cadence: str
    redistribution: Redistribution
    theme_tags: list[str]
    notes: str | None = None


class Registry(BaseModel):
    """The parsed registry: metadata plus sources keyed by their stable id."""

    meta: dict[str, Any]
    sources: dict[str, Source]


def load_registry(path: Path) -> Registry:
    """Parse and validate the registry; invalid entries fail loudly at startup."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources = {entry["id"]: Source(**entry) for entry in raw["sources"]}
    return Registry(meta=raw["meta"], sources=sources)
