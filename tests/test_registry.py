"""The registry is the source of truth: it must parse, validate, and cover every adapter."""

from sovereign_monitor.ingestion import ADAPTERS
from sovereign_monitor.registry import Registry


def test_registry_parses_with_metadata(registry: Registry) -> None:
    assert registry.meta["schema_version"] == 1
    assert len(registry.sources) >= 20


def test_every_wired_adapter_exists_in_registry(registry: Registry) -> None:
    # An adapter without a registry entry would mean endpoints and licensing flags
    # are coming from somewhere other than the source of truth.
    for source_id in ADAPTERS:
        assert source_id in registry.sources, f"adapter {source_id} missing from registry"


def test_news_sources_are_never_open_full_text(registry: Registry) -> None:
    # Editorial policy: single-publisher news feeds must be link_only. GDELT is the
    # one news-layer source whose derived fields are open (its article text is not).
    for source in registry.sources.values():
        if source.layer == "news" and source.id != "gdelt":
            assert source.redistribution == "link_only", (
                f"news source {source.id} must be link_only"
            )
