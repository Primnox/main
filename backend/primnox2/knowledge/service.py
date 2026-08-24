"""Knowledge Service job wiring.

`memory.graph_build` rather than a new `graph.*` namespace: the jobs.kind CHECK
constraint enumerates its namespaces, SQLite cannot alter a CHECK in place, and
rebuilding the jobs table to gain a word is a bad trade. The graph IS the memory
system, so the name is honest rather than a workaround.

Indexing runs as a background job so the user keeps chatting while it happens —
the reason the whole design puts extraction before the question instead of
inside it.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..kernel import scheduler
from ..kernel.events import bus
from ..storage import db
from . import facts, importer

now_ms = lambda: int(time.time() * 1000)

KIND = "memory.graph_build"


def request_build(target: Path | str, *, scope: str, workspace_id: str | None = None,
                  conversation_id: str | None = None, asset_id: str | None = None) -> str:
    """Queue an index build. Returns the job id."""
    return scheduler.enqueue(
        None,
        KIND,
        {"target": str(target), "scope": scope, "workspace_id": workspace_id,
         "conversation_id": conversation_id, "asset_id": asset_id},
        # Idempotent: the import replaces its scope wholesale, so running it
        # twice lands on the same graph. That is what makes an interrupted
        # build safe to retry on the boot sweep instead of failing the job.
        idempotent=True,
        max_attempts=2,
        priority=-5,   # never ahead of a reply the user is waiting for
    )


def _run_build(sched, job: dict) -> None:
    payload = json.loads(job["payload"])
    target = Path(payload["target"])
    scope = payload["scope"]
    conversation_id = payload.get("conversation_id")

    emit_scope = ({"conversation_id": conversation_id} if conversation_id
                  else {"scope": "ambient"})

    if not target.exists():
        sched._finish(job["id"], "failed", error=f"{target} does not exist")
        return
    if not importer.available():
        # Explicit, not silent. An empty graph that answers "no matches" to
        # every question looks like a working index with an empty corpus.
        sched._finish(job["id"], "failed",
                      error="graphify is not installed (pip install graphifyy)")
        return

    bus.emit("job.started",
             {"job_id": job["id"], "kind": KIND, "label": f"Indexing {target.name}"},
             **emit_scope)

    try:
        result = importer.import_tree(
            target, scope=scope, workspace_id=payload.get("workspace_id"),
            asset_id=payload.get("asset_id"))
    except Exception as exc:
        sched._finish(job["id"], "failed", error=f"{type(exc).__name__}: {exc}")
        return

    sched._finish(job["id"], "completed", result=result)
    bus.emit("knowledge.indexed",
             {"scope": scope, "target": str(target), **result}, **emit_scope)


scheduler.register(KIND, _run_build)


def scope_for_workspace(workspace_id: str) -> str:
    return f"ws:{workspace_id}"


def scope_for_asset(asset_id: str) -> str:
    return f"asset:{asset_id}"


def indexed_scopes() -> list[dict]:
    return [dict(r) for r in db.connect().execute(
        "SELECT scope, COUNT(*) AS nodes, MAX(updated_at) AS updated_at"
        "  FROM knowledge_nodes GROUP BY scope ORDER BY updated_at DESC")]


# ── Visualisation ────────────────────────────────────────────────────────────
# Graphify already ships a viewer: `export.to_html` writes a self-contained,
# clustered, clickable page. Rebuilding that as a React component would mean
# reimplementing community colouring, node sizing and search against a graph
# library we do not maintain, to arrive somewhere behind where upstream already
# is. This reads our tables, hands them to Graphify's own build/cluster/export
# chain, and serves the result.

def _to_networkx(scope: str):
    """Our rows -> the extraction dict Graphify's build() consumes.

    Going through `build_from_json` rather than constructing a DiGraph by hand
    keeps every attribute the exporter expects — community, degree, direction —
    produced by the same code that produces them for a normal graphify run.
    """
    from graphify.build import build_from_json

    conn = db.connect()
    nodes = conn.execute(
        "SELECT id, key, label, type, source_file, source_location"
        "  FROM knowledge_nodes WHERE scope=?", (scope,)).fetchall()
    if not nodes:
        return None

    by_id = {r["id"]: r["key"] for r in nodes}
    edges = conn.execute(
        "SELECT e.source_id, e.target_id, e.relation, e.context, e.confidence,"
        "       e.weight, e.source_file, e.source_location"
        "  FROM knowledge_edges e"
        "  JOIN knowledge_nodes n ON n.id = e.source_id"
        " WHERE n.scope=?", (scope,)).fetchall()

    extraction = {
        "nodes": [{"id": r["key"], "label": r["label"],
                   "file_type": r["type"],
                   "source_file": r["source_file"] or "",
                   "source_location": r["source_location"] or ""} for r in nodes],
        "edges": [{"source": by_id[r["source_id"]], "target": by_id[r["target_id"]],
                   "relation": r["relation"], "context": r["context"] or None,
                   "confidence": r["confidence"], "weight": r["weight"],
                   "source_file": r["source_file"] or "",
                   "source_location": r["source_location"] or ""}
                  for r in edges
                  if r["source_id"] in by_id and r["target_id"] in by_id],
    }
    return build_from_json(extraction)


# Above roughly this many nodes a force-directed graph stops being a picture of
# anything — it is a hairball, and the honest response to "show me the graph" is
# the most connected part of it rather than all of it. Graphify's exporter takes
# the cap; the value lives in `knowledge.view_node_limit`, which is what both
# render paths below actually read. Callers who want everything can ask for it.


def render_html(scope: str, *, node_limit: int | None = -1) -> str | None:
    """Graphify's own viewer for one scope, as a self-contained HTML string.

    `node_limit=-1` means "whatever the tunable says" — distinct from None,
    which means "no limit, render everything".
    """
    import tempfile
    from pathlib import Path

    if node_limit == -1:
        from ..settings import tunables
        node_limit = tunables.get("knowledge.view_node_limit") or None
    graph = _to_networkx(scope)
    if graph is None or graph.number_of_nodes() == 0:
        return None

    from graphify.cluster import cluster
    from graphify.export import to_html

    communities = cluster(graph)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "graph.html"
        to_html(graph, communities, str(target), node_limit=node_limit)
        return target.read_text(encoding="utf-8")


def graph_json(scope: str) -> dict:
    """Nodes and edges as plain JSON, for callers that want to draw it
    themselves rather than embed the shipped viewer."""
    # `facts` is derived on read and never reaches knowledge_nodes, so the plain
    # table query below returns nothing for it. `scopes()` still advertises it
    # with a node count, so without this branch the two endpoints contradict
    # each other and a caller that trusts the listing draws an empty canvas.
    if scope == facts.SCOPE:
        built = facts.build()
        return {"scope": scope,
                "nodes": [{"id": n["id"], "key": n["id"], "label": n["label"],
                           "type": n["file_type"], "source_file": n["source_file"],
                           "source_location": "", "salience": 1.0}
                          for n in built["nodes"]],
                "edges": [{"source_id": e["source"], "target_id": e["target"],
                           "relation": e["relation"], "context": e["context"],
                           "confidence": e["confidence"], "weight": e["weight"]}
                          for e in built["edges"]]}

    conn = db.connect()
    nodes = [dict(r) for r in conn.execute(
        "SELECT id, key, label, type, source_file, source_location, salience"
        "  FROM knowledge_nodes WHERE scope=?", (scope,))]
    ids = {n["id"] for n in nodes}
    edges = [dict(r) for r in conn.execute(
        "SELECT e.source_id, e.target_id, e.relation, e.context, e.confidence, e.weight"
        "  FROM knowledge_edges e JOIN knowledge_nodes n ON n.id=e.source_id"
        " WHERE n.scope=?", (scope,))]
    return {"scope": scope, "nodes": nodes,
            "edges": [e for e in edges
                      if e["source_id"] in ids and e["target_id"] in ids]}
