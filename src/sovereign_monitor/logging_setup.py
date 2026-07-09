"""Structured logging setup.

Human-readable console output on a TTY; JSON lines otherwise, so scheduled
GitHub Actions runs produce machine-parseable logs (SPEC: engineering conventions).
"""

import logging
import sys

import structlog


def _stderr_logger(*_: object) -> structlog.PrintLogger:
    # Late-bind sys.stderr at logger creation so redirected or captured streams
    # (tests, CLI wrappers) never leave loggers holding a closed file.
    return structlog.PrintLogger(sys.stderr)


def configure_logging(level_name: str = "INFO") -> None:
    """Configure structlog once at process start; safe to call repeatedly."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer()
        if sys.stderr.isatty()
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=_stderr_logger,
        cache_logger_on_first_use=False,
    )
