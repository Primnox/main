"""Flowcharts, rendered by the same engine as everything else.

A model that draws a diagram emits a mermaid fence. Rendering it as a static
picture makes it a picture; running it through Graphify's exporter makes it the
same clickable, community-coloured, searchable thing as the knowledge graph —
so a diagram in a reply and the codebase behind it are read the same way.

WHY PARSE RATHER THAN SHIP MERMAID.JS. Mermaid renders a fixed drawing: no
neighbour highlighting, no search, no communities, and a 60-node flowchart is a
wall. Converting to nodes and edges costs this file and reuses a viewer that is
already built, already styled, and already handles graphs three orders of
magnitude larger.

WHAT IT UNDERSTANDS. mermaid `graph`/`flowchart` in any direction, the five node
shapes, edge labels, subgraphs, and the arrow forms models actually produce. It
does NOT understand sequence, class, state or gantt diagrams — those are not
graphs of the same shape, and pretending otherwise would draw something
confidently wrong.
"""
from __future__ import annotations

import re

# ```mermaid fences, and bare `graph TD` blocks for models that forget the tag.
FENCE = re.compile(r"```\s*mermaid\s*\n(.*?)```", re.S | re.I)
BARE = re.compile(r"^\s*(?:graph|flowchart)\s+(?:TD|TB|BT|LR|RL)\b.*", re.I | re.M)

_HEADER = re.compile(r"^\s*(?:graph|flowchart)\s+(TD|TB|BT|LR|RL)\s*$", re.I)

# Mermaid diagram types that are NOT node-and-edge graphs. Listed explicitly and
# refused, because the fallback that reads a bare identifier as a node happily
# turned the word `sequenceDiagram` into a one-node graph and drew it — a
# confident, wrong picture, which is worse than declining.
_OTHER_DIAGRAM = re.compile(
    r"^\s*(sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|journey"
    r"|gantt|pie|gitGraph|mindmap|timeline|quadrantChart|requirementDiagram"
    r"|C4Context|sankey(?:-beta)?|xychart(?:-beta)?|block(?:-beta)?)",
    re.I | re.M)
_SUBGRAPH = re.compile(r"^\s*subgraph\s+(.+?)\s*$", re.I)
_END = re.compile(r"^\s*end\s*$", re.I)

# `A[Label] -->|note| B{Other}` and every arrow variant in between. The label
# groups are optional because a bare `A --> B` is by far the most common line a
# model writes.
_SHAPES = r"(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|\(\([^)]*\)\)|\[\[[^\]]*\]\]|>[^\]]*\])"
_NODE = rf"([A-Za-z0-9_.\-]+)\s*({_SHAPES})?"
_ARROW = r"(-{1,3}>|-{2,3}|={2,3}>|-\.->|\.->|--x|--o)"
_EDGE = re.compile(rf"{_NODE}\s*{_ARROW}\s*(?:\|([^|]*)\|)?\s*{_NODE}")

# Shape carries meaning in mermaid: a diamond is a decision, a stadium is a
# terminus. Kept as the node type so the viewer can colour by role rather than
# by cluster alone.
_SHAPE_TYPE = {
    "[": "function",     # process
    "(": "entity",       # rounded / terminus
    "{": "concept",      # decision
    ">": "section",      # flag
}


def _label(raw: str | None, fallback: str) -> tuple[str, str]:
    """Strip a shape wrapper, returning (text, node type)."""
    if not raw:
        return fallback, "entity"
    kind = _SHAPE_TYPE.get(raw[0], "entity")
    text = raw.strip("[](){}>").strip().strip('"').strip("'")
    return (text or fallback), kind


def extract_blocks(text: str) -> list[str]:
    """Every mermaid graph in a message, fenced or bare."""
    blocks = [m.group(1) for m in FENCE.finditer(text or "")]
    if blocks:
        return [b for b in blocks if _HEADER.search(b) or _EDGE.search(b)]
    # A bare block runs to the first blank line; models that omit the fence
    # almost always still put the diagram in its own paragraph.
    out = []
    for match in BARE.finditer(text or ""):
        chunk = (text or "")[match.start():]
        out.append(chunk.split("\n\n")[0])
    return out


def parse(source: str) -> dict:
    """One mermaid block -> the extraction dict Graphify's build() consumes."""
    if _OTHER_DIAGRAM.search(source or ""):
        return {"nodes": [], "edges": [], "direction": "TD"}

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    direction = "TD"
    group: list[str] = []

    def touch(node_id: str, raw: str | None) -> str:
        label, kind = _label(raw, node_id)
        existing = nodes.get(node_id)
        if existing is None:
            nodes[node_id] = {
                "id": node_id, "label": label, "file_type": kind,
                "source_file": " / ".join(group) if group else "",
                "source_location": "",
            }
        elif raw:
            # A later line that carries the shape wins: mermaid commonly
            # declares `A --> B` first and gives B its label further down.
            existing["label"], existing["file_type"] = label, kind
        return node_id

    for line in (source or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        header = _HEADER.match(stripped)
        if header:
            direction = header.group(1).upper()
            continue
        sub = _SUBGRAPH.match(stripped)
        if sub:
            group.append(sub.group(1).strip().strip('"[]'))
            continue
        if _END.match(stripped):
            if group:
                group.pop()
            continue

        matched = False
        for m in _EDGE.finditer(stripped):
            src, src_shape, arrow, label, dst, dst_shape = m.groups()
            a, b = touch(src, src_shape), touch(dst, dst_shape)
            if a == b:
                continue          # a self-loop adds nothing the node lacks
            edges.append({
                "source": a, "target": b,
                "relation": (label or "").strip() or "flows_to",
                # Everything in a diagram was stated by whoever drew it — there
                # is no inference here, so EXTRACTED is the honest label.
                "confidence": "EXTRACTED",
                "context": "flowchart", "weight": 1.0,
                "source_file": " / ".join(group) if group else "",
                "source_location": "",
            })
            matched = True
        if matched:
            continue

        # A standalone declaration: `A[Start]` with no edge on the line.
        lone = re.match(rf"^{_NODE}\s*$", stripped)
        if lone:
            touch(lone.group(1), lone.group(2))

    return {"nodes": list(nodes.values()), "edges": edges, "direction": direction}


def render_html(source: str, *, node_limit: int | None = None) -> str | None:
    """A mermaid block as an interactive Graphify page, or None if it is not a
    graph we understand."""
    parsed = parse(source)
    # An edge is what makes it a graph. A block that produced only loose nodes
    # is either a diagram type this does not understand or a fragment, and
    # rendering scattered dots with nothing between them tells a reader less
    # than the source they already had.
    if not parsed["nodes"] or not parsed["edges"]:
        return None

    from graphify.build import build_from_json
    from graphify.cluster import cluster
    from graphify.export import to_html

    graph = build_from_json({"nodes": parsed["nodes"], "edges": parsed["edges"]})
    if graph.number_of_nodes() == 0:
        return None

    import tempfile
    from pathlib import Path

    communities = cluster(graph)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "flowchart.html"
        to_html(graph, communities, str(target), node_limit=node_limit)
        return target.read_text(encoding="utf-8")
