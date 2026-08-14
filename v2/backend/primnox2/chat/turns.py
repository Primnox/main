"""Conversations and turns — CRS/1.0 §2.1, §2.2, §5.

The Turn is the abstraction V1 lacked. Because it exists, a unit of work can be
named, cancelled, resumed, and attributed after the fact; because it did not,
V1 could have none of those things.
"""
from __future__ import annotations

import json
import time
from typing import Any

from ..ids import CONV, MSG, TURN, new_id
from ..kernel.events import bus
from ..knowledge import live
from ..storage import db
from . import ephemeral

TERMINAL = ("completed", "failed", "cancelled")

# CRS §5.2 — the only legal transitions. Encoded rather than commented so an
# illegal one raises here instead of producing a turn the UI cannot render.
#
# `thinking` is the model call in flight with no token yet; `streaming` is
# tokens arriving. Keeping them apart is what lets the UI distinguish "slow
# provider" from "slow reply", which a single spinner never could.
_LEGAL: dict[str, set[str]] = {
    "queued":           {"building_context", "failed", "cancelled"},
    "building_context": {"thinking", "tool_running", "failed", "cancelled"},
    "thinking":         {"streaming", "tool_running", "awaiting_input", "completed", "failed", "cancelled"},
    "streaming":        {"thinking", "tool_running", "awaiting_input", "completed", "failed", "cancelled"},
    "tool_running":     {"thinking", "streaming", "awaiting_input", "completed", "failed", "cancelled"},
    "awaiting_input":   {"thinking", "streaming", "tool_running", "failed", "cancelled"},
    "completed":        set(),
    "failed":           set(),
    "cancelled":        set(),
}

now_ms = lambda: int(time.time() * 1000)


# ── Conversations ────────────────────────────────────────────────────────────
def create_conversation(title: str = "New Chat", incognito: bool = False) -> dict:
    """CRS §11.2.1 — an incognito conversation writes no row, here or anywhere.

    Everything downstream decides by asking whether the *id* is incognito
    rather than by being handed a flag. A flag has to be threaded through every
    caller and only has to be forgotten once: the HTTP layer forgot it, and the
    first turn of every incognito conversation died on a foreign key.
    """
    cid, ts = new_id(CONV), now_ms()
    if incognito:
        return {**ephemeral.register_conversation(cid, title), "incognito": True}
    with db.tx() as c:
        c.execute(
            "INSERT INTO conversations (id,title,incognito,created_at,updated_at) VALUES (?,?,?,?,?)",
            (cid, title, 0, ts, ts),
        )
    return {"id": cid, "title": title, "incognito": False, "created_at": ts, "updated_at": ts}


def is_incognito(conversation_id: str | None) -> bool:
    return ephemeral.is_incognito(conversation_id)


def close_incognito(conversation_id: str) -> dict:
    """Forget an incognito conversation on request. Ordinary ones are archived
    and keep their rows; there is nothing here to archive."""
    if not ephemeral.is_incognito(conversation_id):
        return {"ok": False, "reason": "not an incognito conversation"}
    ephemeral.forget_conversation(conversation_id)
    live.drop(conversation_id)
    return {"ok": True}


def list_conversations(limit: int = 100, archived: bool = False) -> list[dict]:
    rows = db.connect().execute(
        "SELECT c.*, (SELECT COUNT(*) FROM turns t WHERE t.conversation_id = c.id) AS turn_count"
        "  FROM conversations c"
        f" WHERE c.archived_at IS {'NOT NULL' if archived else 'NULL'}"
        # `c.id DESC` is the tiebreak, and it is not cosmetic: two conversations
        # created in the same millisecond tie on updated_at, and SQLite is then
        # free to return them in any order — so the sidebar could reorder itself
        # between two identical reads. Ids are uuid7, so descending id is
        # descending creation time and the tie resolves the same way every time.
        " ORDER BY c.updated_at DESC, c.id DESC LIMIT ?",
        (limit,),
    )
    listed = [dict(r) for r in rows]
    if not archived:
        listed += ephemeral.list_conversations()

    # Pinned first and in the order they were pinned; everything else by
    # recency. Sorting pins by `updated_at` would make them swap places whenever
    # either was used, which is the opposite of what pinning is for.
    #
    # Two passes rather than one clever key, because the two groups tie-break in
    # OPPOSITE directions: pins ascend (oldest pin on top), the rest descend
    # (newest chat on top). Ids are uuid7 strings, so a single sort key would
    # have to negate a string to express both, and a shared key that resolves
    # ties one way silently reverses whichever group wanted the other.
    # Millisecond collisions are routine — two conversations created in one
    # tick tie on both timestamps — so the tie-break is the common path, not a
    # corner case.
    pinned = sorted((c for c in listed if c.get("pinned_at")),
                    key=lambda c: (c["pinned_at"], c["id"]))
    rest = sorted((c for c in listed if not c.get("pinned_at")),
                  key=lambda c: (c["updated_at"], c["id"]), reverse=True)
    return (pinned + rest)[:limit]


def rename_conversation(conversation_id: str, title: str) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("a conversation needs a title")
    if ephemeral.is_incognito(conversation_id):
        record = ephemeral.conversation(conversation_id)
        if record is None:
            raise KeyError(conversation_id)
        ephemeral.rename_conversation(conversation_id, title[:200])
        return {"id": conversation_id, "title": title[:200]}
    with db.tx() as c:
        cur = c.execute("UPDATE conversations SET title = ? WHERE id = ?",
                        (title[:200], conversation_id))
        if cur.rowcount == 0:
            raise KeyError(conversation_id)
    return {"id": conversation_id, "title": title[:200]}


def set_pinned(conversation_id: str, pinned: bool) -> dict:
    """Pinning is a timestamp so pins keep a stable order."""
    if ephemeral.is_incognito(conversation_id):
        # An incognito conversation cannot outlive the process, so pinning one
        # would promise a permanence it does not have.
        raise ValueError("an incognito conversation cannot be pinned")
    stamp = now_ms() if pinned else None
    with db.tx() as c:
        cur = c.execute("UPDATE conversations SET pinned_at = ? WHERE id = ?",
                        (stamp, conversation_id))
        if cur.rowcount == 0:
            raise KeyError(conversation_id)
    return {"id": conversation_id, "pinned_at": stamp}


def archive_conversation(conversation_id: str, archived: bool = True) -> dict:
    """Out of the list, still on disk. Reversible, and named for what it is."""
    if ephemeral.is_incognito(conversation_id):
        raise ValueError("an incognito conversation is closed, not archived")
    stamp = now_ms() if archived else None
    with db.tx() as c:
        cur = c.execute(
            "UPDATE conversations SET archived_at = ?, pinned_at = CASE WHEN ? "
            "THEN NULL ELSE pinned_at END WHERE id = ?",
            (stamp, 1 if archived else 0, conversation_id))
        if cur.rowcount == 0:
            raise KeyError(conversation_id)
    return {"id": conversation_id, "archived_at": stamp}


def delete_conversation(conversation_id: str) -> dict:
    """Permanent. Turns, messages and events go with it, by foreign key.

    Assets do NOT: a document survives the conversation that produced it
    (§2.1), and `turn_assets` cascading away leaves the asset itself intact.
    That is deliberate — deleting a chat should not silently destroy the report
    it generated.
    """
    # The conversation's own graph goes too. The database rows would cascade
    # from the conversation row anyway; this also clears the in-memory copy, and
    # covers incognito, which has no row to cascade from.
    live.drop(conversation_id)
    if ephemeral.is_incognito(conversation_id):
        ephemeral.forget_conversation(conversation_id)
        return {"id": conversation_id, "deleted": True}
    with db.tx() as c:
        cur = c.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        if cur.rowcount == 0:
            raise KeyError(conversation_id)
    return {"id": conversation_id, "deleted": True}


# ── Folders ──────────────────────────────────────────────────────────────────
def list_folders() -> list[dict]:
    rows = db.connect().execute(
        "SELECT f.*, (SELECT COUNT(*) FROM conversations c"
        "               WHERE c.folder_id = f.id AND c.archived_at IS NULL) AS conversation_count"
        "  FROM folders f ORDER BY f.name COLLATE NOCASE")
    return [dict(r) for r in rows]


def create_folder(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("a folder needs a name")
    fid, ts = new_id("folder"), now_ms()
    with db.tx() as c:
        c.execute("INSERT INTO folders (id,name,created_at) VALUES (?,?,?)",
                  (fid, name[:120], ts))
    return {"id": fid, "name": name[:120], "created_at": ts, "conversation_count": 0}


def rename_folder(folder_id: str, name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("a folder needs a name")
    with db.tx() as c:
        cur = c.execute("UPDATE folders SET name = ? WHERE id = ?", (name[:120], folder_id))
        if cur.rowcount == 0:
            raise KeyError(folder_id)
    return {"id": folder_id, "name": name[:120]}


def delete_folder(folder_id: str) -> dict:
    """The folder goes; the conversations do not.

    `folder_id` is ON DELETE SET NULL, so they return to the top level. Deleting
    a container must never be a way to lose its contents by accident.
    """
    with db.tx() as c:
        cur = c.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        if cur.rowcount == 0:
            raise KeyError(folder_id)
    return {"id": folder_id, "deleted": True}


def move_conversation(conversation_id: str, folder_id: str | None) -> dict:
    if ephemeral.is_incognito(conversation_id):
        raise ValueError("an incognito conversation cannot be filed")
    with db.tx() as c:
        if folder_id and not c.execute("SELECT 1 FROM folders WHERE id = ?",
                                       (folder_id,)).fetchone():
            raise KeyError(folder_id)
        cur = c.execute("UPDATE conversations SET folder_id = ? WHERE id = ?",
                        (folder_id, conversation_id))
        if cur.rowcount == 0:
            raise KeyError(conversation_id)
    return {"id": conversation_id, "folder_id": folder_id}


def get_history(conversation_id: str) -> list[dict]:
    """CRS §3.3.3 — opening a conversation is a STATE READ, not a replay.

    This is the function that makes a single global cursor correct. History
    never comes from the event log, so a client may safely advance its cursor
    past events it was never shown.

    An incognito conversation reads from memory for the same reason: its
    history is state, not replay. It simply has nowhere durable to be.
    """
    if ephemeral.is_incognito(conversation_id):
        return ephemeral.history(conversation_id)

    rows = db.connect().execute(
        "SELECT t.id AS turn_id, t.status, t.error_code, t.error_message, t.error_retryable,"
        "       t.seq_in_conversation, m.role, m.text, m.partial, m.blocks, m.created_at"
        "  FROM turns t LEFT JOIN messages m ON m.turn_id = t.id"
        " WHERE t.conversation_id = ?"
        " ORDER BY t.seq_in_conversation, CASE m.role WHEN 'user' THEN 0 ELSE 1 END",
        (conversation_id,),
    )
    turns: dict[str, dict] = {}
    for r in rows:
        t = turns.setdefault(
            r["turn_id"],
            {
                "turn_id": r["turn_id"],
                "status": r["status"],
                "seq": r["seq_in_conversation"],
                "user_message": None,
                "assistant_message": None,
                "error": (
                    {"code": r["error_code"], "message": r["error_message"],
                     "retryable": bool(r["error_retryable"])}
                    if r["error_code"] else None
                ),
            },
        )
        if r["role"] is None:
            continue
        msg = {
            "text": r["text"],
            "partial": bool(r["partial"]),
            "blocks": json.loads(r["blocks"]) if r["blocks"] else [],
            "created_at": r["created_at"],
        }
        t["user_message" if r["role"] == "user" else "assistant_message"] = msg
    return sorted(turns.values(), key=lambda t: t["seq"])


# ── Turns ────────────────────────────────────────────────────────────────────
def status_of(turn_id: str) -> str | None:
    """The one place that answers "where is this turn", for either kind.

    Callers used to read `turns.status` directly, which silently returns None
    for a turn that legitimately has no row.
    """
    if ephemeral.has_turn(turn_id):
        record = ephemeral.turn(turn_id)
        return record["status"] if record else None
    row = db.connect().execute("SELECT status FROM turns WHERE id = ?", (turn_id,)).fetchone()
    return row["status"] if row else None


def conversation_of(turn_id: str) -> str | None:
    if ephemeral.has_turn(turn_id):
        record = ephemeral.turn(turn_id)
        return record["conversation_id"] if record else None
    row = db.connect().execute("SELECT conversation_id FROM turns WHERE id = ?",
                               (turn_id,)).fetchone()
    return row["conversation_id"] if row else None


def retry_turn(turn_id: str) -> dict:
    """CRS §5.2.3 — a retry creates a NEW turn referencing the failed one.

    It does not reopen the old turn. A terminal turn is a permanent record of
    what happened, and rewriting it would destroy the evidence of the failure
    the user is retrying.
    """
    if ephemeral.has_turn(turn_id):
        record = ephemeral.turn(turn_id)
        return create_turn(record["conversation_id"],
                           record["user_message"]["text"], retry_of=turn_id)

    row = db.connect().execute(
        "SELECT t.conversation_id, m.text FROM turns t"
        "  JOIN messages m ON m.turn_id = t.id AND m.role='user'"
        " WHERE t.id = ?", (turn_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown turn {turn_id}")
    return create_turn(row["conversation_id"], row["text"], retry_of=turn_id)


def create_turn(conversation_id: str, text: str, *,
                retry_of: str | None = None) -> dict:
    """Create a turn and return before any model work starts.

    The HTTP response carries a turn_id (§4.1) — which is the whole point.
    V1 returned {"status": "ok"} and nothing could ever refer to that work
    again, so cancellation and attribution were not merely unimplemented but
    unimplementable.
    """
    tid, mid, ts = new_id(TURN), new_id(MSG), now_ms()
    _observe_live(conversation_id, text, "user")

    if ephemeral.is_incognito(conversation_id):
        seq = ephemeral.next_seq(conversation_id)
        ephemeral.put_turn({
            "turn_id": tid, "conversation_id": conversation_id, "seq": seq,
            "status": "queued", "error": None, "assistant_message": None,
            "user_message": {"text": text, "partial": False, "blocks": [],
                             "created_at": ts},
        })
        bus.emit(
            "turn.created",
            {"turn": {"id": tid, "status": "queued", "seq": seq},
             "user_message": {"text": text, "created_at": ts}},
            conversation_id=conversation_id, turn_id=tid, incognito=True,
        )
        return {"turn_id": tid, "sequence": None, "status": "queued",
                "conversation_id": conversation_id, "text": text}

    pending: list[dict] = []
    with db.tx() as c:
        row = c.execute(
            "SELECT COALESCE(MAX(seq_in_conversation), 0) + 1 AS n FROM turns WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        seq_in_conv = row["n"]
        c.execute(
            "INSERT INTO turns (id,conversation_id,seq_in_conversation,status,created_at,retry_of_turn_id)"
            " VALUES (?,?,?,?,?,?)",
            (tid, conversation_id, seq_in_conv, "queued", ts, retry_of),
        )
        c.execute(
            "INSERT INTO messages (id,turn_id,role,text,created_at) VALUES (?,?,?,?,?)",
            (mid, tid, "user", text, ts),
        )
        c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conversation_id))
        pending.append(
            bus.emit(
                "turn.created",
                {
                    "turn": {"id": tid, "status": "queued", "seq": seq_in_conv},
                    "user_message": {"text": text, "created_at": ts},
                },
                conversation_id=conversation_id, turn_id=tid, conn=c,
            )
        )
    bus.deferred_fanout(pending)
    return {"turn_id": tid, "sequence": pending[0]["sequence"], "status": "queued",
            "conversation_id": conversation_id, "text": text}


def set_status(turn_id: str, status: str, *, detail: str | None = None) -> None:
    """CRS §5.2.1 — a status change and its event are one transaction."""
    if ephemeral.has_turn(turn_id):
        record = ephemeral.turn(turn_id)
        current = record["status"]
        if status == current:
            return
        # The same state machine, deliberately. An incognito turn that could
        # move in ways an ordinary one cannot would be a second lifecycle to
        # reason about, and the UI renders both with the same code.
        if status not in _LEGAL.get(current, set()):
            raise ValueError(f"illegal turn transition {current} -> {status} (CRS §5.2)")
        ephemeral.update_turn(turn_id, status=status)
        bus.emit("turn.status", {"status": status, **({"detail": detail} if detail else {})},
                 conversation_id=record["conversation_id"], turn_id=turn_id, incognito=True)
        return

    pending: list[dict] = []
    with db.tx() as c:
        row = c.execute("SELECT status, conversation_id FROM turns WHERE id = ?", (turn_id,)).fetchone()
        if row is None:
            return
        current = row["status"]
        if status == current:
            return
        if status not in _LEGAL.get(current, set()):
            raise ValueError(f"illegal turn transition {current} -> {status} (CRS §5.2)")

        completed_at = now_ms() if status in TERMINAL else None
        c.execute("UPDATE turns SET status = ?, completed_at = ? WHERE id = ?", (status, completed_at, turn_id))
        pending.append(
            bus.emit(
                "turn.status",
                {"status": status, **({"detail": detail} if detail else {})},
                conversation_id=row["conversation_id"], turn_id=turn_id, conn=c,
            )
        )
    bus.deferred_fanout(pending)


def _observe_live(conversation_id: str | None, text: str, role: str) -> None:
    """Feed the Live Conversation Graph.

    Incognito turns are observed too, and that is not an oversight: the live
    graph is in-memory only and dies with the conversation, so it never breaks
    incognito's actual guarantee (§11.2.1 — nothing reaches the disk). Skipping
    them would instead make the assistant forget what it just agreed to inside
    the very conversation it agreed in.

    Never allowed to break a turn. This is an ambient nicety; a regex that
    misbehaves on strange input must not cost the user their reply.
    """
    if not conversation_id or not text:
        return
    try:
        # Incognito graphs stay in memory and are never written: their messages
        # never reach the disk, so nothing derived from them may either.
        g = live.for_conversation(
            conversation_id, persistent=not ephemeral.is_incognito(conversation_id))
        g.observe_message(text, role=role, turn=len(g.turn_index))
        g.save()
    except Exception:  # pragma: no cover - defensive
        pass


def complete(turn_id: str, text: str, blocks: list | None = None, usage: dict | None = None) -> None:
    _observe_live(conversation_of(turn_id), text, "assistant")
    if ephemeral.has_turn(turn_id):
        record = ephemeral.turn(turn_id)
        if record["status"] in TERMINAL:
            return
        ephemeral.update_turn(
            turn_id, status="completed",
            assistant_message={"text": text, "partial": False,
                               "blocks": blocks or [], "created_at": now_ms()})
        bus.emit("turn.completed",
                 {"assistant_message": {"text": text, "blocks": blocks or []},
                  "usage": usage or {}},
                 conversation_id=record["conversation_id"], turn_id=turn_id,
                 incognito=True)
        return

    pending: list[dict] = []
    ts = now_ms()
    with db.tx() as c:
        row = c.execute("SELECT status, conversation_id FROM turns WHERE id = ?", (turn_id,)).fetchone()
        if row is None or row["status"] in TERMINAL:
            return
        c.execute("UPDATE turns SET status='completed', completed_at=? WHERE id=?", (ts, turn_id))
        c.execute(
            "INSERT INTO messages (id,turn_id,role,text,partial,blocks,usage,created_at)"
            " VALUES (?,?,'assistant',?,0,?,?,?)",
            (new_id(MSG), turn_id, text, json.dumps(blocks or []), json.dumps(usage or {}), ts),
        )
        pending.append(
            bus.emit(
                "turn.completed",
                {"assistant_message": {"text": text, "blocks": blocks or []}, "usage": usage or {}},
                conversation_id=row["conversation_id"], turn_id=turn_id, conn=c,
            )
        )
    bus.deferred_fanout(pending)


def fail(turn_id: str, code: str, message: str, retryable: bool, partial_text: str = "") -> None:
    """CRS §10.1 — a failure is `turn.failed`, never an assistant message.

    V1 broadcast provider errors as chat bubbles from "Primnox", which is how
    `error thinking: Expecting value: line 1 column 1 (char 0)` ended up
    rendered five times as though the assistant had said it.
    """
    if ephemeral.has_turn(turn_id):
        record = ephemeral.turn(turn_id)
        if record["status"] in TERMINAL:
            return
        fields: dict = {"status": "failed",
                        "error": {"code": code, "message": message,
                                  "retryable": retryable}}
        if partial_text:
            fields["assistant_message"] = {"text": partial_text, "partial": True,
                                           "blocks": [], "created_at": now_ms()}
        ephemeral.update_turn(turn_id, **fields)
        bus.emit("turn.failed", {"code": code, "message": message, "retryable": retryable},
                 conversation_id=record["conversation_id"], turn_id=turn_id,
                 incognito=True)
        return

    pending: list[dict] = []
    ts = now_ms()
    with db.tx() as c:
        row = c.execute("SELECT status, conversation_id FROM turns WHERE id = ?", (turn_id,)).fetchone()
        if row is None or row["status"] in TERMINAL:
            return
        c.execute(
            "UPDATE turns SET status='failed', error_code=?, error_message=?, error_retryable=?, completed_at=? WHERE id=?",
            (code, message, int(retryable), ts, turn_id),
        )
        if partial_text:
            c.execute(
                "INSERT INTO messages (id,turn_id,role,text,partial,created_at) VALUES (?,?,?,?,1,?)",
                (new_id(MSG), turn_id, "assistant", partial_text, ts),
            )
        pending.append(
            bus.emit(
                "turn.failed", {"code": code, "message": message, "retryable": retryable},
                conversation_id=row["conversation_id"], turn_id=turn_id, conn=c,
            )
        )
    bus.deferred_fanout(pending)


def cancel(turn_id: str) -> dict:
    """CRS §9.1 — idempotent, and immediate for a queued turn."""
    if ephemeral.has_turn(turn_id):
        record = ephemeral.turn(turn_id)
        if record["status"] in TERMINAL:
            return {"ok": True, "already": record["status"]}
        ephemeral.cancel_jobs_for_turn(turn_id)
        if record["status"] == "queued":
            ephemeral.update_turn(turn_id, status="cancelled")
            bus.emit("turn.cancelled", {"partial_text": ""},
                     conversation_id=record["conversation_id"], turn_id=turn_id,
                     incognito=True)
        return {"ok": True}

    pending: list[dict] = []
    with db.tx() as c:
        row = c.execute("SELECT status, conversation_id FROM turns WHERE id = ?", (turn_id,)).fetchone()
        if row is None:
            return {"ok": False, "reason": "unknown turn"}
        if row["status"] in TERMINAL:
            return {"ok": True, "already": row["status"]}       # §9.1.2

        c.execute(
            "UPDATE jobs SET cancel_requested = 1 WHERE turn_id = ? AND status IN ('queued','running')",
            (turn_id,),
        )
        if row["status"] == "queued":
            # §9.1.3 — never start the work at all.
            c.execute("UPDATE turns SET status='cancelled', completed_at=? WHERE id=?", (now_ms(), turn_id))
            c.execute(
                "UPDATE jobs SET status='cancelled', finished_at=? WHERE turn_id=? AND status='queued'",
                (now_ms(), turn_id),
            )
            pending.append(
                bus.emit("turn.cancelled", {"partial_text": ""},
                         conversation_id=row["conversation_id"], turn_id=turn_id, conn=c)
            )
    bus.deferred_fanout(pending)
    return {"ok": True}


def finish_cancelled(turn_id: str, partial_text: str) -> None:
    """CRS §9.3 — a cancelled turn KEEPS what it produced.

    Discarding it is prohibited: losing the half-written answer is the one
    thing a stop button must never do.
    """
    if ephemeral.has_turn(turn_id):
        record = ephemeral.turn(turn_id)
        if record["status"] in TERMINAL:
            return
        fields: dict = {"status": "cancelled"}
        if partial_text:
            fields["assistant_message"] = {"text": partial_text, "partial": True,
                                           "blocks": [], "created_at": now_ms()}
        ephemeral.update_turn(turn_id, **fields)
        bus.emit("turn.cancelled", {"partial_text": partial_text},
                 conversation_id=record["conversation_id"], turn_id=turn_id,
                 incognito=True)
        return

    pending: list[dict] = []
    ts = now_ms()
    with db.tx() as c:
        row = c.execute("SELECT status, conversation_id FROM turns WHERE id = ?", (turn_id,)).fetchone()
        if row is None or row["status"] in TERMINAL:
            return
        c.execute("UPDATE turns SET status='cancelled', completed_at=? WHERE id=?", (ts, turn_id))
        if partial_text:
            c.execute(
                "INSERT INTO messages (id,turn_id,role,text,partial,created_at) VALUES (?,?,?,?,1,?)",
                (new_id(MSG), turn_id, "assistant", partial_text, ts),
            )
        pending.append(
            bus.emit("turn.cancelled", {"partial_text": partial_text},
                     conversation_id=row["conversation_id"], turn_id=turn_id, conn=c)
        )
    bus.deferred_fanout(pending)


def cancel_requested(turn_id: str) -> bool:
    if ephemeral.has_turn(turn_id):
        return ephemeral.turn_cancel_requested(turn_id)
    row = db.connect().execute(
        "SELECT 1 FROM jobs WHERE turn_id = ? AND cancel_requested = 1 LIMIT 1", (turn_id,)
    ).fetchone()
    return row is not None


# `context_messages()` lived here and is gone. Context assembly belongs to the
# Context Service (`context/service.py`), which is the only place that knows
# about token budgets, asset references, and — the reason this copy had to go —
# that a turn cancelled before its first token must not leave its question in
# the history. Two implementations of "build the prompt" is one too many.
