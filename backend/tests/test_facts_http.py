"""Facts over HTTP, with the provenance the UI has never shown.

v2/world_model.py records where every belief came from, how it was arrived at,
how confident it is and what it replaced. None of that reached the interface,
so a fact the assistant stated looked identical whether the user said it, a
file proved it, or a model guessed it. These pin the read path and, more
importantly, that provenance survives the trip.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from primnox2.app import app
from v2 import world_model
from v2.world_model import Provenance


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_provenance_reaches_the_client(client):
    world_model.record_fact(
        "the package manager is npm",
        project="proto-http", slot="package_manager",
        prov=Provenance(source="file", source_ref="package-lock.json",
                        origin="observed", confidence=0.9),
    )

    facts = client.get("/facts", params={"project": "proto-http"}).json()["facts"]
    match = next(f for f in facts if "npm" in f["text"])

    # Without these a citation block has nothing to render, and the claim goes
    # back to looking like it came from nowhere.
    assert match["source"] == "file"
    assert match["source_ref"] == "package-lock.json"
    assert match["origin"] == "observed"
    assert match["confidence"] == pytest.approx(0.9)
    assert "observed_at" in match


def test_superseded_facts_are_excluded(client):
    """current_facts answers "what is true", not "what was ever believed"."""
    world_model.record_fact("the port is 3000", project="proto-super",
                            slot="port", prov=Provenance(source="user"))
    world_model.record_fact("the port is 5273", project="proto-super",
                            slot="port", prov=Provenance(source="user"))

    texts = [f["text"] for f in
             client.get("/facts", params={"project": "proto-super"}).json()["facts"]]
    assert "the port is 5273" in texts
    assert "the port is 3000" not in texts


def test_secret_facts_stay_opt_in(client):
    """A privacy-first product must not widen the default because the caller is
    now HTTP rather than a Python import.

    Note what the flag actually gates. SENSITIVITY_LEVELS runs public → normal
    → sensitive → secret, and current_facts() excludes only 'secret' when
    include_sensitive is False. So the parameter is named for the level below
    the one it filters. That is the module's established semantic — v2/context.py
    and every other caller depend on it — so the route passes it through
    unchanged rather than quietly redefining it at the HTTP boundary. The
    boundary is pinned here so a future change to it fails loudly.
    """
    world_model.record_fact("the recovery phrase is hunter2",
                            project="proto-secret", sensitivity="secret",
                            prov=Provenance(source="user"))

    hidden = client.get("/facts", params={"project": "proto-secret"}).json()["facts"]
    assert all("hunter2" not in f["text"] for f in hidden)

    shown = client.get("/facts", params={"project": "proto-secret",
                                         "include_sensitive": "true"}).json()["facts"]
    assert any("hunter2" in f["text"] for f in shown)


def test_sensitive_is_not_what_the_flag_hides(client):
    """The level literally called 'sensitive' is returned by default. Pinned so
    that anyone reading the flag name and assuming otherwise is corrected by a
    test rather than by a leak."""
    world_model.record_fact("the office is on the third floor",
                            project="proto-mid", sensitivity="sensitive",
                            prov=Provenance(source="user"))

    facts = client.get("/facts", params={"project": "proto-mid"}).json()["facts"]
    assert any("third floor" in f["text"] for f in facts)


def test_search_is_not_read_as_a_fact_id(client):
    """Route order matters: /facts/search must not match /facts/{fact_id}."""
    world_model.record_fact("the deploy target is fly.io", project="proto-search",
                            prov=Provenance(source="user"))
    r = client.get("/facts/search", params={"q": "deploy", "project": "proto-search"})
    assert r.status_code == 200
    assert any("fly.io" in f["text"] for f in r.json()["facts"])


def test_search_requires_a_query(client):
    assert client.get("/facts/search", params={"q": "  "}).status_code == 400


def test_get_one_fact(client):
    record = world_model.record_fact("the linter is ruff", project="proto-one",
                                     prov=Provenance(source="tool", origin="observed"))
    body = client.get(f"/facts/{record['id']}").json()
    assert body["text"] == "the linter is ruff"
    assert body["source"] == "tool"
    assert body["origin"] == "observed"


def test_unknown_fact_is_404(client):
    assert client.get("/facts/fact_nope").status_code == 404


def test_limit_is_clamped(client):
    """An unbounded limit over HTTP is a way to ask the process to read the
    whole store into memory."""
    r = client.get("/facts", params={"limit": 100000})
    assert r.status_code == 200
    assert len(r.json()["facts"]) <= 200
