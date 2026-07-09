"""Command-line entry point for the sovereign-monitor pipeline.

Errors follow the `program: message` convention (lowercase, no trailing period);
later-phase commands exist but refuse to run until their lifecycle stage lands.
"""

import argparse
import sys

import httpx
import pandas as pd
import pandera.errors

from sovereign_monitor import __version__
from sovereign_monitor.configuration import Settings
from sovereign_monitor.ingestion import ADAPTERS, IngestionConfigurationError
from sovereign_monitor.logging_setup import configure_logging
from sovereign_monitor.registry import load_registry
from sovereign_monitor.schemas import TABLES

PROGRAM = "sovereign-monitor"

# Commands whose implementation arrives with a later lifecycle stage (SPEC.md).
DEFERRED_COMMANDS = {
    "build-index": "B2",
    "signals": "B3",
    "surveil": "B4",
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

    subparsers.add_parser("validate", help="re-validate the curated store against the schemas")

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
    except IngestionConfigurationError as error:
        return _fail(str(error))
    except httpx.HTTPError as error:
        return _fail(f"fetch failed for {source_id}: {error}")
    if result.quarantined:
        return _fail(f"batch {result.batch_id} failed validation and was quarantined")
    return 0


def run_validate(settings: Settings) -> int:
    """Re-check every curated table against its schema; useful after manual edits."""
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
    return exit_code


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level)

    if arguments.command == "ingest":
        return run_ingest(arguments.source, settings)
    if arguments.command == "validate":
        return run_validate(settings)
    stage = DEFERRED_COMMANDS[arguments.command]
    print(
        f"{PROGRAM}: {arguments.command} is not implemented until stage {stage} (see SPEC.md)",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
