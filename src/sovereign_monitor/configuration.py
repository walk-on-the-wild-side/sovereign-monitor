"""Typed runtime configuration.

Every tunable comes from the environment or a local .env file so nothing is
hard-coded and no secret can end up in the repository (SPEC: compliance).
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings; field names map 1:1 to upper-cased environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Secrets — free keys only, per the no-billing constraint.
    fred_api_key: str | None = None

    log_level: str = "INFO"

    # Local data layout: raw/ and quarantine/ under this root are gitignored because
    # they may hold redistribution-restricted values (SPEC: licensing register).
    data_directory: Path = Path("data")

    registry_path: Path = Path("data_sources.yaml")
    countries_path: Path = Path("config/countries.yaml")

    http_timeout_seconds: float = 30.0
    http_user_agent: str = (
        "sovereign-monitor/0.1.0 "
        "(open research; github.com/walk-on-the-wild-side/sovereign-monitor)"
    )
