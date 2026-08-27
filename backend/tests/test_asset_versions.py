"""Asset lineage: version history and revert for generated files.

A workspace has had both since it shipped. An asset had neither, so
"regenerate that deck" replaced the old one with nothing pointing back. That
asymmetry — not the modal-versus-panel framing the research started with — was
the real gap between Canvas and AssetViewer.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from primnox2.app import app
from primnox2.assets import service as assets
from primnox2.assets import versions


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def make(name: str, body: bytes) -> str:
    return assets.ingest_bytes(body, name, source="tool_output")["id"]


def test_an_unversioned_asset_has_no_history():
    """Most files are uploaded once. Inventing a single-entry history would
    make every one of them look versioned."""
    asset = make("notes.txt", b"just once")
    assert versions.versions(asset) == []
    assert versions.head(asset) == asset


def test_superseding_starts_a_lineage_and_keeps_the_original():
    first = make("deck.pptx", b"v1 bytes")
    second = make("deck.pptx", b"v2 bytes")

    versions.supersede(first, second, summary="made it shorter")
    history = versions.versions(first)

    assert [v["version"] for v in history] == [1, 2]
    assert [v["asset_id"] for v in history] == [first, second]
    assert versions.head(first) == second
    # The point of the whole feature: the old file is still there.
    assert assets.get(first) is not None


def test_head_is_reachable_from_any_version():
    first = make("a.pptx", b"one")
    second = make("a.pptx", b"two")
    third = make("a.pptx", b"three")
    versions.supersede(first, second)
    versions.supersede(second, third)

    for anchor in (first, second, third):
        assert versions.head(anchor) == third


def test_identical_regeneration_is_not_a_new_version():
    """Dedup means byte-identical output resolves to the same asset. Recording
    a version there would claim a change that did not happen."""
    first = make("same.txt", b"unchanged bytes")
    again = make("same.txt", b"unchanged bytes")
    assert again == first

    result = versions.supersede(first, again)
    assert result["unchanged"] is True
    assert versions.versions(first) == []


def test_revert_appends_rather_than_deleting():
    """Undoing an undo is just another revert, so the versions after the
    restored one have to survive it."""
    first = make("r.pptx", b"original")
    second = make("r.pptx", b"replacement")
    versions.supersede(first, second, summary="regenerated")

    result = versions.revert(first, 1)
    assert result["asset_id"] == first
    assert result["version"] == 3

    history = versions.versions(first)
    assert [v["version"] for v in history] == [1, 2, 3]
    assert history[2]["summary"] == "reverted to v1"
    assert versions.head(first) == first


def test_revert_to_a_missing_version_is_an_error():
    first = make("m.pptx", b"one")
    second = make("m.pptx", b"two")
    versions.supersede(first, second)
    with pytest.raises(KeyError):
        versions.revert(first, 99)


def test_revert_without_history_is_an_error():
    asset = make("lonely.txt", b"never regenerated")
    with pytest.raises(KeyError):
        versions.revert(asset, 1)


def test_superseding_an_unknown_asset_raises():
    real = make("real.txt", b"real")
    with pytest.raises(KeyError):
        versions.supersede("asset_nope", real)


def test_retention_defaults_to_keep():
    """A user who has never opened Settings can still undo a regeneration."""
    assert versions.retention() == "keep"


def test_superseded_assets_excludes_the_head():
    first = make("s.pptx", b"first")
    second = make("s.pptx", b"second")
    info = versions.supersede(first, second)
    stale = versions.superseded_assets(info["lineage_id"])
    assert stale == [first]


# ── HTTP ─────────────────────────────────────────────────────────────────────

def test_versions_route_reports_retention(client):
    first = make("http.pptx", b"http one")
    second = make("http.pptx", b"http two")
    versions.supersede(first, second, summary="regenerated")

    body = client.get(f"/assets/{first}/versions").json()
    assert [v["version"] for v in body["versions"]] == [1, 2]
    assert body["head"] == second
    # Reported so the client can decide whether Revert is honest to offer.
    assert body["retention"] in {"keep", "history"}


def test_versions_route_404s_on_unknown_asset(client):
    assert client.get("/assets/asset_nope/versions").status_code == 404


def test_revert_route(client):
    first = make("hr.pptx", b"hr one")
    second = make("hr.pptx", b"hr two")
    versions.supersede(first, second)

    r = client.post(f"/assets/{first}/revert", json={"version": 1})
    assert r.status_code == 200
    assert r.json()["asset_id"] == first


def test_revert_route_rejects_a_non_integer_version(client):
    first = make("bad.pptx", b"bad one")
    second = make("bad.pptx", b"bad two")
    versions.supersede(first, second)
    assert client.post(f"/assets/{first}/revert",
                       json={"version": "latest"}).status_code == 400
