"""Declared tunables, and the constants that used to shadow them.

The bug this file exists for: `knowledge/graph.py` held its own
`CHARS_PER_TOKEN = 4` while `context/service.py` estimated with the declared
`context.chars_per_token`, default 3.5. Those two numbers are opposite halves
of one sum — the context service reserves a budget in tokens, the graph
renderer spends it in characters — so every rendered block came out ~14% over
the budget computed for it. And an oversized retrieval block is not trimmed by
the caller; it is skipped whole. The graph would silently vanish from the
prompt, which is the one context source the whole retrieval design rests on.
"""
from __future__ import annotations

import pytest

from primnox2.context import service as context
from primnox2.knowledge import facts, graph
from primnox2.settings import models, tunables
from primnox2.skills import loader
from primnox2.tools import builtins, runtime

# Every accessor added when a bare constant was routed through the registry,
# with the default it must resolve to. `tunables.get` raises KeyError on an
# unknown key, so calling each one catches a mistyped key name outright — the
# failure mode that would otherwise surface as a crash on a live turn.
ACCESSORS = [
    (facts._min_mentions,        "facts.min_mentions"),
    (runtime.max_tool_steps,     "tools.max_steps"),
    (builtins._inline_chars,     "tools.inline_output_chars"),
    (loader._max_asset_chars,    "skills.max_asset_chars"),
    (models._discovery_timeout,  "models.discovery_timeout_s"),
]


@pytest.mark.parametrize("accessor,key", ACCESSORS, ids=[k for _, k in ACCESSORS])
def test_each_accessor_resolves_to_its_declared_default(accessor, key, fresh_db):
    assert key in tunables.REGISTRY, f"{key} is read but never declared"
    assert accessor() == tunables.REGISTRY[key].default


def _fat_graph(count: int = 60) -> tuple[list[dict], list[dict]]:
    """Enough nodes that any sane budget truncates. Edges are left empty: the
    node lines alone prove the budget arithmetic, and rendering edges would
    make the overflow depend on edge formatting too."""
    nodes = [
        {"id": f"n{i}", "label": f"some_module_{i}.function_name_{i}",
         "type": "function", "source_file": f"pkg/module_{i}.py",
         "source_location": f"L{i}", "hops": 0, "weight": 1.0}
        for i in range(count)
    ]
    return nodes, []


def test_a_rendered_graph_block_fits_the_budget_reserved_for_it(fresh_db):
    """The invariant that was broken: what the renderer produces for N tokens
    must still measure as N tokens to the service that reserved them."""
    budget = 500
    rendered = graph.render(*_fat_graph(), token_budget=budget)

    assert "truncated to budget" in rendered, \
        "nothing was truncated, so the budget was never exercised"

    # Slack covers only the truncation marker the renderer appends after
    # cutting — a fixed ~25 characters, not a percentage. The regression this
    # guards was 14% of the budget, which at 500 tokens is 71.
    assert context.estimate_tokens(rendered) <= budget + 10, (
        f"rendered {context.estimate_tokens(rendered)} tokens for a "
        f"{budget}-token budget; the renderer and the estimator disagree"
    )


def test_both_halves_of_the_estimate_move_together(fresh_db):
    """Changing the setting must move the renderer too. While the renderer held
    its own constant, this knob moved only the reserving half — so raising it
    made the overshoot worse rather than fixing it."""
    budget = 500
    nodes, edges = _fat_graph()

    tunables.set_many({"context.chars_per_token": 3.0})
    tunables.invalidate()
    tight = graph.render(nodes, edges, token_budget=budget)

    tunables.set_many({"context.chars_per_token": 6.0})
    tunables.invalidate()
    loose = graph.render(nodes, edges, token_budget=budget)

    assert len(loose) > len(tight), (
        "the renderer ignored context.chars_per_token — it is reading a "
        "constant of its own again"
    )


def test_a_stored_tunable_changes_real_behaviour(fresh_db):
    """Resolution is not the point; effect is. Tool output is clipped before
    the model sees it, so the stored value has to reach the clip."""
    long_output = "x" * 5_000

    tunables.set_many({"tools.inline_output_chars": 500})
    tunables.invalidate()
    assert len(builtins._clip(long_output)) < 700, "the clip ignored the setting"

    tunables.set_many({"tools.inline_output_chars": 4_000})
    tunables.invalidate()
    assert len(builtins._clip(long_output)) > 3_900, "the clip ignored the setting"


def test_an_out_of_range_value_is_clamped_and_reported(fresh_db):
    """A tunable carries a range for a reason: zero tool steps is a runtime
    that can never call a tool, and nothing downstream re-checks for it.

    The contract is clamp-and-report, not refuse — the caller is told the value
    did not survive intact, and what actually landed is inside the range.
    """
    result = tunables.set_many({"tools.max_steps": 0})
    tunables.invalidate()

    assert result["stored"]["tools.max_steps"] == 1, "0 was stored as given"
    assert "tools.max_steps" in result["rejected"], \
        "the value was silently altered with nothing said about it"
    assert runtime.max_tool_steps() == 1, \
        "a zero step ceiling reached the runtime; it can no longer call a tool"
