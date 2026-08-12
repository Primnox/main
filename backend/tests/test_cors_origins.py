"""The CORS allowlist must cover every shell the UI is served from.

This list has a nasty failure mode: dev servers use http://localhost:5173, but
packaged builds use a custom scheme instead. A missing entry therefore works
perfectly in `npm run dev` and breaks every backend call in the shipped app —
the app launches, renders, and then silently fails at every request.

That is exactly what happened when the Tauri shell was added: the list carried
Electron's `app://.` but none of Tauri's origins.

Parsed out of server.py as text rather than by importing it, because importing
server pulls in the whole backend (torch, transformers, audio devices) and
starts background threads.
"""

import ast
import re
from pathlib import Path

import pytest

SERVER_PY = Path(__file__).resolve().parent.parent / "server.py"


def allowed_origins() -> list[str]:
    """Extract the `allow_origins=[...]` literal from the CORS middleware call."""
    source = SERVER_PY.read_text(encoding="utf-8")
    match = re.search(r"allow_origins\s*=\s*(\[.*?\])", source, re.DOTALL)
    assert match, "allow_origins list not found in server.py"
    return ast.literal_eval(match.group(1))


@pytest.fixture(scope="module")
def origins() -> list[str]:
    return allowed_origins()


class TestDevOrigins:
    @pytest.mark.parametrize(
        "origin",
        ["http://localhost:5173", "http://127.0.0.1:5173"],
    )
    def test_vite_dev_server_is_allowed(self, origins, origin):
        assert origin in origins


class TestPackagedShellOrigins:
    def test_tauri_unix_origin_is_allowed(self, origins):
        # Linux (WebKitGTK) and macOS (WKWebView) both serve from this scheme.
        assert "tauri://localhost" in origins, (
            "packaged Tauri build on Linux/macOS would have every request blocked"
        )

    def test_tauri_windows_origin_is_allowed(self, origins):
        # WebView2 maps the custom scheme onto an http(s) host instead.
        assert "http://tauri.localhost" in origins, (
            "packaged Tauri build on Windows would have every request blocked"
        )


class TestAllowlistHygiene:
    def test_no_wildcard(self, origins):
        # A wildcard would let any web page the user visits drive the local API,
        # which is unauthenticated by design.
        assert "*" not in origins

    def test_no_duplicates(self, origins):
        assert len(origins) == len(set(origins))

    def test_every_entry_has_a_scheme(self, origins):
        for origin in origins:
            assert "://" in origin, f"{origin!r} is not a valid origin"

    def test_no_remote_hosts(self, origins):
        """Only loopback and packaged-app schemes belong here."""
        allowed_hosts = {"localhost", "127.0.0.1", "tauri.localhost", "."}
        for origin in origins:
            host = origin.split("://", 1)[1].split("/")[0].rsplit(":", 1)[0]
            assert host in allowed_hosts, f"unexpected host in CORS allowlist: {origin}"


def websocket_origins() -> set:
    """Extract the `allowed_origins = {...}` literal guarding the /ws upgrade."""
    source = SERVER_PY.read_text(encoding="utf-8")
    match = re.search(r"allowed_origins\s*=\s*(\{.*?\})", source, re.DOTALL)
    assert match, "websocket allowed_origins set not found in server.py"
    return ast.literal_eval(match.group(1))


class TestWebSocketOrigins:
    """The /ws guard has its own separate allowlist, and it drifted.

    It carried Electron's `app://.` and none of Tauri's origins, so a
    packaged Tauri build would open the socket, get closed with 1008, and
    lose the entire live feed (mic, screen, chat events) while ordinary HTTP
    calls kept working — the worst kind of failure to diagnose, because the
    app looks alive.
    """

    @pytest.fixture
    def ws_origins(self):
        return websocket_origins()

    @pytest.mark.parametrize(
        "origin",
        ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"],
    )
    def test_packaged_tauri_origins_can_open_the_websocket(self, ws_origins, origin):
        assert origin in ws_origins, f"packaged Tauri build's live feed would be rejected ({origin})"

    def test_dev_server_can_open_the_websocket(self, ws_origins):
        assert "http://localhost:5173" in ws_origins

    def test_websocket_and_cors_agree_on_packaged_origins(self, ws_origins, origins):
        # Two lists that must not drift apart again: anything allowed to make
        # an HTTP call should be allowed to open the socket.
        packaged = {o for o in origins if "tauri" in o}
        assert packaged <= ws_origins, (
            f"origins allowed for HTTP but not websocket: {packaged - ws_origins}"
        )
