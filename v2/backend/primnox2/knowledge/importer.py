"""Graphify extraction -> primnox.db.

Graphify (Apache-2.0) does the extraction: tree-sitter AST parsing across ~25
languages, zero LLM calls. This module is the seam, and it is deliberately thin
— every temptation to "improve" an edge here is a temptation to diverge from a
benchmarked extractor.

Three properties of Graphify's output that a naive importer gets wrong, all
measured against this repo's own v2/backend (56 files, 971 nodes, 2133 edges):

  1. 184 edges point at nodes that were never emitted — `imports asyncio`,
     `imports os`. External modules are edge targets but not nodes. Dropping
     them loses the dependency graph, so they are materialised as `module`
     nodes instead.
  2. 20 (source, target, relation) triples repeat. They are distinct call
     SITES, not duplicates, so they accumulate weight rather than collide.
  3. Node ids are stable slugs, not uuids, so re-import is an upsert keyed on
     (scope, key) and an unchanged file costs nothing.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..storage import db
from . import graph

now_ms = lambda: int(time.time() * 1000)

# Graphify names the standard library and third-party packages as edge targets
# without emitting nodes for them. They become `module` nodes, keyed by name
# under the same scope, so "what does this depend on" stays answerable.
_IMPLICIT_TYPE = "module"


class ExtractionUnavailable(RuntimeError):
    """Graphify is not installed. Raised rather than silently degrading, because
    a knowledge graph that quietly contains nothing is worse than an error."""


def available() -> bool:
    try:
        import graphify.extract  # noqa: F401
        return True
    except Exception:
        return False


def extract(paths: list[Path], root: Path) -> dict:
    """Run Graphify over `paths`. Always passes `root` explicitly.

    ARCHITECTURE.md is emphatic about this: with `root` omitted, Graphify infers
    it from the common parent of the paths passed, so a single-file call anchors
    node ids to that file's own directory and the ids stop matching a later
    whole-tree run.
    """
    try:
        from graphify.extract import extract as _extract
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ExtractionUnavailable(
            "graphify is not installed. `pip install graphifyy`"
        ) from exc
    return _extract(paths, root=root)


def collect(target: Path) -> list[Path]:
    try:
        from graphify.extract import collect_files
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ExtractionUnavailable(
            "graphify is not installed. `pip install graphifyy`"
        ) from exc
    return collect_files(target)


def import_extraction(
    extraction: dict,
    *,
    scope: str,
    asset_id: str | None = None,
    workspace_id: str | None = None,
    replace: bool = True,
) -> dict:
    """Write one extraction into the knowledge tables.

    The whole import is one transaction: a half-imported graph would answer
    questions confidently and wrongly, which is worse than answering none.
    """
    raw_nodes = extraction.get("nodes") or []
    raw_edges = extraction.get("edges") or []

    stats = {"nodes": 0, "implicit_nodes": 0, "edges": 0,
             "self_edges_dropped": 0, "merged_edges": 0, "removed": 0}

    with db.tx() as conn:
        if replace:
            stats["removed"] = graph.clear_scope(conn, scope)

        key_to_id: dict[str, str] = {}
        for n in raw_nodes:
            key = n.get("id")
            if not key:
                continue
            key_to_id[key] = graph.upsert_node(
                conn,
                key=key,
                label=n.get("label") or key,
                type=graph._derive_type(n),
                scope=scope,
                file_type=n.get("file_type"),
                source_file=n.get("source_file"),
                source_location=n.get("source_location"),
                asset_id=asset_id,
                workspace_id=workspace_id,
            )
            stats["nodes"] += 1

        for e in raw_edges:
            src_key, tgt_key = e.get("source"), e.get("target")
            if not src_key or not tgt_key:
                continue

            for key in (src_key, tgt_key):
                if key not in key_to_id:
                    # An external module: a target with no node of its own.
                    key_to_id[key] = graph.upsert_node(
                        conn, key=key, label=key, type=_IMPLICIT_TYPE, scope=scope,
                        asset_id=asset_id, workspace_id=workspace_id,
                    )
                    stats["implicit_nodes"] += 1

            source_id, target_id = key_to_id[src_key], key_to_id[tgt_key]
            if source_id == target_id:
                stats["self_edges_dropped"] += 1
                continue

            before = conn.execute(
                "SELECT COUNT(*) AS c FROM knowledge_edges"
                " WHERE source_id=? AND target_id=? AND relation=? AND context=?",
                (source_id, target_id, e.get("relation") or "related",
                 e.get("context") or ""),
            ).fetchone()["c"]

            graph.upsert_edge(
                conn,
                source_id=source_id,
                target_id=target_id,
                relation=e.get("relation") or "related",
                context=e.get("context") or "",
                confidence=e.get("confidence") or "INFERRED",
                confidence_score=e.get("confidence_score"),
                weight=float(e.get("weight") or 1.0),
                source_file=e.get("source_file"),
                source_location=e.get("source_location"),
            )
            if before:
                stats["merged_edges"] += 1
            else:
                stats["edges"] += 1

    return stats


def import_tree(target: Path, *, scope: str, workspace_id: str | None = None) -> dict:
    """Extract a directory and import it. The whole-repo path."""
    target = Path(target).resolve()
    paths = collect(target)
    if not paths:
        return {"nodes": 0, "edges": 0, "files": 0}
    result = import_extraction(
        extract(paths, target), scope=scope, workspace_id=workspace_id
    )
    result["files"] = len(paths)
    return result
