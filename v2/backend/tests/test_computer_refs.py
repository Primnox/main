"""Generational refs — the silent misclick, made detectable.

The bug these exist to close does not look like a bug in a log. A model reads
a window, plans against it, and by the time it acts a dialog has opened, a
list has scrolled, or a toolbar has swapped a button. `e12` still resolves —
to whatever is twelfth NOW. The action succeeds. The verifier confirms it,
correctly, because the wrong control really was set. Nothing anywhere reports
a problem.

Stamping each read makes the mismatch visible, and once it is visible there
are only two honest responses: find the thing the model actually meant, or
refuse. Guessing is what was already happening.

Same purpose-built target as `test_computer_use.py`; see that file's docstring
for why it is not a real application.
"""
from __future__ import annotations

import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Computer Use is Windows-only")

from primnox2.computer import actions, grants, session as sessions, targets, tree
from test_computer_use import window            # noqa: F401  (fixture)


CONVERSATION = "conv_refs_tests"


@pytest.fixture
def active(window):                              # noqa: F811
    session = sessions.open_session(
        window, grants.ACT, conversation_id=CONVERSATION, turn_id=None)
    try:
        yield session
    finally:
        session.close("test finished")


# ── Parsing ─────────────────────────────────────────────────────────────────

def test_a_ref_carries_the_read_it_came_from():
    assert tree.parse_ref("e12@481") == ("e12", 481)
    assert tree.parse_ref("[e3@7]") == ("e3", 7)


def test_an_unstamped_ref_is_accepted_rather_than_refused():
    """A model that drops the suffix is being less specific, not wrong."""
    assert tree.parse_ref("e12") == ("e12", None)


def test_a_malformed_stamp_is_not_quietly_downgraded():
    """`e12@banana` must not become the unstamped `e12` and get acted on."""
    with pytest.raises(ValueError):
        tree.parse_ref("e12@banana")


# ── What the model is shown ─────────────────────────────────────────────────

def test_the_rendered_tree_stamps_every_ref(active):
    rendered = active.read_tree().render()
    assert f"@{active.generation}]" in rendered, rendered[:300]


def test_an_unstamped_read_stays_unstamped():
    """`tree.read` outside a session has nothing to be stale against, so the
    qualified form would be a promise with no counter behind it."""
    element = tree.Element(ref="e1", role="Button", name="Save", value="",
                           patterns=["invoke"], bounds=(0, 0, 10, 10),
                           enabled=True, depth=0, hwnd=0)
    snapshot = tree.Snapshot(handle="win_1_1", title="t", elements=[element])
    assert snapshot.generation == 0
    assert "[e1]" in snapshot.render()


def test_reading_twice_advances_the_generation(active):
    first = active.read_tree()
    second = active.read_tree()
    assert second.generation == first.generation + 1


# ── Resolution ──────────────────────────────────────────────────────────────

def test_a_current_ref_resolves_directly(active):
    snapshot = active.read_tree()
    element = snapshot.actionable()[0]
    resolved = active.element(element.qualified(snapshot.generation))
    assert resolved is element
    assert active.last_resolution["resolved"] == "direct"


def test_a_stale_ref_rebinds_to_the_same_control(active):
    """The whole point. A ref from an older read must land on the control it
    named then, not on whatever now occupies that position."""
    first = active.read_tree()
    chosen = first.actionable()[0]
    stale = chosen.qualified(first.generation)

    active.read_tree()                            # the window moves on
    rebound = active.element(stale)

    assert rebound.role == chosen.role
    assert rebound.name == chosen.name
    provenance = active.last_resolution
    assert provenance["resolved"] == "rebound"
    assert provenance["from_generation"] == first.generation


def test_a_ref_from_a_read_that_never_happened_is_refused(active):
    """Rounding an invented generation down to the current read is exactly the
    silent misclick this is meant to end."""
    active.read_tree()
    with pytest.raises(targets.Stale) as raised:
        active.element("e1@9999")
    assert "9999" in str(raised.value)


def test_a_ref_older_than_the_remembered_window_is_refused(active):
    """Rebinding from fifteen reads ago would be honouring a claim about a
    window nobody should still believe describes this one."""
    first = active.read_tree()
    for _ in range(sessions.REBIND_HISTORY + 1):
        active.read_tree()
    with pytest.raises(targets.Stale):
        active.element(f"e1@{first.generation}")


def test_rebinding_refuses_when_the_control_is_gone(active, monkeypatch):
    """A selector that matches nothing must raise, not fall back to something
    that happens to be nearby."""
    first = active.read_tree()
    chosen = first.actionable()[0]
    stale = chosen.qualified(first.generation)
    active.read_tree()

    monkeypatch.setattr(tree, "resolve_selector", lambda *a, **k: None)
    with pytest.raises(targets.Stale) as raised:
        active.element(stale)
    assert "changed" in str(raised.value).lower()


def test_a_ref_that_never_existed_still_lists_what_does(active):
    active.read_tree()
    with pytest.raises(LookupError) as raised:
        active.element("e99999")
    assert "@" in str(raised.value), "the alternatives offered were unstamped"


# ── Provenance ──────────────────────────────────────────────────────────────

def test_an_action_records_how_it_was_delivered(active):
    snapshot = active.read_tree()
    field = tree.find_text_target(snapshot)
    assert field is not None
    active.element(field.qualified(snapshot.generation))
    active.act("type", "type", lambda: actions.set_value(field, "hello"),
               route=actions.ROUTE_PATTERN)

    entry = [e for e in active.log if e["kind"] == "type"][-1]
    provenance = entry["provenance"]
    assert provenance["route"] == actions.ROUTE_PATTERN
    assert provenance["rung"] == "L3"
    assert provenance["generation"] == snapshot.generation
    assert provenance["target"]["handle"] == active.target.handle


def test_a_rebound_action_says_so_in_its_own_record(active):
    """A log that reads identically whether the model hit what it named or
    something the runtime substituted cannot be used to diagnose a replay."""
    first = active.read_tree()
    field = tree.find_text_target(first)
    assert field is not None
    stale = field.qualified(first.generation)

    active.read_tree()
    element = active.element(stale)
    active.act("type", "type", lambda: actions.set_value(element, "rebound"),
               route=actions.ROUTE_PATTERN)

    resolution = active.log[-1]["provenance"]["resolution"]
    assert resolution["resolved"] == "rebound"
    assert resolution["from_generation"] == first.generation
    assert resolution["selector"]["role"] == field.role


def test_provenance_is_consumed_not_inherited(active):
    """A second action with no ref of its own must not borrow the first one's
    resolution and claim a lineage it does not have."""
    snapshot = active.read_tree()
    field = tree.find_text_target(snapshot)
    assert field is not None
    active.element(field.qualified(snapshot.generation))

    active.act("type", "a", lambda: actions.set_value(field, "one"),
               route=actions.ROUTE_PATTERN)
    active.act("keys", "b", lambda: "pressed", route=actions.ROUTE_ATTACHED)

    assert "resolution" in active.log[-2]["provenance"]
    assert "resolution" not in active.log[-1]["provenance"]


# ── Re-reading, against a real window ───────────────────────────────────────

def test_a_re_read_of_an_unchanged_window_costs_less_than_the_tree(window):  # noqa: F811
    """The measurement the whole idea rests on. If a delta is not cheaper than
    the tree on a real window, it is complexity for nothing.

    Note what `_control_window` already does: it opens the session AND reads,
    so the model's first explicit read_window is already a re-read. That is
    where most of the saving actually lands, and it is invisible unless you
    look at generations.
    """
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    ctx = ToolContext(conversation_id="conv_delta")
    opened = computer_tools._control_window(
        {"window": window.handle, "reason": "test delta"}, ctx)
    assert opened["status"] != "error", opened
    try:
        delta = computer_tools._read_window({}, ctx)["output"]
        whole = computer_tools._read_window({"full": True}, ctx)["output"]
        assert len(delta) < len(whole), (
            f"a re-read cost {len(delta)} chars against a tree of {len(whole)}")
        assert "Nothing changed since read" in delta, delta[:400]
        # And it must still say the refs are good, or the model re-reads to
        # get them back and the saving is handed straight back.
        assert "still work" in delta
    finally:
        session = sessions.current("conv_delta")
        if session:
            session.close("test finished")


def test_full_still_returns_the_whole_tree(window):                  # noqa: F811
    """The escape hatch has to actually work, or a model that has lost the
    base read has no way back to one."""
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    ctx = ToolContext(conversation_id="conv_delta_full")
    computer_tools._control_window(
        {"window": window.handle, "reason": "test full"}, ctx)
    try:
        first = computer_tools._read_window({}, ctx)["output"]
        again = computer_tools._read_window({"full": True}, ctx)["output"]
        assert len(again) >= len(first) * 0.9, "full returned a delta"
        assert "Nothing changed" not in again
    finally:
        session = sessions.current("conv_delta_full")
        if session:
            session.close("test finished")


def test_every_route_declares_a_rung():
    """A route with no rung makes the ladder undecidable exactly where it is
    supposed to be doing the work."""
    for route in (actions.ROUTE_PATTERN, actions.ROUTE_MESSAGE,
                  actions.ROUTE_ATTACHED, actions.ROUTE_FOREGROUND):
        assert route in actions.RUNGS
