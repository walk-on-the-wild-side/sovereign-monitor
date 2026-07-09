"""Shared test fixtures: isolated settings pointing at a temporary data directory.

Tests never read the developer's .env and never touch the network; adapters are
exercised by replaying recorded payloads from tests/fixtures/ (SPEC: testing & CI).
"""

from pathlib import Path

import pytest
from pydantic_settings import SettingsConfigDict

from sovereign_monitor.configuration import Settings
from sovereign_monitor.registry import Registry, load_registry

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIRECTORY = Path(__file__).resolve().parent / "fixtures"


class IsolatedSettings(Settings):
    """Settings that ignore the developer's .env so tests stay hermetic."""

    model_config = SettingsConfigDict(env_file=None)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return IsolatedSettings(
        fred_api_key=None,
        data_directory=tmp_path / "data",
        public_data_directory=tmp_path / "public_data",
        registry_path=PROJECT_ROOT / "data_sources.yaml",
        countries_path=PROJECT_ROOT / "config" / "countries.yaml",
        feeds_path=PROJECT_ROOT / "config" / "feeds.yaml",
    )


@pytest.fixture(scope="session")
def registry() -> Registry:
    return load_registry(PROJECT_ROOT / "data_sources.yaml")
