"""Event log and bus — CRS/1.0 §3.

Two rules do most of the work here:

  §3.4  An event is committed to the log BEFORE it is pushed to any socket.
        If the push fails the event still happened; it is recoverable.

  §3.3  The log is NOT the history. Conversation history is reconstructable
        from the state tables alone. The log exists only to close the gap
        between a client's last-seen state and live — which is what makes a
        single global cursor sufficient rather than lossy (§3.3.4).
"""
from __future__ import annotations

import asyncio
import itertools
import json
import sqlite3
import threading
import time
from typing import Any, Callable

from ..chat import ephemeral
from ..ids import EVT, new_id
from ..storage import db

# CRS §3.6 — the registered set. A kind not listed here is a bug, not a
# feature: clients ignore unknown kinds (§3.2), so a typo would fail silently
# and forever. Adding a kind is a registration, never ad-hoc (§12.9).
CONVERSATION_KINDS = {
    "turn.created", "turn.status", "turn.completed", "turn.failed", "turn.cancelled",
    "token", "thinking", "job.started", "job.progress", "job.completed",
    "tool.call", "tool.result", "permission.request", "permission.resolved",
    "asset.ready", "asset.failed", "workspace.created", "workspace.updated",
    "privacy.scrub", "memory.written",
    # Emitted by knowledge/service.py's build job on completion. It was never
    # registered here, so every index build ran to completion and then died on
    # the announcement — the graph was built, the job was marked completed, and
    # the worker took a ValueError to the face on the next line. Exactly the
    # silent-typo failure §3.6 exists to prevent, caught by a sandbox audit
    # rather than by the suite, because nothing tested the build's LAST line.
    "knowledge.indexed",
    # The Sandbox Manager speaks the same protocol as everything else, which is
    # what stops the frontend needing bespoke execution logic — it renders
    # these the way it already renders tokens.
    "sandbox.created", "sandbox.stdout", "sandbox.stderr", "sandbox.progress",
    "sandbox.snapshot", "sandbox.completed", "sandbox.failed", "sandbox.destroyed",
    # Planner mode (ARCH §5.5): the model's plan is a first-class event, not
    # prose to be scraped out of the token stream.
    "plan.proposed",
}
SYSTEM_KINDS = {"sync.complete", "sync.required"}
AMBIENT_KINDS = {
    "now_playing", "flow_state", "focus_changed", "proactive_message",
    "mic_state", "vad_level", "transcript",
}
ALL_KINDS = CONVERSATION_KINDS | SYSTEM_KINDS | AMBIENT_KINDS


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, Callable[[dict], None]] = {}
        self._sub_ids = itertools.count(1)
        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        # Ambient events never touch the log (§11.1.2, §11.1.4) and carry their
        # own non-durable counter purely for local ordering.
        self._ambient_seq = itertools.count(1)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ── subscriptions ────────────────────────────────────────────────────
    def subscribe(self, fn: Callable[[dict], None]) -> int:
        with self._lock:
            sid = next(self._sub_ids)
            self._subscribers[sid] = fn
            return sid

    def unsubscribe(self, sid: int) -> None:
        with self._lock:
            self._subscribers.pop(sid, None)

    def _fanout(self, event: dict) -> None:
        with self._lock:
            subs = list(self._subscribers.values())
        for fn in subs:
            try:
                fn(event)
            except Exception:
                # A broken subscriber must never roll back a committed event.
                pass

    # ── emitting ─────────────────────────────────────────────────────────
    def emit(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        scope: str = "conversation",
        incognito: bool = False,
        conn: sqlite3.Connection | None = None,
    ) -> dict:
        """Append (unless exempt) and deliver.

        Pass `conn` from inside an open `db.tx()` to make the event part of the
        caller's transaction — which is required whenever the event describes a
        state change (§4.2). Without it the event commits separately and a
        crash between the two leaves the client's replayed stream disagreeing
        with stored state.
        """
        if kind not in ALL_KINDS:
            raise ValueError(f"unregistered event kind: {kind!r} (CRS §3.6)")
        if scope == "conversation" and conversation_id is None:
            raise ValueError("conversation-scoped events require conversation_id (CRS §3.2)")

        now = int(time.time() * 1000)

        # The bus decides, rather than trusting every caller to remember the
        # flag. A `token` event carries the reply text and a `chat.reply` job
        # event carries the prompt: one forgotten `incognito=True` anywhere in
        # the pipeline would write the conversation to disk, which is the whole
        # thing incognito promises not to do. Asking the conversation id is the
        # one check that cannot be forgotten in a call site nobody edited.
        if not incognito and ephemeral.is_incognito(conversation_id):
            incognito = True

        # Ambient and incognito never reach the log. Incognito writes no rows
        # anywhere (§11.2.1); ambient is ephemeral telemetry (§11.1.2).
        if scope == "ambient" or incognito:
            event = {
                "event_id": new_id(EVT),
                "sequence": None,
                "ambient_seq": next(self._ambient_seq),
                "ts": now,
                "scope": scope,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "kind": kind,
                "payload": payload,
                "ephemeral": True,
            }
            self._fanout(event)
            return event

        event_id = new_id(EVT)
        payload_json = json.dumps(payload)

        def _referenced_rows_exist(cid: str | None, tid: str | None) -> bool:
            """Whether the rows this event's foreign keys point at still exist.

            Checked only after an IntegrityError, so a genuine constraint bug
            still raises instead of being silently swallowed as a deletion.
            """
            try:
                c = db.connect()
                if cid is not None and c.execute(
                        "SELECT 1 FROM conversations WHERE id=?", (cid,)).fetchone() is None:
                    return False
                if tid is not None and c.execute(
                        "SELECT 1 FROM turns WHERE id=?", (tid,)).fetchone() is None:
                    return False
            except Exception:
                return False
            return True

        def _write(c: sqlite3.Connection) -> int:
            # §3.1.2 — increment the counter row inside this transaction, so a
            # rollback takes the number with it. AUTOINCREMENT would burn the
            # value permanently and leave a gap the client cannot distinguish
            # from a dropped event (§3.1.3).
            c.execute("UPDATE event_seq SET value = value + 1 WHERE id = 1")
            seq = c.execute("SELECT value FROM event_seq WHERE id = 1").fetchone()[0]
            c.execute(
                "INSERT INTO events (sequence, event_id, ts, scope, conversation_id, turn_id, kind, payload)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (seq, event_id, now, scope, conversation_id, turn_id, kind, payload_json),
            )
            return seq

        try:
            if conn is not None:
                sequence = _write(conn)
            else:
                with db.tx() as c:
                    sequence = _write(c)
        except sqlite3.IntegrityError:
            # The conversation or turn this event names was deleted between the
            # caller deciding to emit and this write. Both are foreign keys, so
            # the insert fails.
            #
            # Dropped rather than raised, because an event whose conversation is
            # gone has nowhere to live and nobody to reach: deleting a
            # conversation cascades its events away, so this row would be
            # removed the moment it landed. Raising instead killed the in-flight
            # `chat.reply` job with a stack trace for something the user did on
            # purpose — closing a chat while it was still answering.
            #
            # Narrow on purpose: only IntegrityError, and the callers that write
            # state alongside their event pass `conn`, so their transaction
            # still rolls back as one unit.
            if not _referenced_rows_exist(conversation_id, turn_id):
                return {"event_id": event_id, "sequence": None, "ts": now,
                        "scope": scope, "conversation_id": conversation_id,
                        "turn_id": turn_id, "kind": kind, "payload": payload,
                        "dropped": "target no longer exists"}
            raise

        event = {
            "event_id": event_id,
            "sequence": sequence,
            "ts": now,
            "scope": scope,
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "kind": kind,
            "payload": payload,
        }
        # Delivery happens after the write. When `conn` was supplied the
        # caller's COMMIT has not run yet, so the caller is responsible for
        # flushing — see `deferred_fanout`.
        if conn is None:
            self._fanout(event)
        return event

    def deferred_fanout(self, events: list[dict]) -> None:
        """Deliver events that were written inside a caller's transaction.

        Call after COMMIT, never before (§4.2.3) — pushing inside the
        transaction can announce a state the database then rolls back.
        """
        for e in events:
            self._fanout(e)

    # ── replay ───────────────────────────────────────────────────────────
    def head(self) -> int:
        return db.connect().execute("SELECT value FROM event_seq WHERE id = 1").fetchone()[0]

    def min_retained(self) -> int:
        return db.connect().execute("SELECT min_retained_seq FROM event_seq WHERE id = 1").fetchone()[0]

    def replay(self, last_event_seen: int, conversation_ids: list[str], limit: int = 5000) -> list[dict]:
        """CRS §8.1/§8.2 — everything after the cursor, filtered to what this
        client actually has open, plus system scope.

        Filtering is safe because of §3.3: the effects of anything filtered out
        are durable in the state tables and will be read when that conversation
        is next opened.
        """
        conn = db.connect()
        if conversation_ids:
            placeholders = ",".join("?" for _ in conversation_ids)
            sql = (
                "SELECT * FROM events WHERE sequence > ? "
                f"  AND (scope = 'system' OR conversation_id IN ({placeholders})) "
                " ORDER BY sequence LIMIT ?"
            )
            args = [last_event_seen, *conversation_ids, limit]
        else:
            sql = "SELECT * FROM events WHERE sequence > ? AND scope = 'system' ORDER BY sequence LIMIT ?"
            args = [last_event_seen, limit]

        return [
            {
                "event_id": r["event_id"],
                "sequence": r["sequence"],
                "ts": r["ts"],
                "scope": r["scope"],
                "conversation_id": r["conversation_id"],
                "turn_id": r["turn_id"],
                "kind": r["kind"],
                "payload": json.loads(r["payload"]),
            }
            for r in conn.execute(sql, args)
        ]


bus = EventBus()
