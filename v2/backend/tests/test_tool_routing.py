"""Which tool a question about the user is supposed to reach.

Two stores, two tools, and nothing wrong with either. `recall_memory` reads the
memories table; `graph_query` reads `knowledge_nodes`, which holds indexed code
and documents. They do not share a table and never did — `scope='facts'` has no
rows in the graph at all.

What was measured is that the model picked the wrong one. Asked what the user
prefers, it called `graph_query`, got back twenty-four lines of Primnox's own
source, and answered from them. The reply looked like recall.

That makes this a routing problem, and routing lives in two places a test can
actually reach: the sentences the model reads when choosing, and what comes
back when it chooses wrong. Both are asserted here, because the first one is
advice — it will sometimes be ignored — and the second is what has to hold when
it is.
"""
from __future__ import annotations

import pytest

from primnox2.tools import builtins  # noqa: F401  (registers the specs)
from primnox2.tools.registry import get


def _spec(name):
    spec = get(name)
    assert spec is not None, f"{name} is not registered"
    return spec


# ── the sentences the model routes on ────────────────────────────────────────
def test_each_tool_names_the_other():
    """Describing a tool by what it holds is not enough when the mistake being
    made is a choice between two. Each has to point at its sibling by name."""
    assert "graph_query" in _spec("recall_memory").description
    assert "recall_memory" in _spec("graph_query").description


def test_the_memory_tool_claims_first_person_questions():
    text = _spec("recall_memory").description.lower()
    assert "user" in text
    assert any(p in text for p in ("'i'", "'my'", "'me'"))


def test_the_graph_tool_disclaims_the_user():
    """It says what it is for loudly enough; what it lacked was a sentence
    saying what it is NOT for, which is the half that was being got wrong."""
    text = _spec("graph_query").description.lower()
    assert "code" in text
    assert "recall_memory" in text


# ── what comes back when the routing advice is ignored anyway ────────────────
@pytest.mark.parametrize("question", [
    "what do I prefer",
    "what did I say about the database",
    "my usual setup",
    "which editor do we use",
    "remind me what I decided",
])
def test_first_person_questions_are_recognised(question):
    assert builtins._about_the_user(question)


@pytest.mark.parametrize("question", [
    "how does ingest_bytes work",
    "what calls upsert_node",
    "mypy configuration",           # 'my' inside a word must not fire
    "the imports in service.py",    # 'i' inside a word must not fire
    "where is the scheduler defined",
])
def test_questions_about_code_are_left_alone(question):
    assert not builtins._about_the_user(question)


def test_a_personal_question_gets_the_warning_before_the_citations(monkeypatch):
    """Prepended, not appended. Two thousand tokens of graph output read first
    is two thousand tokens of an answer already forming — a caveat underneath
    arrives after the damage."""
    monkeypatch.setattr(builtins.knowledge, "query",
                        lambda *a, **k: "NODE permissions() [function src=x.py]")
    out = builtins._graph_query({"question": "what do I prefer"}, None)["output"]

    assert out.startswith("NOTE:")
    assert "recall_memory" in out
    assert out.index("NOTE:") < out.index("NODE permissions()")


def test_the_warning_does_not_withhold_the_result(monkeypatch):
    """The guess is keyword-shaped and will misfire — "why did I write this?"
    is a real question about code. Suppressing the answer would be the worse
    error, so the lines still come through underneath the caveat."""
    monkeypatch.setattr(builtins.knowledge, "query",
                        lambda *a, **k: "NODE ingest_bytes() [function src=y.py]")
    out = builtins._graph_query({"question": "why did I write ingest_bytes"}, None)["output"]
    assert "NODE ingest_bytes()" in out


def test_a_code_question_carries_no_warning(monkeypatch):
    """A caveat on every answer is a caveat on none of them."""
    monkeypatch.setattr(builtins.knowledge, "query",
                        lambda *a, **k: "NODE ingest_bytes() [function src=y.py]")
    out = builtins._graph_query({"question": "how does ingest_bytes work"}, None)["output"]
    assert "NOTE:" not in out


def test_an_empty_graph_answer_is_unchanged(monkeypatch):
    """Nothing matched is already the correcting outcome — the model tries
    something else. Wrapping it in a caveat about a result that does not exist
    would only make an honest miss look like a warning."""
    monkeypatch.setattr(builtins.knowledge, "query", lambda *a, **k: "")
    out = builtins._graph_query({"question": "what do I prefer"}, None)["output"]
    assert "NOTE:" not in out
