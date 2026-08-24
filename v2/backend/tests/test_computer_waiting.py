"""Waiting — the turns a model should never have to spend.

Without this, "wait for the dialog" is a polling loop the MODEL runs: read,
see nothing, decide to wait, read again. Every pass is a tree in the context
window and a model call spent producing the answer "not yet". A four-second
dialog can cost five of each, and none of them needed judgement.

The tests that matter here are not that waiting works — a sleep in a loop
works. They are the three ways a wait goes wrong in a way nobody notices:

  It waits the full timeout for something that can no longer happen, because
  the window closed on the first pass and nothing checked.

  It burns generations. Each poll reads the tree, and if those reads are
  stamped, the runtime's own waiting invalidates every ref the model is
  holding — the wait breaks the plan it was helping to execute.

  It gives up saying "timed out", with no record of what it was waiting for,
  and the model spends another turn reconstructing its own intent.
"""
from __future__ import annotations

import sys
import time

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Computer Use is Windows-only")

from primnox2.computer import (grants, session as sessions, targets, tree,
                               waiting)
from test_computer_use import window            # noqa: F401  (fixture)


def snapshot_of(elements):
    return tree.Snapshot(handle="win_1_1", title="t", elements=elements)


def element(role="Button", name="Save", value="", enabled=True):
    return tree.Element(ref="e1", role=role, name=name, value=value,
                        patterns=["invoke"], bounds=(0, 0, 10, 10),
                        enabled=enabled, depth=1, hwnd=0)


# ── Responsiveness ──────────────────────────────────────────────────────────

def test_a_live_window_reports_responsive(window):                   # noqa: F811
    assert waiting.responsiveness(window) == waiting.RESPONSIVE


def test_a_closed_window_reports_closed(window):                     # noqa: F811
    """The check has to survive the window it is asking about going away —
    that is the case it exists for."""
    gone = targets.Target(
        handle="win_1_1", hwnd=1, pid=1, title="gone", window_class="x",
        process="x.exe", bounds=(0, 0, 1, 1), foreground=False,
        minimized=False)
    assert waiting.responsiveness(gone) == waiting.CLOSED


# ── Predicates ──────────────────────────────────────────────────────────────

def test_appears_and_disappears_are_opposites():
    present = snapshot_of([element(name="Save")])
    empty = snapshot_of([])
    assert waiting.element_appears("Save")(present)
    assert not waiting.element_appears("Save")(empty)
    assert waiting.element_disappears("Save")(empty)
    assert not waiting.element_disappears("Save")(present)


def test_enabled_is_not_the_same_question_as_present():
    """A greyed-out Save button is the most common thing worth waiting for and
    is invisible to a predicate that only asks whether it exists."""
    greyed = snapshot_of([element(name="Save", enabled=False)])
    assert waiting.element_appears("Save")(greyed)
    assert not waiting.element_enabled("Save")(greyed)


def test_a_role_narrows_the_match():
    tab = snapshot_of([element(role="TabItem", name="Save")])
    assert waiting.element_appears("Save", role="Button")(tab) is False
    assert waiting.element_appears("Save", role="TabItem")(tab) is True


def test_value_contains_can_be_scoped_to_one_control():
    both = snapshot_of([
        element(role="Edit", name="Status", value="Download complete"),
        element(role="Edit", name="Notes", value="nothing here"),
    ])
    assert waiting.value_contains("complete", name="Status")(both)
    assert not waiting.value_contains("complete", name="Notes")(both)


def test_settled_needs_two_identical_reads_in_a_row():
    predicate = waiting.settled(reads=2)
    changing = snapshot_of([element(value="a")])
    same = snapshot_of([element(value="b")])
    assert not predicate(changing)          # only one read so far
    assert not predicate(same)              # changed
    assert predicate(snapshot_of([element(value="b")]))


def test_a_predicate_that_raises_answers_not_yet():
    """A window mid-change makes predicates throw. That is "not yet", and the
    timeout is what decides when to stop asking — a raised exception escaping
    would turn an ordinary wait into a failed tool call."""
    exploding = waiting.Predicate("boom", lambda s: 1 / 0)
    assert exploding(snapshot_of([])) is False


# ── The wait ────────────────────────────────────────────────────────────────

def test_a_predicate_already_true_returns_at_once(window):           # noqa: F811
    outcome = waiting.wait_until(
        window, waiting.Predicate("anything", lambda s: True), timeout_s=10)
    assert outcome.ok
    assert outcome.waited_s < 1.0


def test_a_timeout_says_what_it_was_waiting_for(window):             # noqa: F811
    predicate = waiting.element_appears("no such control anywhere")
    outcome = waiting.wait_until(window, predicate, timeout_s=1.5)
    assert outcome.status == waiting.TIMED_OUT
    assert outcome.code() == "TIMEOUT"
    assert "no such control anywhere" in outcome.sentence(predicate)


def test_polling_backs_off_rather_than_spinning(window):             # noqa: F811
    """A wait that polls at a fixed fast interval reads the target
    application's tree dozens of times a second, and the cost is paid on its
    UI thread."""
    outcome = waiting.wait_until(
        window, waiting.element_appears("nothing"), timeout_s=3.0)
    naive = 3.0 / waiting.FIRST_POLL_S
    assert outcome.polls < naive / 2, (
        f"{outcome.polls} polls in 3s is not backing off")


def test_a_closed_window_ends_the_wait_instead_of_timing_out():
    """Spending the full timeout discovering the window is gone is the
    difference between a wait and a stall."""
    gone = targets.Target(
        handle="win_1_1", hwnd=1, pid=1, title="gone", window_class="x",
        process="x.exe", bounds=(0, 0, 1, 1), foreground=False,
        minimized=False)
    started = time.monotonic()
    outcome = waiting.wait_until(
        gone, waiting.element_appears("anything"), timeout_s=30)
    assert outcome.status == waiting.WINDOW_CLOSED
    assert time.monotonic() - started < 2.0, "it waited anyway"
    assert outcome.code() == "WINDOW_CHANGED"


def test_the_timeout_is_capped():
    """An uncapped wait inside a 300-second grant is a session that looks
    hung to the user with no way to tell."""
    gone = targets.Target(
        handle="win_1_1", hwnd=1, pid=1, title="gone", window_class="x",
        process="x.exe", bounds=(0, 0, 1, 1), foreground=False,
        minimized=False)
    started = time.monotonic()
    waiting.wait_until(gone, waiting.element_appears("x"), timeout_s=10_000)
    assert time.monotonic() - started < 5.0


# ── The interaction with generations, which is the subtle one ───────────────

def test_waiting_costs_exactly_one_generation(window):               # noqa: F811
    """Polling reads must be anonymous. If each pass went through the session
    it would advance the generation and invalidate every ref the model holds,
    so the runtime's own waiting would break the plan it was executing."""
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    ctx = ToolContext(conversation_id="conv_wait_gen")
    computer_tools._control_window(
        {"window": window.handle, "reason": "test waiting"}, ctx)
    active = sessions.current("conv_wait_gen")
    try:
        before = active.generation
        result = computer_tools._wait_for(
            {"condition": "appears", "what": "nothing at all",
             "timeout_s": 1.5}, ctx)
        assert result["status"] == "error"
        assert active.generation == before, (
            "a failed wait advanced the generation and voided the model's refs")

        computer_tools._wait_for(
            {"condition": "settles", "timeout_s": 5}, ctx)
        assert active.generation == before + 1, (
            "a successful wait should cost exactly one stamped read")
    finally:
        if active:
            active.close("test finished")


def test_a_wait_is_on_the_timeline_before_it_finishes(window):       # noqa: F811
    """A session that goes quiet for twenty seconds and then reports a result
    is precisely what the action log exists to prevent."""
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    ctx = ToolContext(conversation_id="conv_wait_log")
    computer_tools._control_window(
        {"window": window.handle, "reason": "test waiting"}, ctx)
    active = sessions.current("conv_wait_log")
    try:
        computer_tools._wait_for(
            {"condition": "appears", "what": "nope", "timeout_s": 1.0}, ctx)
        entry = [e for e in active.log if e["kind"] == "wait"][-1]
        assert entry["status"] == "failed"
        assert "waiting for" in entry["description"] or "waited" in entry["description"]
        assert "provenance" in entry
    finally:
        if active:
            active.close("test finished")


# ── The tool surface ────────────────────────────────────────────────────────

def test_an_unknown_condition_lists_the_real_ones(window):           # noqa: F811
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    ctx = ToolContext(conversation_id="conv_wait_bad")
    computer_tools._control_window(
        {"window": window.handle, "reason": "test waiting"}, ctx)
    try:
        result = computer_tools._wait_for(
            {"condition": "teleports", "what": "x"}, ctx)
        assert result["status"] == "error"
        assert "appears" in result["summary"] and "settles" in result["summary"]
    finally:
        active = sessions.current("conv_wait_bad")
        if active:
            active.close("test finished")


def test_waiting_for_something_unnamed_is_refused(window):           # noqa: F811
    """"wait for a button to appear" with no button named would wait for the
    first thing that happens and call it success."""
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    ctx = ToolContext(conversation_id="conv_wait_noname")
    computer_tools._control_window(
        {"window": window.handle, "reason": "test waiting"}, ctx)
    try:
        result = computer_tools._wait_for({"condition": "appears"}, ctx)
        assert result["status"] == "error"
        assert result["code"] == "PRECONDITION_FAILED"
    finally:
        active = sessions.current("conv_wait_noname")
        if active:
            active.close("test finished")
