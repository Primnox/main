"""The websocket's origin check, including the case it used to let through.

FastAPI's HTTP middleware does not run for websocket upgrades, so CORS does
nothing here and `/ws` has to check for itself. It did — but as
`if origin is not None and origin not in ALLOWED_ORIGINS`, which refuses a wrong
origin and accepts no origin at all.

Measured against the running app before the fix:

    Origin: https://evil.example  ->  403 Forbidden
    Origin omitted entirely       ->  101 Switching Protocols   <-- full stream

Every legitimate client sends one: a browser always does, and Tauri sends
`tauri://localhost`. Its absence means the caller is not one of them, so
trusting the anonymous case more than the named one was backwards.
"""
from __future__ import annotations

import base64
import os
import socket

import pytest

from primnox2.app import ALLOWED_ORIGINS


def _handshake(port: int, origin: str | None) -> str:
    """Raw upgrade request. Returns the status line.

    Raw rather than a websocket client library, because the thing under test is
    a header a well-behaved client would always send — the test has to be able
    to leave it out.
    """
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        key = base64.b64encode(os.urandom(16)).decode()
        lines = ["GET /ws HTTP/1.1", f"Host: 127.0.0.1:{port}",
                 "Upgrade: websocket", "Connection: Upgrade",
                 f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
        if origin is not None:
            lines.append(f"Origin: {origin}")
        s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        data = s.recv(4096).decode("latin1", "replace")
    return data.splitlines()[0] if data else ""


@pytest.fixture(scope="module")
def live_port() -> int:
    """A server of our own, on an ephemeral port.

    Deliberately not the developer's running instance on 4109: pointed there,
    this suite tests whatever binary happens to be up — which during this fix
    was the unpatched one, so the regression test passed against old code and
    reported the hole as closed. A test that can be satisfied by a stale process
    is not a test.
    """
    import threading
    import time

    import uvicorn

    from primnox2.app import app

    with socket.socket() as probe:            # let the OS pick a free port
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while time.time() < deadline and not server.started:
        time.sleep(0.05)
    if not server.started:
        pytest.skip("the app did not start in time")

    yield port

    server.should_exit = True
    thread.join(timeout=10)


def test_a_known_origin_is_accepted(live_port):
    status = _handshake(live_port, "http://localhost:5273")
    assert "101" in status, f"the real frontend was refused: {status}"


def test_an_unknown_origin_is_refused(live_port):
    status = _handshake(live_port, "https://evil.example")
    assert "101" not in status, f"a foreign page got the event stream: {status}"


def test_a_missing_origin_is_refused(live_port):
    """The regression. Omitting the header used to be the way in."""
    status = _handshake(live_port, None)
    assert "101" not in status, (
        "a client that simply omitted Origin got the full live event stream — "
        "every message, turn and tool call, with no credentials")


def test_tauri_is_still_allowed():
    """The desktop shell is not a browser and must keep working."""
    assert "tauri://localhost" in ALLOWED_ORIGINS
