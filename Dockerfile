# Dockerfile — reproducible runtime for the sovereign-monitor pipeline.
# Multi-stage: dependencies resolve with uv in the builder; the runtime stage is a
# slim image holding only the virtual environment, the package, and its config inputs.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
# Resolve third-party dependencies first so this layer caches across source edits.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev
COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-dev

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY data_sources.yaml ./
COPY config ./config
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "-m", "sovereign_monitor"]
CMD ["--help"]
