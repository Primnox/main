"""The HTTP layer.

Everything else in this suite drives the services in-process, which leaves
app.py's 28 routes — the only surface the frontend actually talks to — entirely
unexercised. That gap is where this project's bugs have historically lived: a
Retry button wired to nothing, a folder API the UI could not reach. A service
that works and a route that exposes it are two different claims.

These use FastAPI's TestClient, which runs the real app object including its
startup handler. conftest pins PRIMNOX2_HOME to a temp directory before any
import so that handler cannot point the runtime at a real database.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from primnox2.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ── health and discovery ─────────────────────────────────────────────────────
def test_health_reports_the_runtime(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["crs"] == "CRS/1.0"
    # The active model is part of the payload because "which model am I talking
    # to" is the first question every support conversation starts with.
    assert "model" in body and body["model"].get("model")


def test_tools_are_advertised_over_http(client):
    r = client.get("/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert {"run_python", "graph_query", "recall_conversation"} <= names


# ── conversations ────────────────────────────────────────────────────────────
def test_conversation_crud_round_trips(client):
    created = client.post("/conversations", json={"title": "Over HTTP"})
    assert created.status_code == 200
    cid = created.json()["id"]

    assert cid in {c["id"] for c in client.get("/conversations").json()["conversations"]}

    renamed = client.patch(f"/conversations/{cid}", json={"title": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed"

    assert client.delete(f"/conversations/{cid}").status_code == 200
    assert cid not in {c["id"] for c in client.get("/conversations").json()["conversations"]}


def test_deleting_an_unknown_conversation_is_404_not_500(client):
    """A missing row is a client error. Returning 500 makes every real fault
    indistinguishable from a stale tab."""
    r = client.delete("/conversations/conv_does_not_exist")
    assert r.status_code == 404, f"got {r.status_code}: {r.text[:200]}"


def test_pinning_over_http(client):
    cid = client.post("/conversations", json={"title": "Pin me"}).json()["id"]
    assert client.patch(f"/conversations/{cid}", json={"pinned": True}).status_code == 200
    listed = {c["id"]: c for c in client.get("/conversations").json()["conversations"]}
    assert listed[cid].get("pinned_at"), "pin did not survive the round trip"
    client.delete(f"/conversations/{cid}")


# ── folders — the API the UI could not reach ─────────────────────────────────
def test_folder_crud_round_trips(client):
    created = client.post("/folders", json={"name": "Reachable"})
    assert created.status_code == 200
    fid = created.json()["id"]

    assert fid in {f["id"] for f in client.get("/folders").json()["folders"]}

    renamed = client.patch(f"/folders/{fid}", json={"name": "Renamed Folder"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed Folder"

    assert client.delete(f"/folders/{fid}").status_code == 200
    assert fid not in {f["id"] for f in client.get("/folders").json()["folders"]}


def test_moving_a_conversation_into_a_folder_over_http(client):
    """The drag-and-drop path, at the layer the browser actually calls."""
    fid = client.post("/folders", json={"name": "Target"}).json()["id"]
    cid = client.post("/conversations", json={"title": "Filed"}).json()["id"]

    moved = client.patch(f"/conversations/{cid}", json={"folder_id": fid})
    assert moved.status_code == 200

    listed = {c["id"]: c for c in client.get("/conversations").json()["conversations"]}
    assert listed[cid]["folder_id"] == fid

    unfiled = client.patch(f"/conversations/{cid}", json={"folder_id": None})
    assert unfiled.status_code == 200
    listed = {c["id"]: c for c in client.get("/conversations").json()["conversations"]}
    assert listed[cid]["folder_id"] is None

    client.delete(f"/conversations/{cid}")
    client.delete(f"/folders/{fid}")


def test_deleting_a_folder_does_not_delete_its_conversations(client):
    """A folder is a label. Losing chats by tidying up would be unforgivable."""
    fid = client.post("/folders", json={"name": "Temporary"}).json()["id"]
    cid = client.post("/conversations", json={"title": "Survivor"}).json()["id"]
    client.patch(f"/conversations/{cid}", json={"folder_id": fid})

    client.delete(f"/folders/{fid}")

    listed = {c["id"]: c for c in client.get("/conversations").json()["conversations"]}
    assert cid in listed, "deleting a folder destroyed the conversations inside it"
    assert listed[cid]["folder_id"] is None
    client.delete(f"/conversations/{cid}")


# ── turns ────────────────────────────────────────────────────────────────────
def test_creating_a_turn_returns_a_turn_id(client):
    """CRS §4.1 — the response must name the work, or nothing can refer to it
    again and cancellation is unimplementable."""
    cid = client.post("/conversations", json={"title": "Turn source"}).json()["id"]
    r = client.post(f"/conversations/{cid}/turns", json={"text": "hello"})
    assert r.status_code == 200
    assert r.json()["turn_id"].startswith("turn_")
    client.delete(f"/conversations/{cid}")


def test_history_round_trips_the_user_message(client):
    cid = client.post("/conversations", json={"title": "History"}).json()["id"]
    client.post(f"/conversations/{cid}/turns", json={"text": "remember this"})

    history = client.get(f"/conversations/{cid}/history")
    assert history.status_code == 200
    assert "remember this" in history.text
    client.delete(f"/conversations/{cid}")


def test_retry_of_an_unknown_turn_is_not_a_500(client):
    r = client.post("/turns/turn_missing/retry")
    assert r.status_code in (404, 409), f"got {r.status_code}: {r.text[:200]}"


# ── assets ───────────────────────────────────────────────────────────────────
def test_uploading_and_reading_back_an_asset(client):
    payload = b"the quick brown fox jumps over the lazy dog\n" * 3
    up = client.post("/assets", files={"file": ("note.txt", io.BytesIO(payload), "text/plain")})
    assert up.status_code == 200, up.text[:300]
    asset_id = up.json()["id"]

    got = client.get(f"/assets/{asset_id}")
    assert got.status_code == 200
    assert got.json()["original_name"] == "note.txt"

    down = client.get(f"/assets/{asset_id}/download")
    assert down.status_code == 200
    assert down.content == payload, "download did not return the bytes uploaded"


def test_inline_download_strips_control_chars_from_a_hostile_filename(client):
    """original_name is whatever the uploaded file was called — fully
    attacker-controlled. The inline-download path builds its own
    Content-Disposition header by hand rather than going through Starlette's
    own (already-safe, percent-encoding) `filename=` parameter, so a name
    with an embedded CR/LF must not reach that header raw — a real uvicorn
    server rejects a raw CRLF in a header value outright (confirmed
    separately), which turned an odd filename into a crashed request rather
    than an XSS/response-splitting exploit, but it should not crash either."""
    evil_name = 'evil.pdf\r\nX-Injected: pwned\r\nSet-Cookie: hacked=1'
    up = client.post("/assets", files={"file": (evil_name, io.BytesIO(b"data"), "text/plain")})
    assert up.status_code == 200, up.text[:300]
    asset_id = up.json()["id"]

    down = client.get(f"/assets/{asset_id}/download", params={"inline": "true"})
    assert down.status_code == 200
    disposition = down.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    assert "X-Injected" not in down.headers
    assert "hacked" not in down.headers.get("set-cookie", "")


def test_identical_uploads_deduplicate(client):
    """Content addressing (§2.6): the same bytes are one asset."""
    payload = b"identical content for dedup"
    a = client.post("/assets", files={"file": ("a.txt", io.BytesIO(payload), "text/plain")})
    b = client.post("/assets", files={"file": ("b.txt", io.BytesIO(payload), "text/plain")})
    assert a.json()["id"] == b.json()["id"]


def test_unknown_asset_is_404(client):
    assert client.get("/assets/asset_nope").status_code == 404
