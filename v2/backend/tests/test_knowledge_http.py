"""The knowledge-graph HTTP surface, including the viewer.

The viewer test renders a real scope through Graphify's exporter rather than
asserting the route returns 200 on an empty graph — an exporter that silently
produces a blank page would pass the shallow version.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from primnox2.app import app
from primnox2.knowledge import importer
from primnox2.storage import db

REPO = pathlib.Path(__file__).resolve().parents[1] / "primnox2"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def indexed(fresh_db):
    """A small real scope: one package, extracted by the real extractor."""
    if not importer.available():
        pytest.skip("graphify not installed")
    importer.import_tree(REPO / "storage", scope="test-scope")
    yield "test-scope"


def test_scopes_lists_what_is_indexed(client, indexed):
    scopes = {s["scope"]: s for s in client.get("/knowledge/scopes").json()["scopes"]}
    assert indexed in scopes
    assert scopes[indexed]["nodes"] > 0


def test_graph_json_has_no_dangling_edges(client, indexed):
    body = client.get("/knowledge/graph", params={"scope": indexed}).json()
    assert body["nodes"] and body["edges"]
    ids = {n["id"] for n in body["nodes"]}
    for e in body["edges"]:
        assert e["source_id"] in ids and e["target_id"] in ids


def test_the_viewer_renders_a_real_page(client, indexed):
    r = client.get("/knowledge/view", params={"scope": indexed})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    html = r.text
    assert len(html) > 20_000, "viewer returned a suspiciously small page"
    # Self-contained: the app serves no static assets for it, so a page that
    # reached for a CDN would render blank for the user and pass a length check.
    assert "<script" in html and "http://cdn" not in html
    assert "</html>" in html


def test_the_viewer_is_honest_about_an_unknown_scope(client):
    r = client.get("/knowledge/view", params={"scope": "never-indexed"})
    assert r.status_code == 404, "an empty graph rendered as a blank page instead of 404"


def test_indexing_a_missing_path_is_404(client):
    r = client.post("/knowledge/index", json={"target": "C:/definitely/not/here"})
    assert r.status_code == 404


def test_indexing_requires_a_target(client):
    assert client.post("/knowledge/index", json={}).status_code == 400


def test_indexing_queues_a_job_rather_than_blocking(client, tmp_path):
    """A large repository takes minutes; the request must return a job id."""
    if not importer.available():
        pytest.skip("graphify not installed")
    (tmp_path / "sample.py").write_text("def hello():\n    return 1\n", encoding="utf-8")

    r = client.post("/knowledge/index",
                    json={"target": str(tmp_path), "scope": "queued-scope"})
    assert r.status_code == 200
    assert r.json()["job_id"].startswith("job_")

    row = db.connect().execute(
        "SELECT kind, status FROM jobs WHERE id=?", (r.json()["job_id"],)).fetchone()
    assert row["kind"] == "memory.graph_build"
