"""Permanent memory: store, search, forget.

Carried over from V1's `memory.py` in behaviour, re-homed into primnox.db so a
memory write and its event commit together.

Three of V1's decisions are kept because they were right, and one is dropped:

  KEPT  Soft delete. `deleted_at` rather than DELETE, so "forget that" is
        recoverable and a memory the user removed cannot come back through a
        re-import that no longer knows it was removed.
  KEPT  Duplicate suppression. A model told the same fact twice on consecutive
        turns should not produce two rows; V1 measured near-identical memories
        accumulating until the list was unreadable.
  KEPT  Provenance. Whether a fact was stated by the user or inferred by the
        model is the difference between "remember this" and "the model thought
        this", and the UI must be able to show which.
  DROPPED  V1's staleness decay, which silently hid memories after N days.
        A memory that vanishes on its own is indistinguishable from one the
        system never stored, and users cannot debug it. Forgetting is explicit.
"""
from __future__ import annotations

import re
import time

from ..ids import new_id
from ..kernel.events import bus
from ..storage import db

now_ms = lambda: int(time.time() * 1000)

MEM = "mem"

# What a memory may be filed under. Free-form categories become a mess nobody
# can filter, and these four cover what V1 actually accumulated.
CATEGORIES = ("personal", "work", "project", "session")
DEFAULT_CATEGORY = "personal"

# How a memory came to exist.
EXPLICIT, INFERRED, IMPORTED = "explicit", "inferred_chat", "imported"

# Two memories this similar are the same memory. Measured on V1's store: 0.85
# merged genuine restatements while keeping "I use Postgres" apart from "I use
# Postgres 16", which differ by one token but are different facts.
DUPLICATE_THRESHOLD = 0.85

_WORD = re.compile(r"[a-z0-9]+")


class MemoryTooLong(ValueError):
    """A memory longer than one fact. Its own type so the tool layer can turn
    it into advice the model can act on, rather than a generic failure."""


def _threshold() -> float:
    from ..settings import tunables
    return tunables.get('memory.duplicate_threshold')


def _max_chars() -> int:
    from ..settings import tunables
    return int(tunables.get('memory.max_chars'))


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _similarity(a: str, b: str) -> float:
    """Jaccard overlap on word sets.

    Deliberately not embeddings: this runs on every write, the store is small,
    and a local embedding call would put a model in the path of "remember this"
    — which then fails when the model is unavailable, for a feature that is
    supposed to be the reliable part.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ── Writes ───────────────────────────────────────────────────────────────────
def remember(text: str, *, category: str = DEFAULT_CATEGORY,
             provenance: str = EXPLICIT, conversation_id: str | None = None,
             turn_id: str | None = None) -> dict:
    """Store a fact. Returns {"id", "duplicate_of"} — duplicates are not stored.

    `conversation_id` and `turn_id` are ON DELETE SET NULL, not CASCADE: a fact
    the user asked to be remembered must outlive the conversation it was said
    in. Deleting a chat clears the attribution, not the memory.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("a memory needs text")

    # A memory is one fact, not a transcript. The context service injects the
    # whole store into every prompt and says so in its own comment — "small by
    # construction" — but nothing constructed it small, so a single pasted
    # paragraph spent the entire `context.memory_tokens` budget and clipped
    # every other fact out of the prompt. The user's real preferences went
    # missing to make room for one verbose one, invisibly.
    #
    # Rejected rather than truncated, deliberately. Cutting a fact at N
    # characters can reverse it — "Does not want the report sent to marketing"
    # becomes "Does not want the report sent" — and a memory that states the
    # opposite of the truth is worse than no memory at all. The caller is told
    # to distil instead, which is a thing a model can act on.
    limit = _max_chars()
    if len(text) > limit:
        raise MemoryTooLong(
            f"a memory must be one fact in {limit} characters or fewer; "
            f"this is {len(text)}. Distil it to a single standalone sentence.")

    if category not in CATEGORIES:
        category = DEFAULT_CATEGORY

    for existing in live():
        if _similarity(text, existing["text"]) >= _threshold():
            return {"id": existing["id"], "duplicate_of": existing["id"],
                    "stored": False}

    mem_id, ts = new_id(MEM), now_ms()
    pending = []
    with db.tx() as c:
        c.execute(
            "INSERT INTO memories (id,text,category,provenance,conversation_id,"
            "                      turn_id,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (mem_id, text, category, provenance, conversation_id, turn_id, ts, ts),
        )
        # §4.2 — the row and its event commit together. Announced only when
        # there is a conversation to announce it to: `memory.written` is a
        # conversation-scoped kind (§3.2), and a memory stored outside a chat
        # has no stream to reach. Incognito is the bus's decision, not this
        # call site's (§11.2), and the tool layer refuses that path anyway.
        #
        # Emitted on a real write only. A suppressed duplicate returns early
        # above, because "we already knew that" is not a memory being written
        # and a client rendering it as one would show the same fact twice.
        if conversation_id is not None:
            pending.append(bus.emit(
                "memory.written",
                {"memory_id": mem_id, "text": text, "category": category,
                 "provenance": provenance},
                conversation_id=conversation_id, turn_id=turn_id, conn=c,
            ))
    bus.deferred_fanout(pending)
    return {"id": mem_id, "duplicate_of": None, "stored": True}


def import_many(rows: list[dict], *, provenance: str = IMPORTED,
                conversation_id: str | None = None) -> dict:
    """Bulk-load a corpus, keeping each memory's own timestamp.

    `remember()` is the path for one fact learned in a conversation: it rescans
    the store on every call, and it stamps `created_at` with now. Both are wrong
    for a corpus. N writes become N full scans, and — the part that actually
    breaks something — a timeline collapses into a single instant. A store where
    every fact happened at the same moment cannot answer "which of these is
    current", and that question is usually the reason the corpus was loaded.

    Duplicate suppression is the same rule as `remember()`, applied against the
    live store AND against what this import has already accepted, so importing
    the same pack twice adds nothing the second time.

    Rows are `{"text", "category"?, "provenance"?, "created_at"?}`; `created_at`
    is epoch milliseconds.
    """
    threshold = _threshold()
    known: list[set[str]] = [_tokens(r["text"]) for r in live(limit=1_000_000)]

    def duplicate(tokens: set[str]) -> bool:
        if not tokens:
            return False
        for other in known:
            if not other:
                continue
            # Jaccard is bounded above by min/max of the two sizes, because the
            # intersection cannot exceed the smaller set nor the union the
            # larger. Sentences of very different lengths are therefore never
            # duplicates, and skipping them here is what keeps an import of a
            # few thousand facts from turning into a quadratic set-intersection.
            small, large = sorted((len(tokens), len(other)))
            if small / large < threshold:
                continue
            if len(tokens & other) / len(tokens | other) >= threshold:
                return True
        return False

    pending, duplicates = [], 0
    fallback = now_ms()
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        tokens = _tokens(text)
        if duplicate(tokens):
            duplicates += 1
            continue
        known.append(tokens)
        category = row.get("category")
        pending.append((
            new_id(MEM), text,
            category if category in CATEGORIES else DEFAULT_CATEGORY,
            row.get("provenance") or provenance,
            conversation_id, None,
            int(row.get("created_at") or fallback),
            int(row.get("created_at") or fallback),
        ))

    if pending:
        # One transaction for the whole import. Committing per row would leave a
        # half-loaded corpus behind on a failure, and a half-loaded corpus is
        # worse than none: its gaps look like retrieval misses.
        #
        # No `memory.written` here, unlike `remember()`. A corpus is an
        # out-of-band bulk load rather than something a turn just did, and one
        # event per row would put thousands of them through a log whose job is
        # closing a reconnect gap (§3.3). The store is read on open regardless.
        with db.tx() as c:
            c.executemany(
                "INSERT INTO memories (id,text,category,provenance,conversation_id,"
                "                      turn_id,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)", pending)

    return {"stored": len(pending), "duplicates": duplicates,
            "ids": [p[0] for p in pending]}


def forget(memory_id: str) -> bool:
    """Soft delete. The row stays so a re-import cannot resurrect it."""
    with db.tx() as c:
        cur = c.execute(
            "UPDATE memories SET deleted_at=?, updated_at=? WHERE id=? AND deleted_at IS NULL",
            (now_ms(), now_ms(), memory_id),
        )
        return cur.rowcount > 0


def restore(memory_id: str) -> bool:
    with db.tx() as c:
        cur = c.execute(
            "UPDATE memories SET deleted_at=NULL, updated_at=? WHERE id=?",
            (now_ms(), memory_id),
        )
        return cur.rowcount > 0


def update(memory_id: str, text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    with db.tx() as c:
        cur = c.execute("UPDATE memories SET text=?, updated_at=? WHERE id=?",
                        (text, now_ms(), memory_id))
        return cur.rowcount > 0


def forget_all() -> int:
    """Clear the store. Returns how many were forgotten."""
    with db.tx() as c:
        cur = c.execute("UPDATE memories SET deleted_at=?, updated_at=?"
                        " WHERE deleted_at IS NULL", (now_ms(), now_ms()))
        return cur.rowcount


# ── Reads ────────────────────────────────────────────────────────────────────
def live(category: str | None = None, limit: int = 500) -> list[dict]:
    sql = "SELECT * FROM memories WHERE deleted_at IS NULL"
    params: list = []
    if category:
        sql += " AND category=?"
        params.append(category)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in db.connect().execute(sql, params)]


def get(memory_id: str) -> dict | None:
    row = db.connect().execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
    return dict(row) if row else None


def search(query: str, limit: int = 20) -> list[dict]:
    """Rank by word overlap, then recency.

    Substring matching alone ranked a memory containing the query as a fragment
    of a longer word above an exact one; overlap puts the closest fact first.
    """
    query = (query or "").strip()
    if not query:
        return live(limit=limit)
    rows = live()
    scored = [(_similarity(query, r["text"]), r) for r in rows]
    hits = [r for score, r in sorted(scored, key=lambda p: -p[0]) if score > 0]
    if not hits:
        lowered = query.lower()
        hits = [r for r in rows if lowered in r["text"].lower()]
    return hits[:limit]


def stats() -> dict:
    conn = db.connect()
    by_cat = {r["category"] or "uncategorised": r["n"] for r in conn.execute(
        "SELECT category, COUNT(*) n FROM memories WHERE deleted_at IS NULL"
        " GROUP BY category")}
    total = conn.execute(
        "SELECT COUNT(*) n FROM memories WHERE deleted_at IS NULL").fetchone()["n"]
    forgotten = conn.execute(
        "SELECT COUNT(*) n FROM memories WHERE deleted_at IS NOT NULL").fetchone()["n"]
    return {"total": total, "forgotten": forgotten, "by_category": by_cat}


def render_for_prompt(limit: int = 40) -> str:
    """The block the context service injects. Empty string when there is none,
    so a user with no memories pays nothing for the feature."""
    rows = live(limit=limit)
    if not rows:
        return ""
    lines = "\n".join(f"- {r['text']}" for r in rows)
    return f"What you know about this user:\n{lines}"
