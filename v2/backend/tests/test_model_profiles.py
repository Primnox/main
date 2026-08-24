"""Saved model profiles.

The tests that matter are about the key: where it goes, where it must not go,
and what happens to the previous one when you switch endpoints.
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from primnox2.app import app
from primnox2.settings import models
from primnox2.storage import db

PROBE = "sk-profile-secret-value"


@pytest.fixture(autouse=True)
def clean_profiles():
    saved = {k: os.environ.get(k) for k in
             ("PRIMNOX_BASE_URL", "PRIMNOX_API_TYPE", "PRIMNOX_MODEL", "PRIMNOX_API_KEY")}
    with db.tx() as c:
        c.execute("DELETE FROM settings WHERE key LIKE 'provider.%'")
    yield
    for name in ("Crucible Cloud", "Crucible Local", "Temp"):
        try:
            models.set_key(name, "")
        except Exception:
            pass
    with db.tx() as c:
        c.execute("DELETE FROM settings WHERE key LIKE 'provider.%'")
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ── the key ──────────────────────────────────────────────────────────────────
@pytest.mark.skipif(not models.keyring_available(), reason="no OS keyring")
def test_the_key_never_reaches_the_database():
    models.save({"name": "Crucible Cloud", "base_url": "https://example.test",
                 "api_type": "anthropic", "model": "m1", "api_key": PROBE})

    dump = json.dumps([dict(r) for r in db.connect().execute("SELECT * FROM settings")])
    assert PROBE not in dump, "the API key was persisted to primnox.db"
    assert models.has_key("Crucible Cloud")


@pytest.mark.skipif(not models.keyring_available(), reason="no OS keyring")
def test_describe_reports_the_key_without_returning_it():
    models.save({"name": "Crucible Cloud", "base_url": "https://example.test",
                 "api_type": "anthropic", "model": "m1", "api_key": PROBE})
    described = models.describe()
    assert PROBE not in json.dumps(described)
    assert any(p["name"] == "Crucible Cloud" and p["has_key"] for p in described["profiles"])


@pytest.mark.skipif(not models.keyring_available(), reason="no OS keyring")
def test_switching_to_a_keyless_profile_clears_the_previous_key():
    """The failure this prevents: activating a local endpoint while the previous
    profile's cloud key is still in the environment sends that credential to a
    host the user did not choose to send it to."""
    models.save({"name": "Crucible Cloud", "base_url": "https://example.test",
                 "api_type": "anthropic", "model": "m1", "api_key": PROBE})
    models.save({"name": "Crucible Local", "base_url": "http://127.0.0.1:11434/v1",
                 "api_type": "openai", "model": "local", "api_key": ""})

    models.activate("Crucible Cloud")
    assert os.environ["PRIMNOX_API_KEY"] == PROBE

    models.activate("Crucible Local")
    assert "PRIMNOX_API_KEY" not in os.environ, "a cloud key survived into a local profile"


def test_deleting_a_profile_forgets_its_credential():
    models.save({"name": "Temp", "base_url": "https://x.test",
                 "api_type": "openai", "model": "m", "api_key": PROBE})
    assert models.delete("Temp") is True
    assert models.get_key("Temp") == ""
    assert not any(p["name"] == "Temp" for p in models.profiles())


# ── activation ───────────────────────────────────────────────────────────────
def test_activation_drives_the_environment():
    """One resolution path: the gateway reads os.environ, so activation writes
    there rather than giving the gateway a second source to disagree with."""
    models.save({"name": "Crucible Local", "base_url": "http://127.0.0.1:11434/v1",
                 "api_type": "openai", "model": "qwen-test"})
    models.activate("Crucible Local")

    assert os.environ["PRIMNOX_MODEL"] == "qwen-test"
    assert os.environ["PRIMNOX_BASE_URL"] == "http://127.0.0.1:11434/v1"
    assert models.active_name() == "Crucible Local"


def test_the_active_profile_is_reapplied_at_boot():
    models.save({"name": "Crucible Local", "base_url": "http://127.0.0.1:11434/v1",
                 "api_type": "openai", "model": "qwen-test"})
    models.activate("Crucible Local")
    os.environ.pop("PRIMNOX_MODEL", None)

    assert models.apply_active() == "Crucible Local"
    assert os.environ["PRIMNOX_MODEL"] == "qwen-test"


def test_switching_model_keeps_the_provider_and_its_key():
    """The common case: Opus to Sonnet. Nothing about the endpoint or the
    credential should have to be re-entered, and the change is live at once."""
    models.save({"name": "Crucible Cloud", "base_url": "https://example.test",
                 "api_type": "anthropic", "model": "m1",
                 "models": ["m1", "m2"], "api_key": PROBE})
    models.activate("Crucible Cloud")
    assert os.environ["PRIMNOX_MODEL"] == "m1"

    models.use_model("Crucible Cloud", "m2")
    assert os.environ["PRIMNOX_MODEL"] == "m2"
    assert os.environ["PRIMNOX_BASE_URL"] == "https://example.test"
    if models.keyring_available():
        assert os.environ["PRIMNOX_API_KEY"] == PROBE


def test_choosing_an_unlisted_model_adds_it():
    models.save({"name": "Temp", "base_url": "https://x.test",
                 "api_type": "openai", "model": "a", "models": ["a"]})
    models.use_model("Temp", "b")
    profile = next(p for p in models.profiles() if p["name"] == "Temp")
    assert profile["model"] == "b" and "b" in profile["models"]


def test_editing_a_profile_does_not_empty_its_model_list():
    """A typo fix in the URL must not silently clear the picker."""
    models.save({"name": "Temp", "base_url": "https://old.test",
                 "api_type": "openai", "model": "a", "models": ["a", "b"]})
    models.save({"name": "Temp", "base_url": "https://new.test"})
    profile = next(p for p in models.profiles() if p["name"] == "Temp")
    assert profile["models"] == ["a", "b"]
    assert profile["base_url"] == "https://new.test"


def test_discovery_on_an_unreachable_endpoint_keeps_what_was_saved():
    """Discovery is a convenience. A provider that is down, unauthenticated or
    simply has no /models must not empty the picker."""
    models.save({"name": "Temp", "base_url": "http://127.0.0.1:1/v1",
                 "api_type": "openai", "model": "a", "models": ["a", "b"]})
    assert models.discover("Temp") == ["a", "b"]


def test_ollama_status_answers_either_way():
    """Reports running/not without raising, so the panel can always render."""
    status = models.ollama_status()
    assert set(status) >= {"running", "host", "models"}
    assert isinstance(status["running"], bool)


def test_the_gateway_and_a_local_engine_are_seeded():
    """Two entries, answering different questions: reach any hosted model, and
    reach no network at all. A first run should manage both without config."""
    seeded = {p["name"] for p in models.profiles()}
    assert {"OmniRoute", "Ollama (local)"} <= seeded


def test_the_shipped_catalogue_stays_small():
    """It briefly held 346 rows ported from OmniRoute. Pointing at OmniRoute
    instead is the whole pivot; a catalogue creeping back means we started
    impersonating it again."""
    assert len(models.catalogue()) < 10


def test_entries_needing_a_server_or_a_key_are_not_seeded():
    """A seeded row that cannot answer is a row that looks broken."""
    seeded = {p["name"] for p in models.profiles()}
    assert "LM Studio (local)" not in seeded
    assert "Direct endpoint" not in seeded


def test_a_localhost_gateway_would_not_be_classified_as_on_device():
    """No catalogue entry is a gateway today, but the trust rule that makes one
    safe to add is what stops the Privacy Mirror being skipped for a provider
    that listens locally and forwards to the cloud."""
    from primnox2.models import gateway

    assert gateway.on_device_for("gateway", "http://127.0.0.1:20128/v1") is False
    assert gateway.requires_key_for("gateway", "http://127.0.0.1:20128/v1") is False


def test_a_profile_needs_a_name():
    with pytest.raises(ValueError):
        models.save({"name": "  ", "model": "m"})


def test_saving_the_same_name_updates_rather_than_duplicates():
    models.save({"name": "Temp", "base_url": "https://a.test", "model": "m1"})
    models.save({"name": "Temp", "base_url": "https://b.test", "model": "m2"})
    rows = [p for p in models.profiles() if p["name"] == "Temp"]
    assert len(rows) == 1 and rows[0]["model"] == "m2"


# ── HTTP ─────────────────────────────────────────────────────────────────────
def test_profiles_round_trip_over_http(client):
    created = client.post("/models", json={
        "name": "Temp", "base_url": "https://http.test",
        "api_type": "openai", "model": "http-model", "activate": True})
    assert created.status_code == 200
    body = created.json()
    assert body["active"] == "Temp"
    assert PROBE not in json.dumps(body)

    assert client.delete("/models/Temp").status_code == 200
    assert client.delete("/models/Temp").status_code == 404


def test_activating_an_unknown_profile_is_404(client):
    assert client.post("/models/nope/activate").status_code == 404


# ── discovery, against the two things that silently broke it ─────────────────
def test_discovery_asks_the_versioned_path_when_the_base_has_no_version():
    """Catalogue base URLs come in two shapes: OpenAI-style carries `/v1`,
    Anthropic-style does not. Appending `/models` to the second asks a URL the
    provider does not serve — measured as HTTP 305 against a real proxy whose
    `/v1/models` answered 200 — and the picker kept a one-entry stale list."""
    asked: list[str] = []

    def fake_fetch(url, headers=None):
        asked.append(url)
        if url.endswith("/v1/models"):
            return {"data": [{"id": "claude-opus-5"}, {"id": "claude-sonnet-5"}]}
        return None

    models.save({"name": "Temp", "base_url": "https://proxy.example",
                 "api_type": "anthropic", "model": "old", "models": ["old"]})
    original, models._fetch = models._fetch, fake_fetch
    try:
        found = models.discover("Temp")
    finally:
        models._fetch = original

    assert "https://proxy.example/v1/models" in asked
    assert found == ["claude-opus-5", "claude-sonnet-5"]


def test_discovery_does_not_double_the_version_segment():
    """A base URL that already carries `/v1` must not be asked for
    `/v1/v1/models`."""
    asked: list[str] = []

    def fake_fetch(url, headers=None):
        asked.append(url)
        return {"data": [{"id": "gpt-x"}]}

    models.save({"name": "Temp", "base_url": "https://api.example/v1",
                 "api_type": "openai", "model": "old", "models": ["old"]})
    original, models._fetch = models._fetch, fake_fetch
    try:
        models.discover("Temp")
    finally:
        models._fetch = original

    assert asked == ["https://api.example/v1/models"]


def test_discovery_sends_a_browser_user_agent():
    """Cloudflare's browser-integrity check answers Python's default urllib
    User-Agent with 403, including on a bare GET of the model list. The gateway
    already sends one; this path did not, so discovery through a fronted proxy
    failed every time — and silently, because the failure is swallowed."""
    import urllib.request

    from primnox2.models.gateway import USER_AGENT

    seen: dict = {}

    def fake_urlopen(req, timeout=None):
        seen["ua"] = req.get_header("User-agent")
        raise OSError("stop here — the header is what is under test")

    original, urllib.request.urlopen = urllib.request.urlopen, fake_urlopen
    try:
        models._fetch("https://proxy.example/v1/models", {"x-api-key": "k"})
    finally:
        urllib.request.urlopen = original

    assert seen["ua"] == USER_AGENT
