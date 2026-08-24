"""The catalogue, connection testing, and the portability surface.

Everything here is about the part of Primnox a user touches BEFORE a
conversation: finding a provider among 347, checking a key works without
spending a turn to find out, and moving a set-up between machines.

The routing tests live in test_model_failover.py; these never send a turn.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from primnox2.models import failures, health                    # noqa: E402
from primnox2.settings import connections, models                # noqa: E402


# ── The gateway is the primary provider ──────────────────────────────────────
def test_the_shipped_catalogue_is_the_decision_primnox_owns():
    """It briefly held 346 entries ported from OmniRoute. Only 103 of them
    carried a callable endpoint, and the rest would have needed hand-tracking
    someone else's release cycle to stay a worse copy. What is left is the
    choice Primnox still makes: gateway, or entirely on this machine."""
    names = {e["name"] for e in models.catalogue()}
    assert "OmniRoute" in names and "Ollama (local)" in names
    assert len(models.catalogue()) < 10, "the ported catalogue is back"


def test_omniroute_is_marked_primary_and_is_the_only_one():
    primary = [e for e in models.catalogue() if e.get("primary")]
    assert len(primary) == 1 and primary[0]["name"] == "OmniRoute"
    assert models.primary_name() == "OmniRoute"


def test_the_gateway_is_seeded_and_active_on_a_first_run():
    """A fresh install used to answer every message with "point Settings at a
    real provider" while a perfectly good route sat configured beside it."""
    seeded = {row["name"] for row in models._seed()}
    assert {"OmniRoute", "Ollama (local)"} <= seeded


def test_the_gateway_needs_no_key_here_because_its_keys_live_in_it():
    from primnox2.models import gateway

    entry = models.primary_entry()
    assert entry["needs_key"] is False
    assert gateway.requires_key_for(entry["kind"], entry["base_url"]) is False


def test_the_gateway_is_still_off_device_however_local_its_address():
    """The single most consequential line in the pivot: every hosted turn now
    goes through 127.0.0.1:20128, so if that ever reads as on-device the
    Privacy Mirror stops applying to all of it at once."""
    from primnox2.models import gateway

    entry = models.primary_entry()
    assert entry["kind"] == "gateway"
    assert gateway.on_device_for(entry["kind"], entry["base_url"]) is False


def test_an_unreachable_gateway_reports_how_to_install_it(monkeypatch):
    """Not installed is the expected state of a fresh machine, so the probe
    answers with a command rather than an error."""
    monkeypatch.setattr(models, "_fetch", lambda *a, **k: None)
    status = models.omniroute_status()
    assert status["running"] is False and status["configured"] is False
    assert "npm install -g omniroute" in status["install"]


def test_running_with_nothing_behind_it_is_not_reported_as_healthy(monkeypatch):
    """Reachable with zero models is indistinguishable from healthy by status
    code, and a turn sent into it fails in a way that reads as Primnox's
    fault."""
    monkeypatch.setattr(models, "_fetch", lambda *a, **k: {"data": []})
    status = models.omniroute_status()
    assert status["running"] is True and status["configured"] is False


def test_the_routing_channels_are_offered_rather_than_the_whole_model_list(monkeypatch):
    monkeypatch.setattr(models, "_fetch", lambda *a, **k: {"data": [
        {"id": "auto"}, {"id": "auto/coding"}, {"id": "gpt-5"}, {"id": "claude-sonnet-5"},
    ]})
    status = models.omniroute_status()
    assert status["channels"] == ["auto", "auto/coding"]
    assert status["model_count"] == 4


@pytest.fixture(autouse=True)
def clean():
    health.reset()
    yield
    health.reset()
    for name in ("ImportTest", "ImportTest2", "NoteTarget", "PinTarget"):
        models.delete(name)


# ── Connection testing ───────────────────────────────────────────────────────
class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_a_reachable_endpoint_reports_its_models_and_latency(monkeypatch):
    monkeypatch.setattr(connections.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(b'{"data":[{"id":"m1"},{"id":"m2"}]}'))
    result = connections.probe("https://api.example.com/v1", "k")
    assert result["ok"] and result["models"] == ["m1", "m2"]
    assert result["latency_ms"] >= 0


def test_a_rejected_key_is_named_by_the_same_classifier_the_chain_uses(monkeypatch):
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.HTTPError("u", 401, "invalid api key", {}, None)

    monkeypatch.setattr(connections.urllib.request, "urlopen", boom)
    result = connections.probe("https://api.example.com/v1", "bad")
    assert not result["ok"]
    assert result["reason"] == failures.AUTHENTICATION_ERROR


def test_html_with_a_200_is_called_out_rather_than_reported_as_generic(monkeypatch):
    """A Cloudflare challenge page answers 200 with HTML. "Not JSON" tells the
    user to look at the URL; "request failed" sends them to check their key."""
    monkeypatch.setattr(connections.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(b"<!doctype html><title>Just a moment</title>"))
    result = connections.probe("https://api.example.com/v1", "k")
    assert not result["ok"] and result["reason"] == "not_json"


def test_an_empty_endpoint_is_refused_without_a_network_call(monkeypatch):
    def explode(*a, **k):
        raise AssertionError("should not have made a request")

    monkeypatch.setattr(connections.urllib.request, "urlopen", explode)
    assert connections.probe("")["reason"] == "no_endpoint"


def test_a_versionless_base_tries_the_v1_path_first(monkeypatch):
    tried = []

    def record(req, *a, **k):
        tried.append(req.full_url)
        raise ConnectionError("nope")

    monkeypatch.setattr(connections.urllib.request, "urlopen", record)
    connections.probe("https://api.example.com", "k")
    assert tried[0].endswith("/v1/models")


def test_a_successful_probe_closes_a_breaker_that_was_benching_the_provider(monkeypatch):
    """Someone pasted a corrected key. Making them wait out a cooldown that is
    measuring a problem they just fixed is the wrong answer."""
    profile = models.save({"name": "PinTarget", "base_url": "https://api.example.com/v1",
                           "model": "m1", "kind": "cloud"})
    key = f"{profile['base_url']}|m1"
    health.record_failure(key, failures.classify("PinTarget", "m1", status=401,
                                                 message="invalid api key"))
    assert health.circuit(key).state == health.OPEN

    monkeypatch.setattr(connections.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(b'{"data":[{"id":"m1"}]}'))
    result = connections.test_profile("PinTarget")
    assert result["ok"]
    assert health.circuit(key).state == health.CLOSED


def test_testing_an_unsaved_candidate_records_no_health(monkeypatch):
    """A typo in an add form must not leave a circuit behind it for a provider
    the user never adopted."""
    monkeypatch.setattr(connections.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(b'{"data":[]}'))
    before = len(health.snapshot())
    connections.test_candidate("https://api.nowhere.example/v1", "k")
    assert len(health.snapshot()) == before


def test_testing_an_unknown_profile_is_a_key_error():
    with pytest.raises(KeyError):
        connections.test_profile("no such profile")


# ── Import and export ────────────────────────────────────────────────────────
def test_an_export_never_contains_a_key():
    """An export is a file that gets mailed, committed by accident, or attached
    to a bug report. The only version safe to treat carelessly is one that never
    held a credential."""
    models.save({"name": "ImportTest", "base_url": "https://api.example.com/v1",
                 "model": "m1", "api_key": "sk-secret-value"})
    dumped = repr(models.export_profiles())
    assert "sk-secret-value" not in dumped
    assert not any("api_key" in row for row in models.export_profiles()["profiles"])


def test_import_adds_what_is_new_and_updates_what_exists():
    models.save({"name": "ImportTest", "base_url": "https://a.test/v1", "model": "m1"})
    result = models.import_profiles({"profiles": [
        {"name": "ImportTest", "base_url": "https://b.test/v1", "model": "m2"},
        {"name": "ImportTest2", "base_url": "https://c.test/v1", "model": "m3"},
    ]})
    assert result["updated"] == ["ImportTest"] and result["added"] == ["ImportTest2"]
    assert next(p for p in models.profiles()
                if p["name"] == "ImportTest")["base_url"] == "https://b.test/v1"


def test_import_never_removes_an_existing_profile():
    """The worst a bad file can do is add rows the user then deletes."""
    models.save({"name": "ImportTest", "base_url": "https://a.test/v1", "model": "m1"})
    before = {p["name"] for p in models.profiles()}
    models.import_profiles({"profiles": [{"name": "ImportTest2",
                                          "base_url": "https://c.test/v1", "model": "m"}]})
    assert before <= {p["name"] for p in models.profiles()}


def test_import_skips_rows_it_cannot_use_instead_of_failing_the_file():
    result = models.import_profiles({"profiles": [
        {"name": "", "base_url": "https://x.test"},
        {"name": "NoEndpoint"},
        "not an object",
        {"name": "ImportTest2", "base_url": "https://c.test/v1", "model": "m"},
    ]})
    assert result["added"] == ["ImportTest2"]
    assert len(result["skipped"]) == 3


def test_a_file_that_is_not_an_export_says_so():
    with pytest.raises(ValueError, match="Primnox export"):
        models.import_profiles({"something": "else"})


def test_export_round_trips_through_import():
    models.save({"name": "ImportTest", "base_url": "https://a.test/v1", "model": "m1"})
    models.set_note("ImportTest", "round trip")
    dumped = models.export_profiles()
    models.delete("ImportTest")
    models.import_profiles(dumped)
    assert any(p["name"] == "ImportTest" for p in models.profiles())
    assert models.notes().get("ImportTest") == "round trip"


# ── Bulk operations ──────────────────────────────────────────────────────────
def test_discover_all_covers_every_profile_and_survives_one_failing(monkeypatch):
    """Sequential on purpose: these are the user's own rate-limited accounts,
    and a dozen simultaneous requests is a good way to earn a 429 that says
    nothing about whether the key works."""
    models.save({"name": "ImportTest", "base_url": "https://a.test/v1", "model": "m1"})

    def sometimes(name):
        if name == "ImportTest":
            raise RuntimeError("provider exploded")
        return ["m-found"]

    monkeypatch.setattr(models, "discover", sometimes)
    found = models.discover_all()
    assert set(found) == {p["name"] for p in models.profiles()}
    assert found["ImportTest"] == [], "a failing provider should not fail the batch"


def test_test_all_returns_a_row_per_profile(monkeypatch):
    monkeypatch.setattr(connections.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(b'{"data":[{"id":"m1"}]}'))
    results = connections.test_all()
    assert {r["profile"] for r in results} == {p["name"] for p in models.profiles()}


# ── The HTTP surface ─────────────────────────────────────────────────────────
def test_the_http_surface_answers(monkeypatch):
    """The UI reaches all of this over HTTP, so the wiring is worth one pass —
    a unit-tested function behind a mistyped route is still a broken feature."""
    from fastapi.testclient import TestClient

    from primnox2.app import app

    with TestClient(app) as c:
        assert c.get("/models").json()["primary"] == "OmniRoute"
        assert "install" in c.get("/models/omniroute").json()
        assert c.get("/models/export").json()["primnox_profiles"] == 1
        assert c.get("/guides").json()["guides"]
        assert c.get("/guides/routing-and-failover").status_code == 200
        assert c.get("/guides/nope").status_code == 404
        assert c.post("/models/import", json={"nope": 1}).status_code == 400
        # The browse-and-adopt routes went with the catalogue they served.
        # 405 rather than 404: `/models/{name}` still matches that path for
        # DELETE, so the path exists and the method does not. Either way it no
        # longer serves a catalogue, which is what this asserts.
        assert c.get("/models/catalogue").status_code in (404, 405)
        assert c.post("/models/catalogue/omniroute", json={}).status_code == 404



