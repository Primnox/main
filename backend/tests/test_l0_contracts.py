"""L0 — Contract tests. These protect the architecture itself.

If someone changes a core object, the build fails here rather than at runtime.
Every assertion in this file is about a rule the rest of the system is entitled
to assume, so a failure means something downstream is now free to be wrong.
"""
from __future__ import annotations

import json
import sqlite3

import pytest
from conftest import run_turn, wait_for_turn

from primnox2.chat import turns
from primnox2.ids import new_id
from primnox2.kernel.events import ALL_KINDS, bus
from primnox2.storage import db

# The forward path, as specified. `failed` and `cancelled` are asserted
# separately because they are reachable from ANY non-terminal state (CRS
# §5.2.2) rather than being edges in this table.
FORWARD_TRANSITIONS = {
    "queued": {"building_context"},
    "building_context": {"thinking"},
    "thinking": {"streaming", "tool_running"},
    "tool_running": {"streaming", "thinking"},
    "streaming": {"completed", "tool_running"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}

TERMINAL = ("completed", "failed", "cancelled")
NON_TERMINAL = ("queued", "building_context", "thinking", "tool_running",
                "streaming", "awaiting_input")


def _fresh_turn(conversation_id: str, status: str = "queued") -> str:
    """A turn parked in `status`, written directly so the test controls it."""
    turn = turns.create_turn(conversation_id, "contract probe")
    tid = turn["turn_id"]
    if status != "queued":
        with db.tx() as c:
            c.execute("UPDATE turns SET status=? WHERE id=?", (status, tid))
    return tid


# ── Turn contract ────────────────────────────────────────────────────────────
class TestTurnContract:
    def test_required_fields_present(self, conversation):
        tid = _fresh_turn(conversation)
        row = db.connect().execute("SELECT * FROM turns WHERE id=?", (tid,)).fetchone()
        for field in ("id", "conversation_id", "status", "created_at"):
            assert row[field] is not None, f"turn is missing required field {field}"

    @pytest.mark.parametrize("source,targets", sorted(
        (s, t) for s, t in FORWARD_TRANSITIONS.items() if t))
    def test_declared_transitions_are_legal(self, conversation, source, targets):
        for target in targets:
            tid = _fresh_turn(conversation, source)
            turns.set_status(tid, target)
            row = db.connect().execute("SELECT status FROM turns WHERE id=?", (tid,)).fetchone()
            assert row["status"] == target, f"{source} -> {target} did not apply"

    def test_illegal_transition_is_refused(self, conversation):
        # queued -> streaming skips context assembly entirely. If this ever
        # becomes legal, a turn can stream before its user message is durable.
        tid = _fresh_turn(conversation, "queued")
        with pytest.raises(ValueError):
            turns.set_status(tid, "streaming")

    @pytest.mark.parametrize("state", TERMINAL)
    def test_terminal_states_never_transition(self, conversation, state):
        tid = _fresh_turn(conversation)
        with db.tx() as c:
            c.execute("UPDATE turns SET status=?, completed_at=1 WHERE id=?", (state, tid))
        with pytest.raises(ValueError):
            turns.set_status(tid, "streaming")

    @pytest.mark.parametrize("state", NON_TERMINAL)
    def test_cancel_reachable_from_every_live_state(self, conversation, state):
        """CRS §5.2.2 / §9.1.3.

        Not in the spec's forward table, and it must be: without this the stop
        button cannot work from a queued or tool-running turn, which is the
        exact V1 defect the rewrite exists to remove.
        """
        tid = _fresh_turn(conversation, state)
        turns.set_status(tid, "cancelled")
        row = db.connect().execute("SELECT status, completed_at FROM turns WHERE id=?", (tid,)).fetchone()
        assert row["status"] == "cancelled"
        assert row["completed_at"] is not None, "terminal turn must carry a completion time"

    def test_terminal_requires_completed_at(self, conversation):
        """The schema CHECK, exercised directly."""
        tid = _fresh_turn(conversation)
        with pytest.raises(sqlite3.IntegrityError):
            with db.tx() as c:
                c.execute("UPDATE turns SET status='completed', completed_at=NULL WHERE id=?", (tid,))

    def test_at_most_one_assistant_message(self, conversation):
        """CRS §2.2 — enforced by the database, not by convention."""
        tid = _fresh_turn(conversation)
        with db.tx() as c:
            c.execute("INSERT INTO messages (id,turn_id,role,text,created_at) VALUES (?,?,?,?,?)",
                      (new_id("msg"), tid, "assistant", "one", 1))
        with pytest.raises(sqlite3.IntegrityError):
            with db.tx() as c:
                c.execute("INSERT INTO messages (id,turn_id,role,text,created_at) VALUES (?,?,?,?,?)",
                          (new_id("msg"), tid, "assistant", "two", 2))

    def test_unknown_status_rejected(self, conversation):
        tid = _fresh_turn(conversation)
        with pytest.raises(sqlite3.IntegrityError):
            with db.tx() as c:
                c.execute("UPDATE turns SET status='vibing' WHERE id=?", (tid,))


# ── Event contract ───────────────────────────────────────────────────────────
class TestEventContract:
    REQUIRED = ("event_id", "sequence", "ts", "scope", "kind", "payload")

    def test_no_anonymous_events(self, conversation, events, scripted):
        scripted("A short reply.")
        tid = run_turn(conversation, "hello")
        assert wait_for_turn(tid) == "completed"

        emitted = events.for_turn(tid)
        assert emitted, "a completed turn emitted no events at all"
        for e in emitted:
            for field in self.REQUIRED:
                assert e.get(field) is not None, f"{e['kind']} is missing {field}"
            assert e["kind"] in ALL_KINDS, f"unregistered kind {e['kind']}"
            # Every turn-scoped event names its turn. This is what stops tokens
            # landing in the wrong reply (CRS Appendix A).
            assert e["turn_id"] == tid
            assert e["conversation_id"] == conversation

    def test_unregistered_kind_is_refused(self, conversation):
        with pytest.raises(ValueError):
            bus.emit("turn.vibed", {}, conversation_id=conversation)

    def test_conversation_scope_requires_conversation_id(self):
        with pytest.raises(ValueError):
            bus.emit("token", {"text": "x"}, conversation_id=None)

    def test_sequence_strictly_increases(self, conversation, events, scripted):
        scripted("Sequenced.")
        tid = run_turn(conversation, "hello")
        wait_for_turn(tid)
        seqs = [e["sequence"] for e in events.for_turn(tid) if e.get("sequence")]
        assert seqs == sorted(seqs), "events were emitted out of sequence order"
        assert len(seqs) == len(set(seqs)), "a sequence number was reused"

    def test_global_sequence_is_gapless(self, conversation):
        """CRS §3.1.3 — the property AUTOINCREMENT cannot provide.

        Gaplessness belongs to the COUNTER, not to the stored rows. Deleting a
        turn cascades to its events and legitimately leaves holes in the table;
        that is deletion, not loss, and §8.3's `min_retained_seq` is what tells
        a stale client to resync. What must never happen is the counter
        skipping a value, because then a client cannot tell "nothing happened"
        from "I missed something".
        """
        before = bus.head()
        emitted = [bus.emit("token", {"text": "x"}, conversation_id=conversation)["sequence"]
                   for _ in range(25)]
        assert emitted == list(range(before + 1, before + 26)), "the counter skipped a value"
        assert bus.head() == before + 25

    def test_sequences_are_never_reused(self):
        rows = [r["sequence"] for r in
                db.connect().execute("SELECT sequence FROM events ORDER BY sequence")]
        assert len(rows) == len(set(rows)), "a sequence number was reused"
        assert rows == sorted(rows)
        assert max(rows) <= bus.head(), "an event claims a sequence beyond the counter"

    def test_rollback_returns_the_sequence_number(self, conversation):
        """A failed transaction must not burn a sequence number."""
        before = bus.head()
        with pytest.raises(sqlite3.IntegrityError):
            with db.tx() as c:
                bus.emit("token", {"text": "doomed"}, conversation_id=conversation,
                         turn_id=None, conn=c)
                # Force the transaction to fail after the event was written.
                c.execute("INSERT INTO turns (id,conversation_id,seq_in_conversation,status,created_at)"
                          " VALUES ('dup','nope',1,'queued',1)")
        assert bus.head() == before, "a rolled-back transaction left a gap in the sequence"


# ── Database contract ────────────────────────────────────────────────────────
class TestDatabaseContract:
    def test_turn_completion_is_atomic(self, conversation):
        """Either the turn is completed AND the event exists, or neither.

        Simulated by failing inside the same transaction that would commit
        both. A crash here must leave no completed turn without its event.
        """
        tid = _fresh_turn(conversation, "streaming")
        head_before = bus.head()

        with pytest.raises(sqlite3.IntegrityError):
            with db.tx() as c:
                c.execute("UPDATE turns SET status='completed', completed_at=1 WHERE id=?", (tid,))
                bus.emit("turn.completed", {"assistant_message": {"text": "x"}, "usage": {}},
                         conversation_id=conversation, turn_id=tid, conn=c)
                c.execute("INSERT INTO messages (id,turn_id,role,text,created_at)"
                          " VALUES (?,?,?,?,?)", (new_id("msg"), "no-such-turn", "assistant", "x", 1))

        row = db.connect().execute("SELECT status FROM turns WHERE id=?", (tid,)).fetchone()
        assert row["status"] == "streaming", "the turn was completed without its event"
        assert bus.head() == head_before, "the event survived a rolled-back state change"

    def test_single_database(self):
        """CRS §4.1 — state and log in one file, or atomicity is impossible."""
        names = {r[0] for r in db.connect().execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("turns", "events", "jobs", "assets", "workspaces", "execution_sessions"):
            assert table in names, f"{table} is not in primnox.db"

    def test_foreign_keys_enforced_on_this_connection(self):
        """§4.3.1 — per-connection, so it must be set on every connection."""
        assert db.connect().execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_wal_mode(self):
        assert db.connect().execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    def test_referential_integrity_intact(self):
        assert db.connect().execute("PRAGMA foreign_key_check").fetchall() == []

    def test_history_reconstructable_without_the_log(self, conversation, scripted):
        """CRS §3.3.1 — the load-bearing rule.

        History must come from the state tables alone. If this fails, the log
        has become the storage format and retention can destroy data.
        """
        scripted("Durable answer.")
        tid = run_turn(conversation, "remember this")
        wait_for_turn(tid)

        history = turns.get_history(conversation)
        assert history, "no history was reconstructed"
        answered = [t for t in history if t["turn_id"] == tid]
        assert answered and answered[0]["assistant_message"]["text"] == "Durable answer."

        # Prove it did not consult the log: the query in get_history touches no
        # events table, so deleting every event changes nothing.
        with db.tx() as c:
            c.execute("DELETE FROM events")
        after = turns.get_history(conversation)
        assert [t["turn_id"] for t in after] == [t["turn_id"] for t in history]
        assert after[0]["assistant_message"] is not None


class TestNoGlobalStatus:
    def test_status_is_per_turn_never_global(self, conversation, events, scripted):
        """CRS §5.3 — a runtime-level scalar cannot represent five queued turns."""
        scripted("ok")
        tid = run_turn(conversation, "one")
        wait_for_turn(tid)
        for e in events.of_kind("turn.status", tid):
            assert e["turn_id"], "a status event was emitted without a turn"
