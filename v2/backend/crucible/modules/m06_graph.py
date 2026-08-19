"""Module 6 — Graph Torture.

Imports 50,000 nodes and 120,000 edges — including contradictory assertions
about the same pair — and then asks the graph to answer under that load.

WHY THIS IS THE HARDEST MODULE. Everything else degrades gracefully under scale;
a graph gets slower non-linearly and then stops being useful. The failure that
matters is not a crash, it is a query that takes eight seconds on the critical
path of every reply because retrieval now runs automatically.
"""
from __future__ import annotations

import time

from primnox2.knowledge import graph as knowledge
from primnox2.knowledge import importer
from primnox2.storage import db

from ..generate import graph_extraction
from ..scoring import CRITICAL, HIGH, MEDIUM, ModuleResult

KEY, NAME = "M06", "Graph Torture"
SCOPE = "crucible-scale"

# Retrieval runs on every turn now, so this is a user-visible latency budget,
# not a benchmark curiosity.
QUERY_BUDGET_S = 0.75
IMPORT_BUDGET_S = 240.0


def run(ctx) -> ModuleResult:
    result = ModuleResult(key=KEY, name=NAME)
    started = time.perf_counter()

    if not importer.available():
        result.skip("graphify is not installed; the extractor cannot be exercised")
        return result

    nodes = ctx.scale("graph_nodes", 50_000)
    edges = ctx.scale("graph_edges", 120_000)
    extraction = graph_extraction(nodes=nodes, edges=edges, seed=ctx.seed)

    import_start = time.perf_counter()
    stats = importer.import_extraction(extraction, scope=SCOPE)
    import_s = time.perf_counter() - import_start

    conn = db.connect()
    stored_nodes = conn.execute(
        "SELECT COUNT(*) n FROM knowledge_nodes WHERE scope=?", (SCOPE,)).fetchone()["n"]
    stored_edges = conn.execute(
        "SELECT COUNT(*) n FROM knowledge_edges e JOIN knowledge_nodes k"
        " ON k.id=e.source_id WHERE k.scope=?", (SCOPE,)).fetchone()["n"]

    # Contradictions must SURVIVE, not be silently reconciled. A graph that
    # drops one side of a disagreement has decided something it cannot know.
    contradictions = conn.execute(
        "SELECT COUNT(*) n FROM knowledge_edges WHERE relation='excludes'").fetchone()["n"]

    timings = []
    for probe in ("PaymentGateway_100", "LedgerService", "RiskEngine_4200", "n012345"):
        t0 = time.perf_counter()
        out = knowledge.query(probe, scope=SCOPE, token_budget=400)
        timings.append((probe, time.perf_counter() - t0, len(out)))
    slowest = max(t for _, t, _ in timings)
    answered = sum(1 for _, _, n in timings if n > 0)

    result.measurements = {
        "nodes_requested": nodes, "edges_requested": edges,
        "nodes_stored": stored_nodes, "edges_stored": stored_edges,
        "self_edges_dropped": stats.get("self_edges_dropped"),
        "merged_edges": stats.get("merged_edges"),
        "contradictions_kept": contradictions,
        "import_seconds": round(import_s, 1),
        "import_nodes_per_s": round(stored_nodes / import_s, 1) if import_s else None,
        "query_seconds_slowest": round(slowest, 3),
        "queries_answered": f"{answered}/{len(timings)}",
        "query_detail": [{"probe": p, "seconds": round(t, 3), "chars": n}
                         for p, t, n in timings],
    }

    if slowest > QUERY_BUDGET_S:
        result.find(
            title=f"Graph query takes {slowest:.2f}s at {stored_nodes:,} nodes",
            severity=CRITICAL if slowest > 3 else HIGH,
            owner="Knowledge Service",
            what_happened=(
                f"The slowest probe took {slowest:.2f}s against a {QUERY_BUDGET_S}s "
                f"budget. Retrieval now runs automatically on EVERY turn, so this "
                f"is added to time-to-first-token for every message the user "
                f"sends, whether or not the graph had anything to contribute."),
            reproduction=(
                f"crucible.generate.graph_extraction(nodes={nodes}, edges={edges}); "
                f"importer.import_extraction(...); time knowledge.query(probe)."),
            probable_cause=(
                "`find_nodes` uses LIKE '%term%' with leading wildcards, which "
                "cannot use an index, so every probe is a full scan of "
                f"{stored_nodes:,} rows. `walk()` then issues one neighbours() "
                "query per frontier node — N+1 against the same table."),
            suggested_fix=(
                "Two changes, neither exotic: (1) an FTS5 virtual table over "
                "label and key, so seeding is an index hit instead of a scan; "
                "(2) fetch the whole frontier in one query with "
                "`WHERE source_id IN (...)` rather than looping. If latency "
                "still exceeds budget, make automatic retrieval time-boxed — a "
                "reply with no graph context beats a reply that arrives late."),
            evidence=str(result.measurements["query_detail"]),
        )

    if import_s > IMPORT_BUDGET_S:
        result.find(
            title=f"Import of {edges:,} edges takes {import_s:.0f}s",
            severity=MEDIUM, owner="Knowledge Service",
            what_happened="Indexing a large repository blocks its job for minutes.",
            reproduction="Time importer.import_extraction on the generated extraction.",
            probable_cause=("upsert_edge issues a SELECT then an INSERT per edge — "
                            "two statements per row inside one transaction."),
            suggested_fix=("executemany with INSERT ... ON CONFLICT DO UPDATE, "
                           "so the round-trip per edge disappears."),
        )

    if contradictions == 0:
        result.find(
            title="Contradictory edges were not preserved",
            severity=HIGH, owner="Knowledge Service",
            what_happened=("Both sides of a deliberate disagreement were expected; "
                           "none survived the import."),
            reproduction="Import the generated extraction; count relation='excludes'.",
            probable_cause="The uniqueness key collapses opposing relations.",
            suggested_fix=("Keep relation in the key and let confidence carry the "
                           "disagreement; AMBIGUOUS exists for exactly this."),
        )

    lost = stats.get("nodes", 0) + stats.get("implicit_nodes", 0) - stored_nodes
    if lost:
        result.find(
            title=f"{lost} nodes reported imported but not stored",
            severity=CRITICAL, owner="Knowledge Service",
            what_happened="The import statistics disagree with the table.",
            reproduction="Compare import_extraction() counts with a COUNT(*).",
            probable_cause="Counting attempts rather than successful writes.",
            suggested_fix="Derive the statistics from the table after commit.",
        )

    result.score(
        correctness=10 if (stored_nodes and answered == len(timings)) else 5,
        consistency=10 if contradictions else 5,
        recovery=10,
        performance=(10 if slowest < 0.25 else 7 if slowest < QUERY_BUDGET_S
                     else 3 if slowest < 3 else 0),
        ux_stability=10 if slowest < QUERY_BUDGET_S else 3,
    )
    result.duration_s = time.perf_counter() - started
    return result
