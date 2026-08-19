"""Load a Synthetic Life pack into a live Primnox database.

    python sdl/inject.py --pack memory-100 --db ./scratch.db
    python sdl/inject.py --pack office-500 --app-db --clear
    python sdl/inject.py --from ./sdl-out/office-500 --db ./scratch.db
    python sdl/inject.py --from ./sdl-out/office-500 --load both --db ./scratch.db

A destination is required. `--db` takes any file; `--app-db` names the real
store the app reads. There is no default — see the note in `main()`.

Generating a pack proves the generator works. Injecting one is what turns it
into a test of Primnox: the Memory tab, the facts graph and the context builder
all start reading a corpus with two years of history in it, including the
contradictions, instead of the handful of facts a manual session produces.

Two things this is careful about:

  Timestamps are the pack's, not now. A memory written in month 2 and the one
  that supersedes it in month 15 have to be fifteen months apart in the store,
  or "what does the user currently prefer" degenerates into whichever row was
  inserted last — and it would appear to work, because the insertion order
  happens to match.

  Provenance is always `imported`, whatever the pack's confidence says.
  Provenance answers "where did this come from", and for every row here the
  honest answer is "a synthetic pack" — nobody said any of it and no
  conversation inferred it.

  The graph is loaded under its own scope, `sdl:<pack>`. Primnox scopes a
  knowledge graph per asset or workspace, and dropping a synthetic corpus into
  the global scope would leave two years of fictional people permanently mixed
  into the user's real code graph with no way to tell them apart. A named scope
  is removable in one statement.

  This used to map confidence onto provenance: `stated` became `explicit` and
  `observed` became `inferred_chat`, on the reasoning that flattening them lost
  a distinction the corpus exists to test. Two things were wrong with that.

  The distinction was not being tested: nothing in the codebase ranks, filters
  or breaks ties on provenance. It is written on insert and read only by the
  graph and by the memory list. The tie-break that justified the mapping does
  not exist.

  And the cost was a lie told to the user's face. The memory list renders
  `explicit` as "you said" — so ninety-odd sentences about people who do not
  exist were being attributed to the user as their own statements, in the one
  screen whose entire job is to show what the system believes about them. If a
  stated-beats-observed rule is ever wanted, it needs a real confidence column;
  it must not be smuggled through the field that records who said a thing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdl import memory as memory_gen, packs, world as world_mod  # noqa: E402

# SDL confidence → Primnox provenance.
#
# Every value is `imported`, and the map is kept rather than deleted so the
# three confidences stay named at the point they are dropped — the pack still
# carries stated/observed/reported, and a future confidence column would be
# populated from here.
PROVENANCE = {
    memory_gen.STATED: "imported",
    memory_gen.OBSERVED: "imported",
    memory_gen.REPORTED: "imported",
}

# A month holds many memories and SQLite orders by the integer it is given, so
# they need to be spread rather than share one instant. 28 days keeps every
# offset inside the shortest month, so a memory can never drift into the next.
SPREAD_DAYS = 28


def database_path(override: str | None = None) -> Path:
    """Where the running app keeps its database.

    Mirrors `primnox2/app.py:47` deliberately rather than importing it: that
    module builds the FastAPI app at import time, and a CLI that spins up the
    whole server to learn a path is a CLI that fails when the server does.
    """
    if override:
        return Path(override)
    home = Path(os.getenv("PRIMNOX2_HOME", Path.home() / "Documents" / "Primnox2"))
    return home / "primnox.db"


def _timestamps(rows: list[dict], month_date) -> list[int]:
    """Epoch milliseconds for each memory, ordered inside its month."""
    position: dict[int, int] = {}
    counts: dict[int, int] = {}
    for row in rows:
        counts[row["month"]] = counts.get(row["month"], 0) + 1

    out: list[int] = []
    for row in rows:
        month = row["month"]
        index = position.get(month, 0)
        position[month] = index + 1
        start = datetime.combine(month_date(month), datetime.min.time(),
                                 tzinfo=timezone.utc)
        share = SPREAD_DAYS / max(1, counts[month])
        out.append(int((start.timestamp() + index * share * 86_400) * 1000))
    return out


def load(pack_name: str, from_dir: Path | None, seed: int) -> tuple[list[dict], object]:
    """The pack's memories, and the world they came from."""
    if from_dir:
        path = from_dir / "memory.jsonl"
        if not path.exists():
            raise SystemExit(f"no memory.jsonl in {from_dir} — run generate.py first")
        rows = [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]
        manifest = json.loads((from_dir / "manifest.json").read_text(encoding="utf-8"))
        pack = packs.get(manifest["pack"]["name"])
        world = world_mod.build(seed=manifest["seed"], months=pack.months,
                                people_count=pack.people,
                                project_count=pack.projects)
        return rows, world

    pack = packs.get(pack_name)
    world = world_mod.build(seed=seed, months=pack.months,
                            people_count=pack.people, project_count=pack.projects)
    return memory_gen.generate(world, volume=pack.memories), world


# SDL node type → the vocabulary `knowledge_nodes.type` actually permits.
#
# The column has a CHECK constraint listing eleven kinds, all of them shaped for
# a code graph or a conversation graph. A synthetic life has people, meetings and
# pull requests, and none of those are in the list.
#
# Mapped rather than added to. Widening the app's schema so a benchmark can load
# is the wrong direction: the corpus exists to test Primnox as it is, and a
# dataset that only fits after the product changes to accommodate it has stopped
# measuring the product. Nothing is lost either way — the true type is written to
# `metadata.sdl_type`, so "show me the people" stays answerable and the mapping
# is reversible.
NODE_TYPES = {
    "person": "entity", "organization": "entity", "project": "concept",
    "project_alias": "concept", "feature": "concept", "repository": "module",
    "symbol": "function", "document": "asset", "note": "asset",
    "email": "asset", "message": "asset", "photo": "asset",
    "meeting": "asset", "calendar_event": "asset", "series": "concept",
    "task": "decision", "todo": "decision", "issue": "decision",
    "pull_request": "decision", "commit": "entity", "dispute": "concept",
    "claim": "rationale",
}
FALLBACK_TYPE = "entity"


def load_graph(from_dir: Path, scope: str, batch: int = 20_000) -> dict:
    """Write a pack's nodes and edges into the knowledge tables.

    Goes through `graph.upsert_node` directly rather than through
    `knowledge.importer.import_extraction`. The importer is the Graphify seam
    and derives node type from Graphify's shape flags, which an SDL node does
    not carry — everything would land as `entity`, and "show me the people" would
    return commits. The seam is deliberately thin; this is a different source,
    so it gets its own loader rather than a flag inside that one.
    """
    from primnox2.knowledge import graph as kgraph
    from primnox2.storage import db

    path = from_dir / "graph.jsonl"
    if not path.exists():
        raise SystemExit(f"no graph.jsonl in {from_dir} — run generate.py first")

    nodes: list[dict] = []
    edges: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            (nodes if row.get("kind") == "node" else edges).append(row)

    stats = {"nodes": 0, "edges": 0, "self_edges_dropped": 0, "dangling": 0,
             "unmapped_types": sorted({n["type"] for n in nodes
                                       if n["type"] not in NODE_TYPES})}
    key_to_id: dict[str, str] = {}

    # Batched rather than one transaction for the whole pack. The importer's
    # all-or-nothing rule is right for a single extraction; the full pack is
    # 177,000 nodes and 380,000 edges, and holding that open blocks every other
    # writer for the duration. Nodes are committed before any edge is written,
    # so a batch that fails leaves edges missing — never edges pointing at
    # nodes that are not there.
    for start in range(0, len(nodes), batch):
        with db.tx() as conn:
            for node in nodes[start:start + batch]:
                extra = {k: v for k, v in node.items()
                         if k not in ("kind", "id", "label", "type")}
                extra["sdl_type"] = node["type"]
                key_to_id[node["id"]] = kgraph.upsert_node(
                    conn, key=node["id"], label=node["label"],
                    type=NODE_TYPES.get(node["type"], FALLBACK_TYPE), scope=scope,
                    source_file=extra.get("source_file"), metadata=extra)
                stats["nodes"] += 1

    for start in range(0, len(edges), batch):
        with db.tx() as conn:
            for edge in edges[start:start + batch]:
                src = key_to_id.get(edge["source"])
                dst = key_to_id.get(edge["target"])
                if not src or not dst:
                    stats["dangling"] += 1
                    continue
                written = kgraph.upsert_edge(
                    conn, source_id=src, target_id=dst,
                    relation=edge["relation"], confidence=edge["confidence"],
                    context=edge.get("inferred_from") or "",
                    source_file=edge.get("source_artifact"),
                    source_location=f"month {edge['month']}")
                if written is None:
                    stats["self_edges_dropped"] += 1
                else:
                    stats["edges"] += 1
    return stats


def main(argv=None) -> int:
    # Windows consoles default to cp1252, which cannot encode an em dash — the
    # script would print four lines of a corpus and then die on its own summary.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # pragma: no cover - a wrapped, non-reconfigurable stream
        pass

    ap = argparse.ArgumentParser(description="Inject an SDL pack into Primnox memory")
    ap.add_argument("--pack", default="memory-100")
    ap.add_argument("--from", dest="from_dir", help="a directory generate.py wrote")
    ap.add_argument("--db", help="database file to write to")
    ap.add_argument("--app-db", action="store_true",
                    help="write to the running app's own database. Say this "
                         "out loud; it used to be the default.")
    ap.add_argument("--seed", type=int, default=20260815)
    ap.add_argument("--clear", action="store_true",
                    help="forget existing memories first (soft delete, reversible)")
    ap.add_argument("--load", choices=("memory", "graph", "both"),
                    default="memory",
                    help="graph and both need --from (the graph is a file, not "
                         "something the generator can rebuild from a name alone)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.load in ("graph", "both") and not args.from_dir:
        raise SystemExit("--load graph needs --from <a directory generate.py wrote>")

    # A destination has to be chosen, never inherited.
    #
    # This defaulted to the app's own database. `python sdl/inject.py --pack
    # memory-100` — the exact line in this file's docstring, and the shortest
    # thing anyone would type — wrote a hundred fabricated sentences into the
    # real memory store, where they are indistinguishable from things the user
    # actually said. It happened here. Every row in the store was synthetic.
    #
    # The failure was not that the write was wrong, it was that it was silent
    # and implicit. Nothing was typed that named the target, so nothing could
    # have been mistyped; the default did all the damage on its own. A tool
    # that seeds fiction cannot treat the one database holding fact as the
    # place it goes when you say nothing.
    #
    # --db points anywhere. --app-db is the real store, and now costs a
    # deliberate sentence. Both are explicit, which is the whole fix.
    # `--dry-run` is exempt because it cannot write. Requiring a destination
    # from a command that opens nothing would only cost the cheap way to read
    # a pack before deciding where it goes.
    if args.db and args.app_db:
        raise SystemExit("--db and --app-db name different targets; pass one")
    if not args.db and not args.app_db and not args.dry_run:
        raise SystemExit(
            f"no destination.\n"
            f"  --db <path>   a scratch database of your own\n"
            f"  --app-db      the app's real store, at {database_path()}\n"
            f"                — synthetic rows land beside real memories there")

    rows, world = load(args.pack, Path(args.from_dir) if args.from_dir else None,
                       args.seed)
    rows = sorted(rows, key=lambda m: (m["month"], m["id"]))
    stamps = _timestamps(rows, world.month_date)

    payload = [{
        "text": row["text"],
        "category": row.get("category"),
        "provenance": PROVENANCE.get(row.get("confidence"), "imported"),
        "created_at": stamp,
    } for row, stamp in zip(rows, stamps)]

    db_path = database_path(args.db)
    label = args.from_dir or args.pack
    if args.dry_run:
        where = (str(db_path) if (args.db or args.app_db)
                 else "nowhere — no --db or --app-db given")
        print(f"dry run — {len(payload)} memories from {label} would go to {where}")
        for entry in payload[:5]:
            when = datetime.fromtimestamp(entry["created_at"] / 1000, timezone.utc)
            print(f"  {when:%Y-%m-%d}  [{entry['provenance']:<13}] {entry['text']}")
        print(f"  … and {max(0, len(payload) - 5)} more")
        return 0

    if not db_path.exists():
        raise SystemExit(f"no database at {db_path} — start Primnox once to create it")

    from primnox2.memory import service as memory
    from primnox2.storage import db

    db.configure(db_path)
    # Not db.init(): the schema belongs to the app, and running migrations from
    # a second process while the app holds the file open is how a database ends
    # up half-migrated. If the table is missing, the app has never booted here.
    if not db.connect().execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memories'"
    ).fetchone():
        raise SystemExit(f"{db_path} has no memories table — start Primnox once first")

    print(f"SDL → {db_path}")
    print(f"  pack {label}, {world.months} months")

    if args.load in ("memory", "both"):
        forgotten = memory.forget_all() if args.clear else 0
        result = memory.import_many(payload)
        if args.clear:
            print(f"  forgot {forgotten} existing")
        print(f"  stored {result['stored']}, suppressed "
              f"{result['duplicates']} duplicates")

        stats = memory.stats()
        by_cat = ", ".join(f"{k} {v}" for k, v in sorted(stats["by_category"].items()))
        print(f"  store now holds {stats['total']} ({by_cat})")

    if args.load in ("graph", "both"):
        source = Path(args.from_dir)
        scope = f"sdl:{source.name}"
        graph_stats = load_graph(source, scope)
        print(f"  graph scope {scope}: {graph_stats['nodes']} nodes, "
              f"{graph_stats['edges']} edges "
              f"({graph_stats['self_edges_dropped']} self-edges dropped, "
              f"{graph_stats['dangling']} dangling)")

    # What the app should say is true NOW. Printed so the Memory tab and the
    # `recall_memory` tool can be checked against the pack's own ground truth
    # rather than against whatever looks plausible on screen.
    current = memory_gen.current_preferences(rows)
    if current:
        print("  current preferences (ground truth):")
        for topic, entry in sorted(current.items()):
            print(f"     {topic:<10} month {entry['month']:>2}  {entry['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
