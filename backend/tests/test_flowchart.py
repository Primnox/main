"""Mermaid flowcharts rendered through Graphify's viewer.

The parser is the risk. A diagram it half-understands draws something
confidently wrong, which is worse than refusing — so the tests that matter are
the ones asserting it declines cleanly.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from primnox2.app import app
from primnox2.knowledge import flowchart

SIMPLE = """graph TD
  A[Start] --> B{Indexed?}
  B -->|yes| C[Query graph]
  B -->|no| D[Read file]
  C --> E((Answer))
  D --> E
"""


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ── parsing ──────────────────────────────────────────────────────────────────
def test_nodes_edges_and_labels_survive():
    p = flowchart.parse(SIMPLE)
    assert {n["id"] for n in p["nodes"]} == {"A", "B", "C", "D", "E"}
    assert len(p["edges"]) == 5
    assert {e["relation"] for e in p["edges"]} >= {"yes", "no", "flows_to"}


def test_shape_becomes_node_type():
    """A diamond is a decision and a stadium is a terminus. Dropping the shape
    would throw away the only role information the diagram carries."""
    by_id = {n["id"]: n for n in flowchart.parse(SIMPLE)["nodes"]}
    assert by_id["B"]["file_type"] == "concept"     # {decision}
    assert by_id["A"]["file_type"] == "function"    # [process]
    assert by_id["E"]["file_type"] == "entity"      # ((terminus))


def test_a_label_declared_after_its_first_use_still_lands():
    """Mermaid commonly writes `A --> B` first and labels B further down."""
    p = flowchart.parse("graph LR\n  A --> B\n  B[Named Later]\n")
    assert {n["id"]: n["label"] for n in p["nodes"]}["B"] == "Named Later"


def test_subgraphs_become_grouping():
    p = flowchart.parse(
        "graph TD\n  subgraph Retrieval\n    C[Query] --> D[Read]\n  end\n")
    assert all(n["source_file"] == "Retrieval" for n in p["nodes"])


def test_direction_is_read():
    assert flowchart.parse("flowchart LR\n A-->B\n")["direction"] == "LR"


def test_self_loops_are_dropped():
    """A node pointing at itself adds nothing the node does not already carry."""
    assert flowchart.parse("graph TD\n A --> A\n")["edges"] == []


def test_comments_and_blank_lines_are_ignored():
    p = flowchart.parse("graph TD\n  %% a comment\n\n  A --> B\n")
    assert len(p["edges"]) == 1


# ── extraction from a message ────────────────────────────────────────────────
def test_a_fenced_block_is_found_in_a_reply():
    message = f"Here is the flow:\n\n```mermaid\n{SIMPLE}```\n\nDone."
    assert len(flowchart.extract_blocks(message)) == 1


def test_an_unfenced_diagram_is_still_found():
    """Small models forget the language tag constantly."""
    message = f"The flow:\n\n{SIMPLE}\nThat is it."
    assert flowchart.extract_blocks(message)


def test_prose_yields_nothing():
    assert flowchart.extract_blocks("Just a paragraph about graphs and flows.") == []


# ── refusing what it does not understand ─────────────────────────────────────
def test_a_sequence_diagram_is_refused_rather_than_guessed():
    """Not a graph of this shape. Drawing it as one would be confidently wrong."""
    source = ("sequenceDiagram\n  Alice->>Bob: Hello\n  Bob-->>Alice: Hi\n")
    assert flowchart.render_html(source) is None


def test_empty_input_is_refused():
    assert flowchart.render_html("") is None
    assert flowchart.render_html("graph TD\n") is None


# ── rendering ────────────────────────────────────────────────────────────────
def test_render_produces_a_self_contained_page():
    html = flowchart.render_html(SIMPLE)
    assert html and len(html) > 5_000
    assert "<script" in html and "http://cdn" not in html


def test_flowchart_endpoint_renders(client):
    r = client.post("/knowledge/flowchart", json={"source": SIMPLE})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert len(r.text) > 5_000


def test_flowchart_endpoint_is_honest_about_what_it_cannot_draw(client):
    r = client.post("/knowledge/flowchart",
                    json={"source": "sequenceDiagram\n  A->>B: hi\n"})
    assert r.status_code == 422
