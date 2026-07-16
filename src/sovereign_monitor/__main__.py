"""Command-line entry point for the sovereign-monitor pipeline.

Errors follow the `program: message` convention (lowercase, no trailing period);
later-phase commands exist but refuse to run until their lifecycle stage lands.
"""

import argparse
import sys
from pathlib import Path

import httpx
import pandas as pd
import pandera.errors

from sovereign_monitor import __version__
from sovereign_monitor.configuration import Settings
from sovereign_monitor.index import build_index_exports
from sovereign_monitor.ingestion import (
    ADAPTERS,
    IngestionConfigurationError,
    IngestionRuntimeError,
)
from sovereign_monitor.logging_setup import configure_logging
from sovereign_monitor.registry import load_registry
from sovereign_monitor.schemas import TABLES
from sovereign_monitor.signals import build_signal_exports, evaluate_signals
from sovereign_monitor.storage import export_public_subset, seed_curated_from_public
from sovereign_monitor.surveillance import build_surveillance_exports, stale_sources

PROGRAM = "sovereign-monitor"

# Commands whose implementation arrives with a later lifecycle stage (SPEC.md).
DEFERRED_COMMANDS = {
    "export": "B5",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="open, reproducible sovereign-stress monitor built from free public data",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="pull one source into the local store")
    ingest.add_argument("--source", required=True, choices=sorted(ADAPTERS))

    subparsers.add_parser(
        "validate", help="re-validate the curated store and warn about stale sources"
    )
    subparsers.add_parser(
        "export-public",
        help="write the re-publishable subset of the store to public_data/",
    )
    subparsers.add_parser(
        "seed-public",
        help="seed an empty curated store from committed public_data/ (CI startup)",
    )
    subparsers.add_parser(
        "signals", help="compute anomaly/regime flags into dashboard_export/signals.csv"
    )
    subparsers.add_parser(
        "backtest", help="evaluate signals against docs/stress_events.yaml (local MLflow)"
    )
    subparsers.add_parser(
        "build-index",
        help="compute the composite index and write dashboard_export/",
    )
    subparsers.add_parser(
        "surveil",
        help="run drift/threshold/staleness checks into dashboard_export/alerts.csv",
    )

    for name, stage in DEFERRED_COMMANDS.items():
        subparsers.add_parser(name, help=f"not implemented until stage {stage}")
    return parser


def _fail(message: str) -> int:
    print(f"{PROGRAM}: {message}", file=sys.stderr)
    return 1


def run_ingest(source_id: str, settings: Settings) -> int:
    registry = load_registry(settings.registry_path)
    if source_id not in registry.sources:
        return _fail(f"source {source_id!r} is not in {settings.registry_path}")
    adapter = ADAPTERS[source_id](registry.sources[source_id], settings)
    try:
        result = adapter.run()
    except (IngestionConfigurationError, IngestionRuntimeError) as error:
        return _fail(str(error))
    except httpx.HTTPError as error:
        return _fail(f"fetch failed for {source_id}: {error}")
    if result.quarantined:
        return _fail(f"batch {result.batch_id} failed validation and was quarantined")
    return 0


def run_validate(settings: Settings) -> int:
    """Re-check every curated table against its schema, then warn about staleness."""
    exit_code = 0
    for specification in TABLES.values():
        table_path = settings.data_directory / "curated" / specification.file_name
        if not table_path.exists():
            continue
        frame = pd.read_parquet(table_path)
        try:
            specification.schema.validate(frame, lazy=True)
        except pandera.errors.SchemaErrors as error:
            exit_code = _fail(
                f"{specification.name} failed validation: "
                f"{len(error.failure_cases)} failure case(s)"
            )
        else:
            print(f"{specification.name}: {len(frame)} rows valid")
    warn_about_stale_sources(settings)
    return exit_code


def warn_about_stale_sources(settings: Settings) -> int:
    """Print a warning per source whose newest record exceeds its cadence threshold."""
    stale = stale_sources(settings)
    for source in stale:
        print(
            f"{PROGRAM}: warning: {source.source_id} newest record is {source.age_days} days old "
            f"(cadence {source.cadence}, threshold {source.threshold_days}d)"
        )
    return len(stale)


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level)

    if arguments.command == "ingest":
        return run_ingest(arguments.source, settings)
    if arguments.command == "validate":
        return run_validate(settings)
    if arguments.command == "export-public":
        exported = export_public_subset(settings)
        for table_name, row_count in exported.items():
            print(f"exported {table_name}: {row_count} rows")
        return 0
    if arguments.command == "seed-public":
        seeded = seed_curated_from_public(settings)
        for table_name, row_count in seeded.items():
            print(f"seeded {table_name}: {row_count} rows")
        return 0
    if arguments.command == "signals":
        for name, count in build_signal_exports(settings).items():
            print(f"built {name}: {count} rows")
        return 0
    if arguments.command == "backtest":
        result = evaluate_signals(settings, Path("docs/stress_events.yaml"))
        for key, value in result["metrics"].items():
            print(f"{key}: {value}")
        return 0
    if arguments.command == "build-index":
        observations_path = settings.data_directory / "curated" / "observations.parquet"
        if not observations_path.exists():
            return _fail("no curated observations to index; run ingest (or seed-public) first")
        built = build_index_exports(settings)
        for export_name, row_count in built.items():
            print(f"built {export_name}: {row_count} rows")
        return 0
    if arguments.command == "surveil":
        summary = build_surveillance_exports(settings)
        print(f"alerts: {summary['alerts']} ({summary['critical']} critical)")
        return 0
    stage = DEFERRED_COMMANDS[arguments.command]
    print(
        f"{PROGRAM}: {arguments.command} is not implemented until stage {stage} (see SPEC.md)",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
