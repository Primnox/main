"""The graph of what Primnox knows about YOU.

This is the one a user should see. The knowledge graph proper indexes a corpus
you point it at — a repository, a folder of documents — and is a developer's
view of a codebase. Opening the app on that was a product error: it showed
`_startup()` calling `_warm_sandbox()`, which is Primnox's own plumbing and
tells the user nothing about their own material.

What belongs here is what was SAVED:

  fact          a permanent memory — "I prefer concise answers"
  decision      something settled in a conversation — "we'll use WAL mode"
  entity        a thing that keeps coming up across chats
  document      a file you uploaded
  conversation  the chat a fact came from, as the hub that ties them together

Derived on read rather than stored. The inputs — memories, conversation graphs,
assets — are already tables, and a fourth copy of them would be a cache that can
disagree with all three. The whole thing is small by construction: a user with
ten thousand memories has a different problem.
"""
from __future__ import annotations

from ..storage import db

SCOPE = "facts"

# An entity mentioned in one chat and never again is noise, not knowledge. Two
# is the point where it starts describing the user rather than a passing remark.
def _min_mentions() -> int:
    from ..settings import tunables
    return tunables.get("facts.min_mentions")


MIN_MENTIONS = 2   # default; the live value comes from _min_mentions()


def _shorten(label: str, limit: int = 58) -> str:
    """Trim to a word boundary. A label cut mid-word reads as corrupted data
    rather than as an abbreviation."""
    label = " ".join(label.split())
    if len(label) <= limit:
        return label
    cut = label[:limit].rsplit(" ", 1)[0]
    return (cut or label[:limit]) + "…"


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in db.connect().execute(sql, params)]


def build() -> dict:
    """Everything saved, as one extraction dict Graphify's build() consumes."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(key: str, label: str, kind: str, detail: str = "") -> str:
        if key not in nodes:
            nodes[key] = {
                "id": key,
                # Long memories are a sentence, not a name. Truncated for the
                # canvas; the full text is in the Memory tab, which is where
                # someone reading a fact in full should be sent anyway.
                "label": _shorten(label),
                "file_type": kind, "source_file": detail, "source_location": "",
            }
        return key

    def edge(a: str, b: str, relation: str, confidence: str = "EXTRACTED") -> None:
        if a != b:
            edges.append({"source": a, "target": b, "relation": relation,
                          "confidence": confidence, "weight": 1.0,
                          "context": "facts", "source_file": "", "source_location": ""})

    # ── conversations, as hubs ────────────────────────────────────────────
    titles = {c["id"]: c["title"] for c in _rows(
        "SELECT id, title FROM conversations WHERE archived_at IS NULL")}

    # ── permanent memories ────────────────────────────────────────────────
    for m in _rows("SELECT id, text, category, provenance, conversation_id"
                   "  FROM memories WHERE deleted_at IS NULL"):
        category = m["category"] or "personal"
        fact = node(f"fact:{m['id']}", m["text"], "fact", category)
        if m["conversation_id"] in titles:
            chat = node(f"conv:{m['conversation_id']}",
                        titles[m["conversation_id"]], "conversation")
            edge(fact, chat, "remembered_in")
        else:
            # Not every memory comes from a chat: one typed into the Memory
            # panel has no conversation, and an imported corpus has none at all.
            # Without this they are drawn as unconnected dots — a hundred of
            # them turns the canvas into confetti and hides the part that has
            # structure. Category is a relationship the row already carries, so
            # this groups them without inventing a source they never had.
            edge(fact, node(f"category:{category}", category, "category"),
                 "filed_under")

    # ── what conversations established ────────────────────────────────────
    # Node types come from the conversation graph, which already separates a
    # decision from a passing mention. Entities are pooled by label across
    # chats: "PaymentGateway" discussed in four conversations is ONE thing that
    # keeps coming up, and drawing it four times hides exactly that.
    seen_entities: dict[str, list[str]] = {}
    for row in _rows(
            "SELECT n.label, n.type, n.scope, n.salience"
            "  FROM knowledge_nodes n"
            " WHERE n.scope LIKE 'conv:%' AND n.type IN ('decision','entity','file','tool')"):
        cid = row["scope"].split(":", 1)[1]
        if cid not in titles:
            continue
        chat = node(f"conv:{cid}", titles[cid], "conversation")

        if row["type"] == "decision":
            # Keyed on the whole text so two chats settling the same thing
            # are one node, and the near-duplicates a model produces when it
            # restates a decision do not each get their own dot.
            decision = node(f"decision:{row['label'].strip().lower()}",
                            row["label"], "decision")
            edge(decision, chat, "decided_in")
        else:
            seen_entities.setdefault(row["label"], []).append(cid)

    min_mentions = _min_mentions()
    for label, conversations in seen_entities.items():
        if len(conversations) < min_mentions:
            continue
        entity = node(f"entity:{label}", label, "entity",
                      f"{len(conversations)} conversations")
        for cid in conversations:
            edge(entity, node(f"conv:{cid}", titles[cid], "conversation"),
                 "discussed_in")

    # ── documents ─────────────────────────────────────────────────────────
    # Keyed by NAME, not asset id. Content addressing means two uploads of a
    # changed `sales.xlsx` are two assets, and drawing both put the same
    # filename on the canvas twice with nothing to tell them apart — the reader
    # sees a duplicate, not a version.
    #
    # And only documents that reached a conversation. An asset with no chat
    # behind it is a file in a folder: it has no relationship to anything, and a
    # graph of disconnected dots is a worse list than a list.
    for a in _rows("SELECT id, original_name, kind FROM assets WHERE status='ready'"):
        chats = [t["conversation_id"] for t in _rows(
            "SELECT DISTINCT t.conversation_id"
            "  FROM turn_assets ta JOIN turns t ON t.id = ta.turn_id"
            " WHERE ta.asset_id=?", (a["id"],))
            if t["conversation_id"] in titles]
        if not chats:
            continue
        doc = node(f"doc:{a['original_name']}", a["original_name"],
                   "document", a["kind"])
        for cid in chats:
            edge(doc, node(f"conv:{cid}", titles[cid], "conversation"), "shared_in")

    # A conversation with nothing attached to it is a chat, not knowledge.
    # Dropping the empties keeps the canvas about what was learned.
    connected = {e["source"] for e in edges} | {e["target"] for e in edges}
    nodes = {k: v for k, v in nodes.items()
             if k in connected or not k.startswith("conv:")}

    return {"nodes": list(nodes.values()), "edges": edges}


def stats() -> dict:
    graph = build()
    by_kind: dict[str, int] = {}
    for n in graph["nodes"]:
        by_kind[n["file_type"]] = by_kind.get(n["file_type"], 0) + 1
    return {"nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
            "by_kind": by_kind}


def render_html(node_limit: int | None = None) -> str | None:
    graph_data = build()
    if not graph_data["nodes"]:
        return None

    from graphify.build import build_from_json
    from graphify.cluster import cluster
    from graphify.export import to_html

    graph = build_from_json(graph_data)
    if graph.number_of_nodes() == 0:
        return None

    import tempfile
    from pathlib import Path

    communities = cluster(graph)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "facts.html"
        to_html(graph, communities, str(target), node_limit=node_limit)
        return target.read_text(encoding="utf-8")
