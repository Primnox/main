"""The knowledge graph store.

Nodes and edges live in primnox.db alongside everything else, so a graph write
and its event commit together (CRS §4.1). That is the whole reason this mirrors
Graphify's output instead of querying `graphify-out/graph.json` over MCP.

Retrieval returns CITATIONS, not prose. A hit is `NODE label [src=file loc=L58]`
and the caller reads the file. For code that beats inlining source: file:line is
a cheap follow-up, and the model spends its budget on the answer rather than on
paragraphs it may not need.
"""
from __future__ import annotations

import json
import time
from collections import deque

from ..ids import EDGE, NODE, new_id
from ..storage import db

now_ms = lambda: int(time.time() * 1000)

GLOBAL = "*"

# Cheap and deliberate: the callers of this module budget in tokens, and a
# tokenizer dependency here would buy accuracy nobody spends.
def _tune(key):
    from ..settings import tunables
    return tunables.get(key)


# Deliberately the SAME tunable the context service estimates with. This module
# converts a token budget back into characters, and the context service converts
# the rendered block back into tokens — two halves of one sum. A local constant
# here read 4 while the context service read 3.5, so every block came out ~14%
# over the budget reserved for it, and an oversized retrieval block is not
# trimmed by the caller, it is dropped whole.


def _derive_type(node: dict) -> str:
    """Graphify emits no `type`; it emits shape flags. Map them.

    `_callable_class` before `_callable`: a class is callable in Python and
    carries both flags, so testing `_callable` first would file every class as
    a function.
    """
    if node.get("_callable_class"):
        return "class"
    if node.get("_callable"):
        return "function"
    file_type = node.get("file_type")
    if file_type == "rationale":
        return "rationale"
    if file_type == "document":
        return "section"
    if node.get("source_location") == "L1":
        return "file"
    return "entity"


# ── Writes ───────────────────────────────────────────────────────────────────
def upsert_node(
    conn,
    *,
    key: str,
    label: str,
    type: str,
    scope: str = GLOBAL,
    file_type: str | None = None,
    source_file: str | None = None,
    source_location: str | None = None,
    asset_id: str | None = None,
    workspace_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Insert or refresh one node; returns its internal id.

    Keyed on (scope, key) where `key` is Graphify's stable slug, which makes a
    re-import an update rather than a duplicate.
    """
    ts = now_ms()
    row = conn.execute(
        "SELECT id FROM knowledge_nodes WHERE scope=? AND key=?", (scope, key)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE knowledge_nodes SET label=?, type=?, file_type=?, source_file=?,"
            "       source_location=?, metadata=?, updated_at=? WHERE id=?",
            (label, type, file_type, source_file, source_location,
             json.dumps(metadata) if metadata else None, ts, row["id"]),
        )
        return row["id"]

    node_id = new_id(NODE)
    conn.execute(
        "INSERT INTO knowledge_nodes"
        " (id,label,key,type,file_type,source_file,source_location,scope,"
        "  asset_id,workspace_id,salience,metadata,created_at,updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?)",
        (node_id, label, key, type, file_type, source_file, source_location, scope,
         asset_id, workspace_id, json.dumps(metadata) if metadata else None, ts, ts),
    )
    return node_id


def upsert_edge(
    conn,
    *,
    source_id: str,
    target_id: str,
    relation: str,
    confidence: str,
    context: str = "",
    weight: float = 1.0,
    confidence_score: float | None = None,
    source_file: str | None = None,
    source_location: str | None = None,
    chunk_id: str | None = None,
) -> str | None:
    """Insert one edge, or strengthen the existing one. None if refused.

    A self-edge is dropped rather than raised: recursive functions produce them
    routinely and they carry no retrieval value, so failing the build over one
    would trade a whole graph for a node the walk already has.
    """
    if source_id == target_id:
        return None

    existing = conn.execute(
        "SELECT id, weight FROM knowledge_edges"
        " WHERE source_id=? AND target_id=? AND relation=? AND context=?",
        (source_id, target_id, relation, context),
    ).fetchone()
    if existing:
        # Repeated observation is evidence. Graphify emits one edge per call
        # site, so N calls from A to B should outrank a single mention.
        conn.execute(
            "UPDATE knowledge_edges SET weight=? WHERE id=?",
            (existing["weight"] + weight, existing["id"]),
        )
        return existing["id"]

    edge_id = new_id(EDGE)
    conn.execute(
        "INSERT INTO knowledge_edges"
        " (id,source_id,target_id,relation,context,confidence,confidence_score,"
        "  weight,source_file,source_location,chunk_id,created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (edge_id, source_id, target_id, relation, context, confidence,
         confidence_score, weight, source_file, source_location, chunk_id, now_ms()),
    )
    return edge_id


def clear_scope(conn, scope: str) -> int:
    """Drop a scope's nodes. Edges follow by cascade."""
    n = conn.execute("SELECT COUNT(*) AS c FROM knowledge_nodes WHERE scope=?",
                     (scope,)).fetchone()["c"]
    conn.execute("DELETE FROM knowledge_nodes WHERE scope=?", (scope,))
    return n


# ── Reads ────────────────────────────────────────────────────────────────────
def find_nodes(query: str, *, scope: str | None = None, limit: int | None = None) -> list[dict]:
    """Seed lookup: exact key, then label prefix, then substring.

    Ordered by tier so an exact hit is never buried under fuzzy ones, and by
    salience within a tier.
    """
    q = query.strip().lower()
    if not q:
        return []
    sql = (
        "SELECT *, CASE WHEN lower(key)=:q THEN 0"
        "              WHEN lower(label)=:q THEN 1"
        "              WHEN lower(label) LIKE :pre THEN 2"
        "              ELSE 3 END AS tier"
        "  FROM knowledge_nodes"
        " WHERE lower(key)=:q OR lower(label) LIKE :sub OR lower(key) LIKE :sub"
    )
    params: dict = {"q": q, "pre": f"{q}%", "sub": f"%{q}%"}
    if scope:
        sql += " AND scope=:scope"
        params["scope"] = scope
    sql += " ORDER BY tier, salience DESC, label LIMIT :limit"
    params["limit"] = limit or _tune("knowledge.seed_limit")
    return [dict(r) for r in db.connect().execute(sql, params)]


def neighbours(node_id: str, *, relation: str | None = None) -> list[dict]:
    """One hop, both directions, with the edge that got us there."""
    sql = (
        "SELECT e.relation, e.context, e.confidence, e.weight,"
        "       e.source_file AS edge_file, e.source_location AS edge_loc,"
        "       n.*, :nid AS from_id,"
        "       CASE WHEN e.source_id=:nid THEN 'out' ELSE 'in' END AS direction"
        "  FROM knowledge_edges e"
        "  JOIN knowledge_nodes n"
        "    ON n.id = CASE WHEN e.source_id=:nid THEN e.target_id ELSE e.source_id END"
        " WHERE e.source_id=:nid OR e.target_id=:nid"
    )
    params: dict = {"nid": node_id}
    if relation:
        sql += " AND e.relation=:rel"
        params["rel"] = relation
    sql += " ORDER BY e.weight DESC, n.label"
    return [dict(r) for r in db.connect().execute(sql, params)]


def walk(seeds: list[str], *, depth: int | None = None, limit: int | None = None,
         relation: str | None = None) -> tuple[list[dict], list[dict]]:
    """Breadth-first from seed node ids. Returns (nodes, edges).

    Breadth-first and not depth-first because the useful answer to "where is X
    used" is X's immediate surroundings; a deep path through one branch buries
    the direct callers under transitive ones.
    """
    depth = depth or _tune("knowledge.walk_depth")
    limit = limit or _tune("knowledge.walk_limit")
    conn = db.connect()
    seen: dict[str, dict] = {}
    edges: list[dict] = []
    edge_keys: set[tuple] = set()

    for sid in seeds:
        row = conn.execute("SELECT * FROM knowledge_nodes WHERE id=?", (sid,)).fetchone()
        if row:
            seen[sid] = dict(row) | {"hops": 0}

    frontier = deque((sid, 0) for sid in seen)
    while frontier and len(seen) < limit:
        nid, hops = frontier.popleft()
        if hops >= depth:
            continue
        for nb in neighbours(nid, relation=relation):
            key = (nid, nb["id"], nb["relation"], nb["context"])
            if key not in edge_keys:
                edge_keys.add(key)
                edges.append(nb)
            if nb["id"] not in seen:
                if len(seen) >= limit:
                    break
                seen[nb["id"]] = nb | {"hops": hops + 1}
                frontier.append((nb["id"], hops + 1))
    return list(seen.values()), edges


def render(nodes: list[dict], edges: list[dict], *, token_budget: int | None = None) -> str:
    """Format a subgraph as citation lines, trimmed to a token budget.

    Nodes first: they are the answer's anchors, and a truncation that ate them
    would leave edges referring to labels the model never saw.
    """
    token_budget = token_budget or _tune("knowledge.query_tokens")
    char_budget = max(200, int(token_budget * _tune("context.chars_per_token")))
    lines: list[str] = []
    for n in sorted(nodes, key=lambda x: (x.get("hops", 0), -x.get("weight", 0) or 0)):
        loc = f" loc={n['source_location']}" if n.get("source_location") else ""
        src = f" src={n['source_file']}" if n.get("source_file") else ""
        lines.append(f"NODE {n['label']} [{n['type']}{src}{loc}]")

    by_id = {n["id"]: n for n in nodes}
    for e in edges:
        other = by_id.get(e["id"])
        if other is None:
            continue
        origin = by_id.get(e["from_id"])
        a = origin["label"] if origin else e["from_id"]
        b = other["label"]
        if e.get("direction") == "in":
            a, b = b, a
        ctx = f" ctx={e['context']}" if e.get("context") else ""
        at = f" at={e['edge_file']}:{e['edge_loc']}" if e.get("edge_loc") else ""
        lines.append(f"EDGE {a} --{e['relation']} [{e['confidence']}{ctx}]--> {b}{at}")

    out = "\n".join(lines)
    if len(out) > char_budget:
        cut = out[:char_budget].rfind("\n")
        out = out[: cut if cut > 0 else char_budget] + "\n… (truncated to budget)"
    return out


def query(question: str, *, scope: str | None = None, depth: int = 2,
          token_budget: int | None = None, relation: str | None = None) -> str:
    """The retrieval entry point: question in, citation lines out."""
    seeds = find_nodes(question, scope=scope)
    if not seeds:
        for word in sorted(question.split(), key=len, reverse=True)[:3]:
            if len(word) > 3:
                seeds = find_nodes(word, scope=scope)
                if seeds:
                    break
    if not seeds:
        return ""
    nodes, edges = walk([s["id"] for s in seeds], depth=depth, relation=relation)
    return render(nodes, edges, token_budget=token_budget)


def stats(scope: str | None = None) -> dict:
    conn = db.connect()
    where, params = ("WHERE scope=?", (scope,)) if scope else ("", ())
    nodes = conn.execute(f"SELECT COUNT(*) AS c FROM knowledge_nodes {where}", params).fetchone()["c"]
    edges = conn.execute(
        "SELECT COUNT(*) AS c FROM knowledge_edges e"
        + (" JOIN knowledge_nodes n ON n.id=e.source_id WHERE n.scope=?" if scope else ""),
        params,
    ).fetchone()["c"]
    by_conf = {r["confidence"]: r["c"] for r in conn.execute(
        "SELECT confidence, COUNT(*) AS c FROM knowledge_edges GROUP BY confidence")}
    return {"nodes": nodes, "edges": edges, "by_confidence": by_conf}
