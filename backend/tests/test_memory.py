"""Permanent memory, and the retrieval the runtime performs on its own.

The retrieval tests matter more than the CRUD ones. `graph_query` existed as a
tool for a whole build without anything calling it, which meant the knowledge
graph was only ever consulted if the model happened to think of it — and the
local 7B does not. These assert the runtime does the looking.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from primnox2.app import app
from primnox2.chat import turns
from primnox2.context import service as context
from primnox2.knowledge import importer, live
from primnox2.memory import service as memory
from primnox2.storage import db

REPO = pathlib.Path(__file__).resolve().parents[1] / "primnox2"


@pytest.fixture
def clean_memory():
    with db.tx() as c:
        c.execute("DELETE FROM memories")
    yield
    with db.tx() as c:
        c.execute("DELETE FROM memories")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ── storing ──────────────────────────────────────────────────────────────────
def test_a_memory_round_trips(clean_memory):
    result = memory.remember("I prefer concise answers.")
    assert result["stored"] is True
    assert [m["text"] for m in memory.live()] == ["I prefer concise answers."]


def test_a_memory_written_in_a_chat_announces_itself(clean_memory, conversation, events):
    """§3.6 registers `memory.written`, and for a whole build nothing emitted
    it — a registered kind no subsystem sends is one the client can never
    render, which is the same silent gap `graph_query` had. The sequence is
    the part worth asserting: it proves the event reached the log in the
    write's own transaction (§4.2), not just a connected socket (§3.4).
    """
    memory.remember("They deploy on Tuesday mornings.", conversation_id=conversation)

    written = events.of_kind("memory.written")
    assert len(written) == 1
    assert written[0]["payload"]["text"] == "They deploy on Tuesday mornings."
    assert written[0]["conversation_id"] == conversation
    assert written[0]["sequence"] is not None


def test_a_suppressed_duplicate_announces_nothing(clean_memory, conversation, events):
    """Nothing was stored, so nothing is announced. The alternative is a client
    showing the same fact arriving twice."""
    memory.remember("They deploy on Tuesday mornings.", conversation_id=conversation)
    again = memory.remember("They deploy on Tuesday mornings", conversation_id=conversation)

    assert again["stored"] is False
    assert len(events.of_kind("memory.written")) == 1


def test_a_memory_stored_outside_a_chat_announces_nothing(clean_memory, events):
    """`memory.written` is conversation-scoped (§3.2). A fact set from the
    settings screen or loaded as a corpus has no stream to reach, and the bus
    refuses a conversation-scoped event with no conversation."""
    memory.remember("Stored with no conversation attached.")

    assert events.of_kind("memory.written") == []


def test_a_near_duplicate_is_not_stored_twice(clean_memory):
    """A model restating the same fact on consecutive turns should not fill the
    store with variants of one sentence."""
    memory.remember("I prefer dark mode in every application.")
    again = memory.remember("I prefer dark mode in every application")
    assert again["stored"] is False
    assert again["duplicate_of"]
    assert len(memory.live()) == 1


def test_similar_but_different_facts_are_both_kept(clean_memory):
    """The duplicate check must not merge facts that differ in the one token
    that matters."""
    memory.remember("I use Postgres for the main database")
    memory.remember("I use Redis for the job queue")
    assert len(memory.live()) == 2


def test_forgetting_is_soft(clean_memory):
    """A memory the user removed must not come back through a re-import that no
    longer knows it was removed."""
    mid = memory.remember("Ephemeral fact.")["id"]
    assert memory.forget(mid) is True
    assert memory.live() == []

    row = db.connect().execute("SELECT deleted_at FROM memories WHERE id=?", (mid,)).fetchone()
    assert row["deleted_at"], "the row was hard-deleted"
    assert memory.restore(mid) is True
    assert len(memory.live()) == 1


def test_empty_text_is_refused(clean_memory):
    with pytest.raises(ValueError):
        memory.remember("   ")


def test_search_ranks_the_closest_fact_first(clean_memory):
    memory.remember("The deployment runs on Tuesday mornings")
    memory.remember("I like strong coffee")
    hits = memory.search("deployment Tuesday")
    assert hits and "deployment" in hits[0]["text"]


def test_a_memory_outlives_the_conversation_that_created_it(clean_memory):
    """ON DELETE SET NULL, not CASCADE: deleting a chat clears the attribution,
    not the fact the user asked to be remembered."""
    cid = turns.create_conversation("source")["id"]
    memory.remember("Remember this beyond the chat.", conversation_id=cid)

    turns.delete_conversation(cid)

    rows = memory.live()
    assert len(rows) == 1
    assert rows[0]["conversation_id"] is None


# ── retrieval the runtime performs ───────────────────────────────────────────
def test_memory_reaches_the_prompt_without_the_model_asking(clean_memory, conversation):
    memory.remember("I prefer terse answers with no preamble.")
    bundle = context.build(conversation, "write me a function")

    assert "memory" in bundle.retrieved
    assert any("terse answers" in m["content"]
               for m in bundle.messages if m["role"] == "system")


@pytest.mark.skipif(not importer.available(), reason="graphify not installed")
def test_the_graph_reaches_the_prompt_without_the_model_asking(fresh_db, conversation):
    """Regression for the gap this suite was written to close: the graph was
    reachable only through a tool, so a model that did not think to call it
    answered from nothing."""
    importer.import_tree(REPO / "assets", scope="repo")
    bundle = context.build(conversation, "where is ingest_bytes called?")

    assert "graph" in bundle.retrieved
    injected = "\n".join(m["content"] for m in bundle.messages if m["role"] == "system")
    assert "ingest_bytes" in injected
    assert "service.py" in injected, "a hit arrived without its citation"


def test_the_conversation_graph_reaches_the_prompt(conversation):
    live.drop_all()
    # Completed, because the graph now learns only from turns that settled.
    tid = turns.create_turn(conversation, "We'll use `EventSourcing` for the audit trail.")["turn_id"]
    turns.complete(tid, "Agreed.")
    bundle = context.build(conversation, "remind me of the approach")

    assert "conversation" in bundle.retrieved
    live.drop_all()


def test_retrieval_never_breaks_a_turn(conversation, monkeypatch):
    """Retrieval is an enhancement on the hot path of every turn. A graph that
    fails to load must cost the extra context, never the reply."""
    from primnox2.knowledge import graph as knowledge

    monkeypatch.setattr(knowledge, "query",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    bundle = context.build(conversation, "still has to work")
    assert bundle.messages[-1]["content"] == "still has to work"


def test_retrieval_stays_inside_the_budget(clean_memory, conversation):
    """A tiny window must still produce a usable prompt rather than one made
    entirely of retrieved context."""
    for i in range(200):
        memory.remember(f"Distinct preference number {i} about topic {i}.")
    bundle = context.build(conversation, "hello", budget=500)
    assert bundle.tokens <= bundle.budget


# ── HTTP ─────────────────────────────────────────────────────────────────────
def test_memory_crud_over_http(client, clean_memory):
    created = client.post("/memories", json={"text": "Over HTTP", "category": "work"})
    assert created.status_code == 200 and created.json()["stored"] is True

    listed = client.get("/memories").json()
    assert any(m["text"] == "Over HTTP" for m in listed["memories"])
    assert listed["stats"]["total"] >= 1

    mid = next(m["id"] for m in listed["memories"] if m["text"] == "Over HTTP")
    assert client.delete(f"/memories/{mid}").status_code == 200
    assert not any(m["text"] == "Over HTTP" for m in client.get("/memories").json()["memories"])


def test_empty_memory_is_rejected_over_http(client, clean_memory):
    assert client.post("/memories", json={"text": "  "}).status_code == 400


def test_forgetting_an_unknown_memory_is_404(client):
    assert client.delete("/memories/mem_nope").status_code == 404


# ── memory is created in the conversation, not in a settings screen ──────────
def test_the_model_can_save_a_memory_mid_chat(clean_memory, conversation):
    """The defect this closes: `remember` did not exist, so the ONLY way to save
    a fact was a textarea in a settings tab — which nobody opens, so the store
    stayed empty while the assistant kept forgetting."""
    from primnox2.tools import registry, runtime  # noqa: F401

    ctx = registry.ToolContext(conversation_id=conversation)
    out = registry.get("remember").handler(
        {"text": "I prefer short answers.", "asked_by_user": True}, ctx)

    assert out["status"] == "success"
    rows = memory.live()
    assert rows and rows[0]["text"] == "I prefer short answers."
    assert rows[0]["provenance"] == memory.EXPLICIT
    assert rows[0]["conversation_id"] == conversation


def test_a_model_initiated_memory_is_marked_as_inferred(clean_memory, conversation):
    """Whether the user asked or the model decided is the difference between a
    fact and a guess, and the review screen has to be able to show which."""
    from primnox2.tools import registry, runtime  # noqa: F401

    registry.get("remember").handler(
        {"text": "They work mostly in Python."}, registry.ToolContext(conversation_id=conversation))
    assert memory.live()[0]["provenance"] == memory.INFERRED


def test_an_incognito_chat_refuses_to_write_a_permanent_memory(clean_memory):
    """Incognito promises nothing is written. A permanent fact extracted from
    one would be the single thing it must never do."""
    from primnox2.chat import turns
    from primnox2.tools import registry, runtime  # noqa: F401

    cid = turns.create_conversation("secret", incognito=True)["id"]
    out = registry.get("remember").handler(
        {"text": "Should never be stored."}, registry.ToolContext(conversation_id=cid))

    assert out["status"] == "error"
    assert memory.live() == []


def test_saving_the_same_fact_twice_reports_it_rather_than_failing(clean_memory, conversation):
    from primnox2.tools import registry, runtime  # noqa: F401

    ctx = registry.ToolContext(conversation_id=conversation)
    registry.get("remember").handler({"text": "I prefer dark mode always."}, ctx)
    second = registry.get("remember").handler({"text": "I prefer dark mode always."}, ctx)

    assert second["status"] == "success"
    assert "already" in second["output"].lower()
    assert len(memory.live()) == 1


def test_the_model_is_told_the_tool_exists(clean_memory):
    """A tool nobody mentions is a tool nobody calls."""
    from primnox2.tools import runtime

    prompt = runtime.system_prompt()
    assert "remember" in prompt
    assert "remember" in {s.name for s in __import__(
        "primnox2.tools.registry", fromlist=["x"]).all_specs()}


# ── bulk import ──────────────────────────────────────────────────────────────
def test_import_keeps_each_memory_at_its_own_time(clean_memory):
    """The reason `import_many` exists.

    `remember()` stamps `created_at` with now, so importing a corpus would put
    two years of history at one instant — and "which of these is current" would
    then be answered by insertion order, which happens to look right.
    """
    memory.import_many([
        {"text": "Devan prefers dark mode.", "created_at": 1_000_000_000_000},
        {"text": "Devan switched to light mode.", "created_at": 1_040_000_000_000},
    ])
    rows = memory.live()
    assert [r["text"] for r in rows] == ["Devan switched to light mode.",
                                         "Devan prefers dark mode."]
    assert [r["created_at"] for r in rows] == [1_040_000_000_000, 1_000_000_000_000]


def test_importing_the_same_pack_twice_adds_nothing(clean_memory):
    """A corpus loaded twice must not double. The dedup rule is the same one
    `remember()` uses, applied against the live store."""
    rows = [{"text": f"Devan met person {i} about project {i}.",
             "created_at": 1_000_000_000_000 + i} for i in range(20)]
    first = memory.import_many(rows)
    second = memory.import_many(rows)

    assert first["stored"] == 20
    assert (second["stored"], second["duplicates"]) == (0, 20)
    assert len(memory.live()) == 20


def test_duplicates_inside_one_import_are_caught(clean_memory):
    """Suppression has to consider what this batch already accepted, not only
    what was in the store when it began."""
    result = memory.import_many([
        {"text": "Devan writes mostly Python."},
        {"text": "Devan writes mostly Python"},
    ])
    assert (result["stored"], result["duplicates"]) == (1, 1)


def test_an_import_can_be_forgotten_like_anything_else(clean_memory):
    """Imported memories are ordinary rows: soft delete has to reach them, or a
    benchmark corpus becomes permanent furniture."""
    ids = memory.import_many([{"text": "Devan cycles to the office."}])["ids"]
    assert memory.forget(ids[0]) is True
    assert memory.live() == []
