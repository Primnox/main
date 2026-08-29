"""The facts graph — what Primnox knows about the USER.

The test that matters most is the negative one. This graph existed as a code
index first, so the app opened on `_startup()` calling `_warm_sandbox()` —
Primnox's own plumbing presented as the user's knowledge. These assert the
separation holds.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from primnox2.app import app
from primnox2.chat import turns
from primnox2.knowledge import facts, importer, live
from primnox2.memory import service as memory
from primnox2.storage import db


@pytest.fixture
def clean(fresh_db):
    # Assets and conversations too: this suite shares one database, and an
    # "empty system" test that still sees a document from three tests ago is
    # measuring the suite rather than the code.
    def _wipe():
        with db.tx() as c:
            c.execute("DELETE FROM memories")
            c.execute("DELETE FROM assets")
            c.execute("DELETE FROM conversations")
        live.drop_all()

    _wipe()
    yield
    _wipe()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _seed() -> str:
    cid = turns.create_conversation("Payments design")["id"]
    # Completed: the graph learns from settled turns only, so a seed that only
    # creates one produces an empty graph.
    tid = turns.create_turn(cid, "We'll use `PaymentGateway` with WAL mode.")["turn_id"]
    turns.complete(tid, "Sounds good.")
    live.save(cid)
    memory.remember("I prefer concise answers.", conversation_id=cid)
    return cid


# ── what it contains ─────────────────────────────────────────────────────────
def test_saved_facts_appear(clean):
    _seed()
    kinds = {n["file_type"] for n in facts.build()["nodes"]}
    assert "fact" in kinds
    assert "conversation" in kinds


def test_decisions_from_chats_appear(clean):
    _seed()
    labels = [n["label"] for n in facts.build()["nodes"]
              if n["file_type"] == "decision"]
    assert any("WAL" in l for l in labels)


def test_a_memory_is_linked_to_the_chat_it_came_from(clean):
    _seed()
    graph = facts.build()
    assert any(e["relation"] == "remembered_in" for e in graph["edges"])


def test_an_entity_in_one_chat_is_noise_and_two_is_knowledge(clean):
    """A thing mentioned once is a passing remark. The threshold is what stops
    the canvas filling with every capitalised word the user ever typed."""
    one = turns.create_conversation("Only once")["id"]
    t1 = turns.create_turn(one, "Something about `OneOffThing` here.")["turn_id"]
    turns.complete(t1, "Noted.")
    live.save(one)
    assert not any(n["label"] == "OneOffThing" for n in facts.build()["nodes"])

    two = turns.create_conversation("Again")["id"]
    t2 = turns.create_turn(two, "More about `OneOffThing`.")["turn_id"]
    turns.complete(t2, "Noted again.")
    live.save(two)
    assert any(n["label"] == "OneOffThing" for n in facts.build()["nodes"])


def test_documents_appear_with_the_chat_they_were_shared_in(clean):
    from primnox2.assets import service as assets

    cid = turns.create_conversation("With a file")["id"]
    tid = turns.create_turn(cid, "here is a doc")["turn_id"]
    asset = assets.ingest_bytes(b"some contents", "brief.txt", turn_id=tid)
    with db.tx() as c:
        c.execute("UPDATE assets SET status='ready' WHERE id=?", (asset["id"],))

    graph = facts.build()
    assert any(n["label"] == "brief.txt" for n in graph["nodes"])
    assert any(e["relation"] == "shared_in" for e in graph["edges"])


# ── what it must NOT contain ─────────────────────────────────────────────────
@pytest.mark.skipif(not importer.available(), reason="graphify not installed")
def test_an_indexed_codebase_never_leaks_into_the_facts_graph(clean):
    """Regression for the defect this module exists to fix: the app opened on a
    graph of its own source, which is a developer's view of Primnox rather than
    anything about the user."""
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[1] / "primnox2" / "storage"
    importer.import_tree(repo, scope="some-codebase")
    _seed()

    labels = {n["label"] for n in facts.build()["nodes"]}
    assert not any(l.endswith(".py") for l in labels), \
        f"source files reached the facts graph: {sorted(labels)[:5]}"
    assert not any(l.endswith("()") for l in labels), \
        "functions reached the facts graph"


def test_an_empty_system_renders_nothing_rather_than_an_empty_canvas(clean):
    """A blank graph looks broken. 404 lets the UI say what would fill it."""
    assert facts.render_html() is None


def test_a_chat_with_nothing_established_is_not_a_node(clean):
    turns.create_conversation("Just chatting")
    assert facts.build()["nodes"] == []


# ── surfaces ─────────────────────────────────────────────────────────────────
def test_facts_is_listed_first(client, clean):
    _seed()
    scopes = client.get("/knowledge/scopes").json()["scopes"]
    assert scopes[0]["scope"] == "facts"
    assert scopes[0]["kind"] == "facts"
    assert "knows about you" in scopes[0]["label"]


def test_an_indexed_corpus_is_labelled_as_one(client, clean):
    """So "2,501 nodes" can never read as knowledge about the user."""
    if not importer.available():
        pytest.skip("graphify not installed")
    import pathlib
    importer.import_tree(
        pathlib.Path(__file__).resolve().parents[1] / "primnox2" / "storage",
        scope="some-codebase")

    scopes = {s["scope"]: s for s in client.get("/knowledge/scopes").json()["scopes"]}
    assert scopes["some-codebase"]["kind"] == "corpus"
    assert scopes["some-codebase"]["label"].startswith("Indexed:")


def test_the_facts_view_renders(client, clean):
    _seed()
    r = client.get("/knowledge/view", params={"scope": "facts"})
    assert r.status_code == 200
    assert "<script" in r.text


def test_the_facts_view_explains_an_empty_system(client, clean):
    r = client.get("/knowledge/view", params={"scope": "facts"})
    assert r.status_code == 404
    assert "nothing saved yet" in r.json()["detail"]


# ── memories that never came from a chat ─────────────────────────────────────
def test_a_memory_without_a_chat_is_filed_under_its_category(clean):
    """A fact typed into the Memory panel, or loaded from a corpus, has no
    conversation to hang from. Drawn unconnected, a hundred of them bury the
    part of the canvas that has structure."""
    memory.import_many([
        {"text": "Devan takes the tram since moving.", "category": "personal"},
        {"text": "Devan owns the Atlas rollout.", "category": "work"},
    ])
    graph = facts.build()
    filed = [e for e in graph["edges"] if e["relation"] == "filed_under"]
    hubs = {n["label"] for n in graph["nodes"] if n["file_type"] == "category"}

    assert len(filed) == 2
    assert hubs == {"personal", "work"}


def test_no_fact_is_left_unconnected(clean):
    """The property that matters, stated directly: every fact reaches something.
    An unreachable node is indexing work that can never pay off."""
    _seed()
    memory.import_many([{"text": f"Devan met person {i}.", "category": "work"}
                        for i in range(10)])
    graph = facts.build()
    touched = ({e["source"] for e in graph["edges"]}
               | {e["target"] for e in graph["edges"]})
    orphans = [n["id"] for n in graph["nodes"] if n["id"] not in touched]
    assert orphans == []


def test_a_memory_from_a_chat_still_points_at_the_chat(clean):
    """The category hub is a fallback, not a replacement: where a real source
    exists it stays the relationship shown."""
    _seed()
    graph = facts.build()
    relations = {e["relation"] for e in graph["edges"]}
    assert "remembered_in" in relations
    assert "filed_under" not in relations
