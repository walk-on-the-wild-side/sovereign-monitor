"""get_with_retry: absorbs transport errors and 5xx, surfaces everything else."""

import httpx
import pytest
import structlog

from sovereign_monitor.ingestion.http_retry import get_with_retry


def test_survives_transport_error_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise httpx.ReadError("connection reset")
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(time, "sleep", lambda _: None)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    response = get_with_retry(client, "https://api.test/x", {}, structlog.get_logger())
    assert response.status_code == 200
    assert attempts["count"] == 2


def test_survives_server_disconnect_style_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # The specific failure observed against the World Bank API in production:
    # a connection accepted then closed with no response at all.
    import time

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(time, "sleep", lambda _: None)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    response = get_with_retry(client, "https://api.test/x", {}, structlog.get_logger())
    assert response.status_code == 200
    assert attempts["count"] == 2


def test_survives_5xx_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(time, "sleep", lambda _: None)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    response = get_with_retry(client, "https://api.test/x", {}, structlog.get_logger())
    assert response.status_code == 200
    assert attempts["count"] == 3


def test_eventually_surfaces_persistent_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    monkeypatch.setattr(time, "sleep", lambda _: None)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(503, text="down"))
    )
    with pytest.raises(httpx.HTTPStatusError):
        get_with_retry(client, "https://api.test/x", {}, structlog.get_logger())


def test_4xx_never_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404, text="not found")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        get_with_retry(client, "https://api.test/x", {}, structlog.get_logger())
    assert attempts["count"] == 1
