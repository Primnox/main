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
    def test_electron_origin_is_allowed(self, origins):
        assert "app://." in origins, "packaged Electron build would be blocked"

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
