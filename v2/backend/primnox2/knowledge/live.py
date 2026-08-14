"""The Conversation Graph.

Ours, not Graphify's. Graphify indexes files; this indexes a conversation — the
entities named, the decisions taken, the files touched, the tools run. It
answers "go back to the third architecture option" and "reuse the API we chose
earlier" without re-reading the transcript, which is what gives a small model
long-horizon coherence.

It is held in memory while a chat is active and SAVED alongside it, because the
chat itself is saved: a graph that died with the process would leave `recall`
returning nothing for every conversation the user did not have in the last few
minutes, which is most of them.

Persisting it does not make it a second memory system, and the distinction is
worth being exact about:

  - It is DERIVED. Every node is a cache over messages that are themselves still
    on disk, so it can be dropped and rebuilt. A schema change deletes it rather
    than migrating it.
  - It is SCOPED. Rows are keyed `conv:<id>` with a conversation_id foreign key,
    so a conversation and what was inferred from it are deleted by one cascade
    and neither can outlive the other.
  - It is NOT PROMOTED. Nothing here reaches global Memory on its own. That
    stays an explicit act, which is what keeps a wrong inference made in passing
    from becoming a fact about the user.

Incognito conversations are the exception and stay memory-only: their messages
never reach the disk (§11.2.1), so nothing derived from them may either.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict

from ..ids import EDGE, NODE, new_id
from ..storage import db

now_ms = lambda: int(time.time() * 1000)


def scope_for(conversation_id: str) -> str:
    return f"conv:{conversation_id}"

# Kinds a live node can take. Deliberately few: this is a working set, not an
# ontology, and every kind here has to earn a query someone actually makes.
ENTITY, DECISION, FILE, TOOL, ASSET = "entity", "decision", "file", "tool", "asset"

# A conversation's graph is capped. An unbounded one turns a long chat into a
# slow memory leak, and the tail of a conversation is where the useful entities
# are anyway.
MAX_NODES = 400

_lock = threading.RLock()
_graphs: dict[str, "LiveGraph"] = {}

# Capitalised multi-word names, CamelCase identifiers, snake_case, dotted paths,
# and backtick spans. Deterministic — no model call to maintain a working set.
_CAMEL = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")
_BACKTICK = re.compile(r"`([^`\n]{2,60})`")
_PATHLIKE = re.compile(r"\b[\w./\\-]+\.(?:py|ts|tsx|js|jsx|sql|md|json|yaml|yml|rs|go)\b")
# The body is "any non-terminator, OR a terminator glued to a non-space". A
# plain [^.!?\n] run ends at the first period, which truncates the moment a
# decision names a file or a version — "put it in storage/db.py" was recorded as
# "put it in storage/db", losing the extension from the one token that mattered.
_DECISION = re.compile(
    r"(?:^|[.!?]\s+)((?:we|let's|i'?ll|going to|decided to|use|pick|choose|go with)\b"
    r"(?:[^.!?\n]|[.!?](?=\S)){6,160})",
    re.IGNORECASE,
)


class LiveGraph:
    """One conversation's working set."""

    def __init__(self, conversation_id: str, *, persistent: bool = True):
        self.conversation_id = conversation_id
        self.persistent = persistent
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.turn_index: dict[int, list[str]] = defaultdict(list)
        self.created_at = now_ms()
        self.dirty = False

    # ── writes ──────────────────────────────────────────────────────────────
    def note(self, label: str, kind: str, *, turn: int = 0, detail: str = "") -> str | None:
        key = f"{kind}:{label.strip().lower()}"
        if not label.strip():
            return None
        node = self.nodes.get(key)
        if node:
            node["mentions"] += 1
            node["last_turn"] = turn
            if detail and not node["detail"]:
                node["detail"] = detail
        else:
            if len(self.nodes) >= MAX_NODES:
                self._evict()
            self.nodes[key] = {
                "key": key, "label": label.strip(), "kind": kind, "detail": detail,
                "mentions": 1, "first_turn": turn, "last_turn": turn,
            }
        if key not in self.turn_index[turn]:
            self.turn_index[turn].append(key)
        self.dirty = True
        return key

    def link(self, a: str, b: str, relation: str) -> None:
        if a and b and a != b:
            self.edges.append({"source": a, "target": b, "relation": relation})
            self.dirty = True

    def _evict(self) -> None:
        """Drop the least-mentioned, oldest node. Decisions are never evicted —
        they are the thing "go back to the third option" needs to still exist."""
        candidates = [n for n in self.nodes.values() if n["kind"] != DECISION]
        if not candidates:
            candidates = list(self.nodes.values())
        victim = min(candidates, key=lambda n: (n["mentions"], n["last_turn"]))
        self.nodes.pop(victim["key"], None)
        self.edges = [e for e in self.edges
                      if e["source"] != victim["key"] and e["target"] != victim["key"]]

    # ── observation ─────────────────────────────────────────────────────────
    def observe_message(self, text: str, *, role: str, turn: int) -> None:
        """Harvest entities and decisions from one message. Deterministic."""
        if not text:
            return
        found: list[str] = []
        for m in _CAMEL.findall(text):
            k = self.note(m, ENTITY, turn=turn)
            if k:
                found.append(k)
        for m in _BACKTICK.findall(text):
            k = self.note(m, ENTITY, turn=turn)
            if k:
                found.append(k)
        for m in _PATHLIKE.findall(text):
            k = self.note(m, FILE, turn=turn)
            if k:
                found.append(k)

        # Decisions come from the assistant's own commitments and the user's
        # instructions; harvesting them from quoted material would record
        # choices nobody made.
        if role in ("user", "assistant"):
            for m in _DECISION.findall(text):
                self.note(m.strip()[:160], DECISION, turn=turn, detail=role)

        # Entities named in the same message are related by co-occurrence. Weak
        # by design — it is a working set, not a claim about the world.
        for i, a in enumerate(found[:12]):
            for b in found[i + 1:12]:
                self.link(a, b, "co_occurs")

    def observe_tool(self, name: str, summary: str, *, turn: int) -> None:
        self.note(name, TOOL, turn=turn, detail=summary[:200])

    def observe_asset(self, name: str, *, turn: int) -> None:
        self.note(name, ASSET, turn=turn)

    # ── reads ───────────────────────────────────────────────────────────────
    def decisions(self) -> list[dict]:
        return sorted((n for n in self.nodes.values() if n["kind"] == DECISION),
                      key=lambda n: n["first_turn"])

    def recall(self, query: str, *, limit: int = 10) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return []
        hits = [n for n in self.nodes.values()
                if q in n["label"].lower() or q in (n["detail"] or "").lower()]
        return sorted(hits, key=lambda n: (-n["mentions"], -n["last_turn"]))[:limit]

    # ── persistence ─────────────────────────────────────────────────────────
    def save(self) -> bool:
        """Write this graph to primnox.db. No-op for incognito or when clean.

        Rewrites the scope wholesale rather than diffing: the graph is small
        (capped at MAX_NODES) and derived, so a replace is both cheaper to write
        and impossible to get subtly wrong.
        """
        if not self.persistent or not self.dirty:
            return False
        scope = scope_for(self.conversation_id)
        ts = now_ms()
        with db.tx() as c:
            c.execute("DELETE FROM knowledge_nodes WHERE scope=?", (scope,))
            key_to_id: dict[str, str] = {}
            for key, n in self.nodes.items():
                nid = new_id(NODE)
                key_to_id[key] = nid
                c.execute(
                    "INSERT INTO knowledge_nodes"
                    " (id,label,key,type,scope,conversation_id,salience,metadata,"
                    "  created_at,updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (nid, n["label"], key, n["kind"], scope, self.conversation_id,
                     float(n["mentions"]),
                     json.dumps({"detail": n["detail"], "first_turn": n["first_turn"],
                                 "last_turn": n["last_turn"]}),
                     ts, ts),
                )
            seen: set[tuple] = set()
            for e in self.edges:
                a, b = key_to_id.get(e["source"]), key_to_id.get(e["target"])
                if not a or not b or a == b or (a, b, e["relation"]) in seen:
                    continue
                seen.add((a, b, e["relation"]))
                c.execute(
                    "INSERT INTO knowledge_edges"
                    " (id,source_id,target_id,relation,context,confidence,weight,created_at)"
                    " VALUES (?,?,?,?,'','INFERRED',1.0,?)",
                    (new_id(EDGE), a, b, e["relation"], ts),
                )
        self.dirty = False
        return True

    def load(self) -> bool:
        """Restore from primnox.db. Returns False if nothing was saved."""
        scope = scope_for(self.conversation_id)
        rows = db.connect().execute(
            "SELECT * FROM knowledge_nodes WHERE scope=?", (scope,)).fetchall()
        if not rows:
            return False
        id_to_key: dict[str, str] = {}
        for r in rows:
            meta = json.loads(r["metadata"] or "{}")
            id_to_key[r["id"]] = r["key"]
            self.nodes[r["key"]] = {
                "key": r["key"], "label": r["label"], "kind": r["type"],
                "detail": meta.get("detail", ""), "mentions": int(r["salience"] or 1),
                "first_turn": meta.get("first_turn", 0),
                "last_turn": meta.get("last_turn", 0),
            }
        edge_rows = db.connect().execute(
            "SELECT e.source_id, e.target_id, e.relation FROM knowledge_edges e"
            "  JOIN knowledge_nodes n ON n.id = e.source_id WHERE n.scope=?",
            (scope,)).fetchall()
        for r in edge_rows:
            a, b = id_to_key.get(r["source_id"]), id_to_key.get(r["target_id"])
            if a and b:
                self.edges.append({"source": a, "target": b, "relation": r["relation"]})
        # Turn numbering continues from what was restored, so a reopened chat
        # does not start renumbering its turns from zero.
        for n in self.nodes.values():
            self.turn_index[n["last_turn"]].append(n["key"])
        self.dirty = False
        return True

    def render(self, *, limit: int = 30) -> str:
        """A compact block for the context builder."""
        if not self.nodes:
            return ""
        lines: list[str] = []
        dec = self.decisions()
        if dec:
            lines.append("Decisions so far:")
            for i, d in enumerate(dec[:10], 1):
                lines.append(f"  {i}. {d['label']}")
        ents = sorted((n for n in self.nodes.values() if n["kind"] != DECISION),
                      key=lambda n: (-n["mentions"], -n["last_turn"]))[:limit]
        if ents:
            lines.append("In play:")
            for n in ents:
                # 'x' rather than '×': this string reaches a Windows console,
                # which is cp1252 by default and renders the multiplication
                # sign as a replacement char.
                lines.append(f"  {n['label']} ({n['kind']}, x{n['mentions']})")
        return "\n".join(lines)


# ── module surface ───────────────────────────────────────────────────────────
def for_conversation(conversation_id: str, *, persistent: bool = True) -> LiveGraph:
    """Get a conversation's graph, restoring it from disk on first touch.

    The load happens here rather than at boot so reopening one old chat does not
    mean paying for every chat the user has ever had.
    """
    with _lock:
        g = _graphs.get(conversation_id)
        if g is None:
            g = LiveGraph(conversation_id, persistent=persistent)
            if persistent:
                try:
                    g.load()
                except Exception:  # pragma: no cover - a cache must not block a chat
                    pass
            _graphs[conversation_id] = g
        return g


def save(conversation_id: str) -> bool:
    with _lock:
        g = _graphs.get(conversation_id)
    return g.save() if g else False


def evict(conversation_id: str) -> bool:
    """Drop from memory, keeping what is on disk. For closing a chat."""
    with _lock:
        g = _graphs.pop(conversation_id, None)
    if g is None:
        return False
    try:
        g.save()
    except Exception:  # pragma: no cover - defensive
        pass
    return True


def drop(conversation_id: str) -> bool:
    """Forget entirely, memory and disk. For deleting a chat.

    The database rows would also go by cascade when the conversation row is
    deleted; this covers incognito, where there is no conversation row to
    cascade from, and makes the intent explicit at the call site.
    """
    with _lock:
        existed = _graphs.pop(conversation_id, None) is not None
    try:
        with db.tx() as c:
            cur = c.execute("DELETE FROM knowledge_nodes WHERE scope=?",
                            (scope_for(conversation_id),))
            existed = existed or cur.rowcount > 0
    except Exception:  # pragma: no cover - defensive
        pass
    return existed


def drop_all() -> None:
    """In-memory only. Used by tests between cases."""
    with _lock:
        _graphs.clear()


def active() -> list[str]:
    with _lock:
        return list(_graphs)
