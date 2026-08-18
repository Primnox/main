"""Knowledge Service (V2.2) — store, import, live graph.

The import tests run against Graphify's real output rather than a fixture: the
three failure modes that matter (dangling edge targets, repeated triples,
self-edges) are properties of the real extractor, and a hand-written fixture
would only ever assert what I already believed.
"""
from __future__ import annotations

import pathlib

import pytest

from primnox2.chat import turns
# Deliberately the consumer's own estimator. These tests assert that a rendered
# block fits the budget reserved for it, so measuring with anything other than
# what the context service measures with is measuring the wrong thing — that
# gap is exactly how the renderer drifted 14% over budget unnoticed.
from primnox2.context import service as context
from primnox2.knowledge import graph, importer, live
from primnox2.storage import db

REPO = pathlib.Path(__file__).resolve().parents[1] / "primnox2"


# ── Store ────────────────────────────────────────────────────────────────────
def test_node_upsert_is_idempotent_on_scope_and_key(fresh_db):
    with db.tx() as c:
        a = graph.upsert_node(c, key="mod_fn", label="fn()", type="function", scope="s1")
        b = graph.upsert_node(c, key="mod_fn", label="fn()", type="function", scope="s1")
    assert a == b
    assert db.connect().execute("SELECT COUNT(*) c FROM knowledge_nodes").fetchone()["c"] == 1


def test_same_key_in_a_different_scope_is_a_different_node(fresh_db):
    with db.tx() as c:
        a = graph.upsert_node(c, key="fn", label="fn()", type="function", scope="s1")
        b = graph.upsert_node(c, key="fn", label="fn()", type="function", scope="s2")
    assert a != b


def test_self_edges_are_dropped_not_raised(fresh_db):
    """A recursive function is normal. Failing the build over one would trade a
    whole graph for a node the neighbour walk already has."""
    with db.tx() as c:
        n = graph.upsert_node(c, key="recurse", label="recurse()", type="function", scope="s")
        assert graph.upsert_edge(c, source_id=n, target_id=n,
                                 relation="calls", confidence="EXTRACTED") is None


def test_repeated_edges_accumulate_weight(fresh_db):
    with db.tx() as c:
        a = graph.upsert_node(c, key="a", label="a()", type="function", scope="s")
        b = graph.upsert_node(c, key="b", label="b()", type="function", scope="s")
        for _ in range(3):
            graph.upsert_edge(c, source_id=a, target_id=b, relation="calls",
                              confidence="EXTRACTED", context="call")
    rows = db.connect().execute("SELECT weight FROM knowledge_edges").fetchall()
    assert len(rows) == 1
    assert rows[0]["weight"] == pytest.approx(3.0)


def test_context_distinguishes_edges_between_the_same_pair(fresh_db):
    """`calls b` and `type-hints b` are different facts about the same pair."""
    with db.tx() as c:
        a = graph.upsert_node(c, key="a", label="a()", type="function", scope="s")
        b = graph.upsert_node(c, key="b", label="B", type="class", scope="s")
        graph.upsert_edge(c, source_id=a, target_id=b, relation="calls",
                          confidence="EXTRACTED", context="call")
        graph.upsert_edge(c, source_id=a, target_id=b, relation="calls",
                          confidence="EXTRACTED", context="parameter_type")
    assert db.connect().execute("SELECT COUNT(*) c FROM knowledge_edges").fetchone()["c"] == 2


def test_contextless_edges_cannot_duplicate(fresh_db):
    """Regression: `context` nullable would make SQLite treat every NULL as
    distinct in the UNIQUE index, so the same edge would insert forever."""
    with db.tx() as c:
        a = graph.upsert_node(c, key="a", label="a", type="entity", scope="s")
        b = graph.upsert_node(c, key="b", label="b", type="entity", scope="s")
        for _ in range(4):
            graph.upsert_edge(c, source_id=a, target_id=b, relation="related",
                              confidence="INFERRED")
    assert db.connect().execute("SELECT COUNT(*) c FROM knowledge_edges").fetchone()["c"] == 1


def test_deleting_a_node_cascades_to_its_edges(fresh_db):
    with db.tx() as c:
        a = graph.upsert_node(c, key="a", label="a", type="entity", scope="s")
        b = graph.upsert_node(c, key="b", label="b", type="entity", scope="s")
        graph.upsert_edge(c, source_id=a, target_id=b, relation="related",
                          confidence="INFERRED")
    with db.tx() as c:
        c.execute("DELETE FROM knowledge_nodes WHERE id=?", (a,))
    assert db.connect().execute("SELECT COUNT(*) c FROM knowledge_edges").fetchone()["c"] == 0


def test_bad_confidence_is_rejected(fresh_db):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        with db.tx() as c:
            a = graph.upsert_node(c, key="a", label="a", type="entity", scope="s")
            b = graph.upsert_node(c, key="b", label="b", type="entity", scope="s")
            graph.upsert_edge(c, source_id=a, target_id=b, relation="r",
                              confidence="PROBABLY")


# ── Type derivation ──────────────────────────────────────────────────────────
def test_a_class_is_not_filed_as_a_function():
    """A Python class carries BOTH _callable and _callable_class. Testing
    _callable first files every class in the codebase as a function."""
    assert graph._derive_type({"_callable": True, "_callable_class": True}) == "class"
    assert graph._derive_type({"_callable": True}) == "function"
    assert graph._derive_type({"file_type": "rationale"}) == "rationale"
    assert graph._derive_type({"source_location": "L1"}) == "file"
    assert graph._derive_type({}) == "entity"


# ── Import against the real extractor ────────────────────────────────────────
@pytest.mark.skipif(not importer.available(), reason="graphify not installed")
def test_importing_this_repo_produces_a_connected_graph(fresh_db):
    result = importer.import_tree(REPO, scope="repo")

    assert result["nodes"] > 200, "extraction produced suspiciously little"
    assert result["edges"] > 500

    # Graphify emits `imports asyncio` without emitting a node for asyncio.
    # Dropping those loses the dependency graph entirely.
    assert result["implicit_nodes"] > 0

    orphans = db.connect().execute(
        "SELECT COUNT(*) c FROM knowledge_edges e"
        " LEFT JOIN knowledge_nodes s ON s.id=e.source_id"
        " LEFT JOIN knowledge_nodes t ON t.id=e.target_id"
        " WHERE s.id IS NULL OR t.id IS NULL").fetchone()["c"]
    assert orphans == 0


@pytest.mark.skipif(not importer.available(), reason="graphify not installed")
def test_reimport_replaces_rather_than_doubles(fresh_db):
    first = importer.import_tree(REPO, scope="repo")
    before = graph.stats()
    second = importer.import_tree(REPO, scope="repo")
    after = graph.stats()

    assert second["removed"] == before["nodes"]
    assert after["nodes"] == before["nodes"], "re-import doubled the graph"
    assert after["edges"] == before["edges"]
    assert first["nodes"] == second["nodes"]


@pytest.mark.skipif(not importer.available(), reason="graphify not installed")
def test_query_returns_citations_for_a_known_symbol(fresh_db):
    importer.import_tree(REPO, scope="repo")
    out = graph.query("ingest_bytes", token_budget=800)

    assert "ingest_bytes" in out
    assert "assets/service.py" in out, "a hit without a citation is not useful"
    assert out.startswith("NODE ")


@pytest.mark.skipif(not importer.available(), reason="graphify not installed")
def test_query_respects_its_token_budget(fresh_db):
    importer.import_tree(REPO, scope="repo")
    small = graph.query("service", token_budget=100)
    large = graph.query("service", token_budget=4000)

    assert len(small) < len(large)
    assert context.estimate_tokens(small) <= 115, "the 100-token budget was overrun"


@pytest.mark.skipif(not importer.available(), reason="graphify not installed")
def test_a_scope_can_be_cleared_without_touching_another(fresh_db):
    importer.import_tree(REPO / "storage", scope="a")
    importer.import_tree(REPO / "storage", scope="b")
    before_b = db.connect().execute(
        "SELECT COUNT(*) c FROM knowledge_nodes WHERE scope='b'").fetchone()["c"]
    with db.tx() as c:
        graph.clear_scope(c, "a")
    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) c FROM knowledge_nodes WHERE scope='a'").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM knowledge_nodes WHERE scope='b'").fetchone()["c"] == before_b


# ── Live conversation graph ──────────────────────────────────────────────────
def test_an_incognito_graph_is_never_written_to_the_database(fresh_db):
    """Incognito messages never reach the disk, so nothing derived from them may.

    Compares row counts before and after rather than asserting the database is
    empty — the suite shares one database across the session, so "empty" would
    be measuring the other tests rather than this one.
    """
    conn = db.connect()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    before = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in tables}

    g = live.for_conversation("conv_incognito", persistent=False)
    g.observe_message("We should use PaymentGateway with `stripe_client` in api/pay.py",
                      role="user", turn=1)
    assert g.nodes, "nothing was harvested, so the test would pass vacuously"
    assert g.save() is False, "an incognito graph agreed to persist itself"

    after = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in tables}
    assert after == before, "an incognito graph wrote to the database"
    live.drop_all()


def test_a_conversation_graph_survives_the_process(fresh_db):
    """The chat is saved, so its graph is too — otherwise recall returns nothing
    for every conversation the user did not have in the last few minutes."""
    cid = turns.create_conversation("persistent")["id"]
    g = live.for_conversation(cid)
    g.observe_message("We'll go with `EventSourcing` for the audit trail.",
                      role="assistant", turn=1)
    assert g.save() is True

    live.drop_all()   # simulate a restart: nothing left in memory

    restored = live.for_conversation(cid)
    labels = {n["label"] for n in restored.nodes.values()}
    assert "EventSourcing" in labels, "the graph did not survive"
    assert restored.decisions(), "decisions did not survive"
    live.drop_all()


def test_deleting_a_conversation_cascades_to_its_saved_graph(fresh_db):
    cid = turns.create_conversation("doomed")["id"]
    live.for_conversation(cid).observe_message("`DoomedThing` here", role="user", turn=1)
    live.save(cid)

    scope = live.scope_for(cid)
    assert db.connect().execute(
        "SELECT COUNT(*) c FROM knowledge_nodes WHERE scope=?", (scope,)).fetchone()["c"] > 0

    turns.delete_conversation(cid)

    assert db.connect().execute(
        "SELECT COUNT(*) c FROM knowledge_nodes WHERE scope=?", (scope,)).fetchone()["c"] == 0, \
        "a conversation's graph outlived the conversation"
    live.drop_all()


def test_saving_replaces_rather_than_accumulates(fresh_db):
    cid = turns.create_conversation("resave")["id"]
    g = live.for_conversation(cid)
    g.observe_message("`AlphaThing` first", role="user", turn=1)
    g.save()
    first = db.connect().execute(
        "SELECT COUNT(*) c FROM knowledge_nodes WHERE scope=?",
        (live.scope_for(cid),)).fetchone()["c"]

    g.observe_message("`AlphaThing` again", role="user", turn=2)
    g.save()
    second = db.connect().execute(
        "SELECT COUNT(*) c FROM knowledge_nodes WHERE scope=?",
        (live.scope_for(cid),)).fetchone()["c"]

    assert second == first, "re-saving duplicated the graph instead of replacing it"
    live.drop_all()


def test_live_graph_harvests_entities_files_and_decisions():
    live.drop_all()
    g = live.for_conversation("conv_y")
    g.observe_message("Let's use SQLite for this. The `event_seq` counter lives "
                      "in storage/db.py and PaymentGateway calls it.",
                      role="assistant", turn=1)

    labels = {n["label"] for n in g.nodes.values()}
    assert "PaymentGateway" in labels
    assert "event_seq" in labels
    assert "storage/db.py" in labels
    assert any(n["kind"] == live.DECISION for n in g.nodes.values())
    live.drop_all()


def test_a_decision_naming_a_file_keeps_the_extension():
    """Regression: the sentence-terminator run ended at the first period, so
    "put it in storage/db.py" was stored as "storage/db" - truncated at exactly
    the token the decision was about."""
    live.drop_all()
    g = live.for_conversation("conv_dot", persistent=False)
    g.observe_message("We'll put the counter in storage/db.py for now.",
                      role="assistant", turn=1)

    decisions = [d["label"] for d in g.decisions()]
    assert decisions, "no decision was captured"
    assert any("storage/db.py" in d for d in decisions), \
        f"decision truncated at the dot: {decisions}"
    live.drop_all()


def test_live_graph_recalls_an_earlier_decision():
    """'go back to the third architecture option' without re-reading the chat."""
    live.drop_all()
    g = live.for_conversation("conv_z")
    g.observe_message("We decided to use WAL mode for the database.", role="user", turn=1)
    for t in range(2, 12):
        g.observe_message(f"Unrelated turn {t} about other things.", role="user", turn=t)

    hits = g.recall("WAL")
    assert hits, "a decision from turn 1 was lost by turn 11"
    assert "WAL" in hits[0]["label"]
    live.drop_all()


def test_live_graph_evicts_but_never_a_decision():
    live.drop_all()
    g = live.for_conversation("conv_evict")
    g.observe_message("We decided to use Postgres.", role="user", turn=0)
    for i in range(live.MAX_NODES + 60):
        g.note(f"Filler{i}", live.ENTITY, turn=i)

    assert len(g.nodes) <= live.MAX_NODES
    assert any(n["kind"] == live.DECISION for n in g.nodes.values()), \
        "eviction ate the decisions, which are the point"
    live.drop_all()


def test_dropping_a_conversation_drops_its_graph(fresh_db):
    live.drop_all()
    live.for_conversation("conv_a").note("Thing", live.ENTITY)
    assert "conv_a" in live.active()
    assert live.drop("conv_a") is True
    assert "conv_a" not in live.active()
    assert live.for_conversation("conv_a").nodes == {}
    live.drop_all()


def test_evicting_keeps_what_was_saved(fresh_db):
    """Closing a chat frees memory; it does not forget the chat."""
    cid = turns.create_conversation("evictable")["id"]
    live.for_conversation(cid).observe_message("`KeptThing` here", role="user", turn=1)

    assert live.evict(cid) is True
    assert cid not in live.active()

    assert any(n["label"] == "KeptThing"
               for n in live.for_conversation(cid).nodes.values()), \
        "eviction lost the graph instead of freeing memory"
    live.drop_all()


def test_live_graphs_do_not_leak_between_conversations():
    live.drop_all()
    live.for_conversation("c1").observe_message("`SecretThing` here", role="user", turn=1)
    g2 = live.for_conversation("c2")
    assert not g2.recall("SecretThing")
    live.drop_all()


# ── Wiring ───────────────────────────────────────────────────────────────────
def test_creating_a_turn_feeds_the_live_graph(conversation):
    """Regression: the graph and its tool are useless if nothing populates it.

    This suite already caught one dead control (a Retry button with no onClick);
    an unwired observer is the same defect a layer down — every unit passes and
    the feature does nothing.
    """
    live.drop_all()
    turns.create_turn(conversation, "Please look at `PaymentGateway` in api/pay.py")

    g = live.for_conversation(conversation)
    labels = {n["label"] for n in g.nodes.values()}
    assert "PaymentGateway" in labels
    assert "api/pay.py" in labels
    live.drop_all()


def test_completing_a_turn_feeds_the_live_graph(conversation):
    live.drop_all()
    tid = turns.create_turn(conversation, "what next")["turn_id"]
    turns.complete(tid, "We'll use `WriteAheadLog` for durability.")

    g = live.for_conversation(conversation)
    assert any("WriteAheadLog" == n["label"] for n in g.nodes.values())
    live.drop_all()


def test_deleting_a_conversation_drops_its_live_graph():
    cid = turns.create_conversation("disposable")["id"]
    turns.create_turn(cid, "Discussing `TransientThing` here")
    assert live.for_conversation(cid).nodes

    turns.delete_conversation(cid)
    assert cid not in live.active()
    live.drop_all()


def test_observation_never_breaks_a_turn(conversation, monkeypatch):
    """An ambient nicety must not cost the user their reply."""
    def boom(*a, **k):
        raise RuntimeError("regex exploded")

    monkeypatch.setattr(live.LiveGraph, "observe_message", boom)
    result = turns.create_turn(conversation, "still has to work")
    assert result["turn_id"]
    live.drop_all()


# ── Token economics ──────────────────────────────────────────────────────────
def _corpus_tokens(symbol: str) -> int:
    """What a model without a graph has to read: every file naming the symbol."""
    total = 0
    for p in REPO.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if symbol in text:
            total += context.estimate_tokens(text)
    return total


@pytest.mark.skipif(not importer.available(), reason="graphify not installed")
def test_graph_answer_is_bounded_by_its_budget(fresh_db):
    """The real invariant, and the one that survives a bigger corpus.

    A graph answer costs what you budget. Reading the files costs what the
    files happen to weigh, which nobody controls. Measured here: at a 400-token
    budget the answer obeys it, while the same question over source is ~15k
    tokens on this repo and would be far worse on a large one.
    """
    importer.import_tree(REPO, scope="repo")
    for budget in (200, 400, 1000):
        answer = graph.query("ingest_bytes", token_budget=budget)
        tokens = context.estimate_tokens(answer)
        assert tokens <= budget + 20, f"budget {budget} produced {tokens} tokens"


@pytest.mark.skipif(not importer.available(), reason="graphify not installed")
def test_graph_answer_is_cheaper_than_reading_the_corpus(fresh_db):
    """Measured on this repo at a realistic retrieval budget.

    The ratio is a function of corpus size, not a constant: it is ~7x here at a
    2000-token budget and grows with the codebase, because the graph side is
    pinned to the budget while the corpus side is not. The threshold below is
    deliberately loose - this asserts the direction holds, not a number that
    would break every time a file is added.
    """
    importer.import_tree(REPO, scope="repo")
    answer = graph.query("ingest_bytes", token_budget=500)
    graph_tokens = context.estimate_tokens(answer)
    corpus = _corpus_tokens("ingest_bytes")

    assert graph_tokens > 0, "the graph answered nothing"
    assert corpus > 0, "no file mentions the symbol; the comparison is vacuous"
    assert graph_tokens * 4 < corpus, (
        f"graph {graph_tokens} tok vs corpus {corpus} tok - "
        "the retrieval saving the design is premised on did not hold"
    )


def _relations(g, kind):
    """Edges of one relation, as (decision label, subject label) pairs."""
    return {
        (g.nodes[e["source"]]["label"], g.nodes[e["target"]]["label"])
        for e in g.edges
        if e["relation"] == kind and e["source"] in g.nodes and e["target"] in g.nodes
    }


def test_a_decision_is_linked_to_what_it_is_about(fresh_db):
    """A decision with degree zero is unreachable knowledge.

    Measured on the real store before this held: every decision node had no
    edges at all, while the entities named inside them were fully cross-linked
    to each other. The idea was recorded and the subject was recorded, so
    "what did we decide about storage/db.py" had every fact it needed and no
    path between them.
    """
    cid = turns.create_conversation("decisions")["id"]
    g = live.for_conversation(cid)
    g.observe_message(
        "Let's use `EventSourcing` and put the counter in storage/db.py",
        role="assistant", turn=1)

    decisions = g.decisions()
    assert decisions, "no decision was harvested; the test would pass vacuously"

    subjects = {subject for _, subject in _relations(g, "concerns")}
    assert "EventSourcing" in subjects, "the decision is not linked to the concept"
    assert "storage/db.py" in subjects, "the decision is not linked to the file"
    live.drop_all()


def test_a_decision_is_not_linked_to_passing_mentions(fresh_db):
    """Subjects come from the decision's own span, not the whole message.

    A turn routinely settles one thing and mentions another in passing. Linking
    to everything in the message would make "what did we decide about X" answer
    with Y — worse than not answering, because it reads as a real commitment.
    """
    cid = turns.create_conversation("passing")["id"]
    g = live.for_conversation(cid)
    g.observe_message(
        "Let's use `EventSourcing` for the audit trail. "
        "Unrelatedly `PaymentGateway` came up yesterday and needs no change.",
        role="assistant", turn=1)

    subjects = {subject for _, subject in _relations(g, "concerns")}
    assert "EventSourcing" in subjects, "the decision lost its actual subject"
    assert "PaymentGateway" not in subjects, \
        "a passing mention was recorded as something the decision settled"
    live.drop_all()


def test_linking_a_decision_does_not_inflate_mention_counts(fresh_db):
    """`mentions` drives eviction order and salience, so it has to stay honest.

    A path is used deliberately: it is caught by exactly one of the three
    harvest patterns, so the expected count is unambiguous. Re-scanning the
    decision span for subjects instead of reusing the keys already harvested
    would double it.
    """
    cid = turns.create_conversation("counts")["id"]
    g = live.for_conversation(cid)
    g.observe_message("Let's use storage/db.py for this", role="user", turn=1)

    node = g.nodes["file:storage/db.py"]
    assert node["mentions"] == 1, \
        f"named once, counted {node['mentions']} times"
    live.drop_all()


def test_decision_links_survive_a_save_and_reload(fresh_db):
    """The link is only useful if it outlives the process — recall happens on
    chats the user did not have in the last few minutes."""
    cid = turns.create_conversation("durable-links")["id"]
    g = live.for_conversation(cid)
    g.observe_message("We'll go with `EventSourcing` for the audit trail",
                      role="assistant", turn=1)
    assert _relations(g, "concerns"), "nothing to persist; the test is vacuous"
    assert g.save() is True

    live.drop_all()

    restored = live.for_conversation(cid)
    subjects = {subject for _, subject in _relations(restored, "concerns")}
    assert "EventSourcing" in subjects, "the decision link did not survive a reload"
    live.drop_all()
