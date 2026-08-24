"""Security tests for the Origin check on state-changing HTTP routes
(app.py's `_verify_origin` middleware) — the fix for the CSRF finding on
/vault/setup, /vault/disable, /settings and every other POST/PATCH/PUT/DELETE
route: CORS restricts what a browser may READ from a cross-origin response,
not whether it may SEND the request, so without this check a page loaded
from anywhere could mutate this loopback server with no interaction beyond
loading it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from primnox2.app import ALLOWED_ORIGINS, app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_attacker_origin_on_settings_patch_is_rejected(client):
    """The exact exploit from the security review: a page on a malicious
    origin issuing a state-changing request must be refused, not silently
    accepted."""
    resp = client.patch("/settings",
                         json={"settings": {"provider.base_url": "https://attacker.example/v1"}},
                         headers={"Origin": "https://attacker.example"})
    assert resp.status_code == 403


def test_attacker_origin_on_vault_setup_is_rejected(client):
    resp = client.post("/vault/setup", json={},
                        headers={"Origin": "https://attacker.example"})
    assert resp.status_code == 403


def test_attacker_origin_on_vault_disable_is_rejected(client):
    resp = client.post("/vault/disable",
                        headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403


@pytest.mark.parametrize("origin", sorted(ALLOWED_ORIGINS))
def test_legitimate_frontend_origin_is_not_blocked(client, origin):
    """The check must not collateral-damage the app's own frontends. Uses
    /vault/disable rather than /vault/setup deliberately: setup has a real
    side effect (it would actually enable encryption on the shared session
    test database — vault.py's own docstring says setup_vault() "leaves the
    plaintext db in place," which is exactly what made an earlier version of
    this test corrupt state for every test after it in the same session).
    disable() on an already-disabled vault 409s immediately with no write at
    all, so a 409 here still proves the request reached the handler — it
    just proves it without mutating anything."""
    resp = client.post("/vault/disable", headers={"Origin": origin})
    assert resp.status_code == 409  # "not enabled" — reached the handler


def test_missing_origin_is_not_blocked(client):
    """Deliberately fail-open on an absent Origin: unlike a websocket
    upgrade (always sent by a real browser with Origin attached), an
    ordinary HTTP request has legitimate origin-less callers — this test
    suite's own TestClient included, which never sets one. A real
    cross-origin browser attack always carries Origin on these methods
    regardless of preflight, so failing open here does not reopen the
    exploit; it only keeps non-browser/local tooling working."""
    resp = client.post("/vault/disable")
    assert resp.status_code == 409  # reached the handler, not blocked at 403


def test_get_requests_are_never_blocked_by_origin(client):
    """Only state-changing methods are gated — a GET from any origin (or
    none) must still work, matching how CORS itself treats GET."""
    resp = client.get("/health", headers={"Origin": "https://attacker.example"})
    assert resp.status_code == 200


def test_options_preflight_is_not_blocked_by_origin_check(client):
    """OPTIONS is how CORS preflight itself arrives — the origin middleware
    must not intercept it (CORSMiddleware needs to see and answer it), only
    the actual POST/PATCH/PUT/DELETE that follows."""
    resp = client.options("/settings", headers={
        "Origin": "https://attacker.example",
        "Access-Control-Request-Method": "PATCH",
    })
    assert resp.status_code != 403
