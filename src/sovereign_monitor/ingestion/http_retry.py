"""Retry helper for upstream APIs that fail transiently (World Bank, in practice).

Retries on transport-level failures (connection reset, server disconnect — httpx
raises these as exceptions, not responses) and 5xx status codes; a 4xx or a
successful response returns/raises immediately on the first attempt.
"""

import time
from typing import Any

import httpx

RETRY_DELAYS_SECONDS = (5.0, 15.0, 45.0)


def get_with_retry(
    client: httpx.Client, url: str, params: dict[str, Any], log: Any
) -> httpx.Response:
    """GET with retry on transport errors and 5xx; anything else surfaces immediately."""
    attempts = len(RETRY_DELAYS_SECONDS) + 1
    for attempt in range(attempts):
        is_last_attempt = attempt == attempts - 1
        try:
            response = client.get(url, params=params)
        except httpx.TransportError as error:
            if is_last_attempt:
                raise
            delay = RETRY_DELAYS_SECONDS[attempt]
            log.warning("request failed; retrying", url=url, error=str(error), wait_seconds=delay)
            time.sleep(delay)
            continue

        if response.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
            response.raise_for_status()
            return response
        if is_last_attempt:
            response.raise_for_status()
        delay = RETRY_DELAYS_SECONDS[attempt]
        log.warning(
            "server error; retrying",
            url=url,
            status_code=response.status_code,
            wait_seconds=delay,
        )
        time.sleep(delay)
    raise AssertionError("unreachable: loop always returns or raises")
