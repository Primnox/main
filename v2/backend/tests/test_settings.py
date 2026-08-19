"""Runtime settings.

The security-shaped tests matter most here. This endpoint writes environment
variables and handles an API key, and it is reachable over HTTP — so the tests
that earn their place are the ones asserting what it refuses to do.
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from primnox2.app import app
from primnox2.settings import service as settings
from primnox2.storage import db


@pytest.fixture(autouse=True)
def clean_settings():
    with db.tx() as c:
        c.execute("DELETE FROM settings")
    saved = {env: os.environ.get(env) for env in settings.ENV_KEYS.values()}
    yield
    with db.tx() as c:
        c.execute("DELETE FROM settings")
    for env, value in saved.items():
        if value is None:
            os.environ.pop(env, None)
        else:
            os.environ[env] = value


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ── what it refuses ──────────────────────────────────────────────────────────
def test_the_api_key_is_never_stored_in_the_database():
    """schema.sql says secrets do not live in the settings table, and it is not
    decoration: primnox.db gets copied, browsed, and attached to bug reports."""
    result = settings.set_many({"provider.api_key": "sk-should-not-persist"})
    assert result["stored"] == {}
    assert "provider.api_key" in result["rejected"]

    dump = json.dumps([dict(r) for r in db.connect().execute("SELECT * FROM settings")])
    assert "sk-should-not-persist" not in dump


def test_an_unknown_setting_is_refused():
    """The store maps keys to environment variables. An open key/value store
    reachable over HTTP is a way to set arbitrary env vars on the host."""
    result = settings.set_many({"PATH": "/tmp/evil", "anything.else": "x"})
    assert result["stored"] == {}
    assert set(result["rejected"]) == {"PATH", "anything.else"}
    assert os.environ.get("PATH") != "/tmp/evil"


def test_a_closed_choice_rejects_a_typo():
    """Free text would let 'saf' silently mean 'prompt for everything', which
    reads as the app being broken rather than as a typo."""
    assert settings.set_many({"sandbox.auto_approve": "saf"})["rejected"]
    assert settings.set_many({"sandbox.auto_approve": "safe"})["stored"]


def test_describe_never_returns_the_key(monkeypatch):
    monkeypatch.setenv("PRIMNOX_API_KEY", "sk-live-secret-value")
    described = settings.describe()
    assert described["api_key_present"] is True
    assert "sk-live-secret-value" not in json.dumps(described)


# ── what it does ─────────────────────────────────────────────────────────────
def test_a_saved_setting_applies_to_the_running_process():
    """`active_provider()` reads os.environ on every call, so a model change
    should take effect on the next turn rather than the next restart."""
    settings.set_many({"provider.model": "some-model-v9"})
    assert os.environ["PRIMNOX_MODEL"] == "some-model-v9"


def test_clearing_a_setting_removes_the_variable():
    settings.set_many({"provider.model": "temporary"})
    settings.set_many({"provider.model": ""})
    assert "PRIMNOX_MODEL" not in os.environ


def test_a_real_environment_variable_outranks_a_stored_one(monkeypatch):
    """An operator setting a variable on the command line did it on purpose. A
    value saved in the UI months ago must not silently override it."""
    settings.set_many({"provider.model": "stored-model"})
    monkeypatch.setenv("PRIMNOX_MODEL", "command-line-model")

    settings.apply_to_environment()
    assert os.environ["PRIMNOX_MODEL"] == "command-line-model"


def test_stored_settings_are_applied_when_the_variable_is_absent():
    settings.set_many({"provider.base_url": "https://example.test"})
    os.environ.pop("PRIMNOX_BASE_URL", None)

    applied = settings.apply_to_environment()
    assert "PRIMNOX_BASE_URL" in applied
    assert os.environ["PRIMNOX_BASE_URL"] == "https://example.test"


# ── HTTP ─────────────────────────────────────────────────────────────────────
def test_settings_round_trip_over_http(client):
    r = client.patch("/settings", json={"settings": {"provider.model": "http-model"}})
    assert r.status_code == 200
    assert r.json()["effective"]["provider.model"] == "http-model"
    assert client.get("/settings").json()["effective"]["provider.model"] == "http-model"


def test_the_endpoint_reports_what_it_rejected(client):
    r = client.patch("/settings", json={"settings": {"sandbox.auto_approve": "nope"}})
    assert r.status_code == 200
    assert "sandbox.auto_approve" in r.json()["rejected"]


def test_an_omitted_key_does_not_clear_the_stored_one(client, monkeypatch):
    """Saving the panel without touching the key field must not wipe a working
    config — the field is blank because it is never read back, not because the
    user wants it gone."""
    monkeypatch.setenv("PRIMNOX_API_KEY", "sk-existing")
    client.patch("/settings", json={"settings": {"provider.model": "x"}})
    assert os.environ.get("PRIMNOX_API_KEY") == "sk-existing"
