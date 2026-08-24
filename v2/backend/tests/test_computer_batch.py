"""Running several steps in one call — and stopping properly when one fails.

The loop this replaces is `think -> act -> think -> act`, where most of the
thinking decides nothing: filling three fields and pressing Save is four model
calls, and the plan was complete before the first one.

What made batching unsafe to build until now was not the sequencing. It was
that a step could report success without having worked — and multiplied by k
steps, a batch does not fail, it DRIFTS. Step two operates a window step one
did not actually change, step three operates one step two did not, and the
whole run reads as clean. That is why the Verifier had to land first, and it
is what most of this file is really testing: not that eight steps run, but
that step three stopping means steps four through eight do not happen and the
model is told so in those words.

The other half is the substrate paying off. Every step in a batch is written
against ONE read — the model cannot re-read between steps, that is the point —
so by step three the refs are two generations stale. Rebinding is what makes
the batch possible at all.
"""
from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Computer Use is Windows-only")

from primnox2.computer import actions, operations, session as sessions, tree
from primnox2.tools import computer as computer_tools
from primnox2.tools.registry import ToolContext
from test_computer_use import window            # noqa: F401  (fixture)


@pytest.fixture
def controlled(window):                          # noqa: F811
    ctx = ToolContext(conversation_id=f"conv_batch_{id(window)}")
    opened = computer_tools._control_window(
        {"window": window.handle, "reason": "batch tests"}, ctx)
    assert opened["status"] != "error", opened
    try:
        yield ctx, sessions.current(ctx.conversation_id)
    finally:
        active = sessions.current(ctx.conversation_id)
        if active:
            active.close("test finished")


def field_ref(active):
    snapshot = active.snapshot or active.read_tree()
    field = tree.find_text_target(snapshot)
    assert field is not None
    return field.qualified(snapshot.generation), field


# ── Validation, which happens before anything runs ──────────────────────────

def test_an_unknown_verb_is_refused_before_the_first_step(controlled):
    """A batch that discovers a bad verb halfway through has already done the
    first half, and there is no putting that back."""
    ctx, active = controlled
    ref, _ = field_ref(active)
    before = len(active.log)
    result = computer_tools._run_steps({"steps": [
        {"verb": "type", "ref": ref, "text": "should not happen"},
        {"verb": "teleport"},
    ]}, ctx)
    assert result["status"] == "error"
    assert "teleport" in result["summary"]
    assert not [e for e in active.log[before:] if e["kind"] == "type"], (
        "the first step ran before the batch was validated")


def test_the_available_verbs_are_named_in_the_refusal(controlled):
    ctx, _ = controlled
    result = computer_tools._run_steps({"steps": [{"verb": "teleport"}]}, ctx)
    assert "click" in result["summary"] and "type" in result["summary"]


def test_a_batch_longer_than_the_budget_is_refused(controlled):
    """The structural answer to a small model that emits forty steps because
    it has lost track of what it is doing."""
    ctx, _ = controlled
    steps = [{"verb": "read"}] * (computer_tools.MAX_BATCH_STEPS + 1)
    result = computer_tools._run_steps({"steps": steps}, ctx)
    assert result["status"] == "error"
    assert result["code"] == "PRECONDITION_FAILED"


def test_an_empty_batch_is_refused(controlled):
    ctx, _ = controlled
    assert computer_tools._run_steps({"steps": []}, ctx)["status"] == "error"


# ── Running ─────────────────────────────────────────────────────────────────

def test_steps_run_in_order_and_each_is_reported(controlled):
    ctx, active = controlled
    ref, _ = field_ref(active)
    result = computer_tools._run_steps({"steps": [
        {"verb": "type", "ref": ref, "text": "one"},
        {"verb": "type", "ref": ref, "text": "two"},
        {"verb": "read"},
    ]}, ctx)
    assert result["status"] == "success", result["summary"]
    body = result["output"]
    assert body.index("1.") < body.index("2.") < body.index("3.")
    assert "All 3 steps completed" in body


def test_the_window_ends_in_the_last_step_s_state(controlled):
    ctx, active = controlled
    ref, field = field_ref(active)
    computer_tools._run_steps({"steps": [
        {"verb": "type", "ref": ref, "text": "first"},
        {"verb": "type", "ref": ref, "text": "last"},
    ]}, ctx)
    assert tree.live_value(field) == "last"


def test_one_call_does_what_four_would_have(controlled):
    """The measurement the feature exists for: steps that would each have been
    a separate model round-trip, spent as one."""
    ctx, active = controlled
    ref, _ = field_ref(active)
    before = active.grant.actions_used
    computer_tools._run_steps({"steps": [
        {"verb": "type", "ref": ref, "text": "a"},
        {"verb": "type", "ref": ref, "text": "ab"},
        {"verb": "type", "ref": ref, "text": "abc"},
    ]}, ctx)
    assert active.grant.actions_used == before + 3, (
        "three actions should still be three actions on the record")


# ── Stopping, which is the part that has to be right ────────────────────────

def test_a_failing_step_stops_the_batch(controlled):
    ctx, active = controlled
    ref, _ = field_ref(active)
    result = computer_tools._run_steps({"steps": [
        {"verb": "type", "ref": ref, "text": "ran"},
        {"verb": "click", "ref": "e99999@1"},
        {"verb": "type", "ref": ref, "text": "MUST NOT RUN"},
    ]}, ctx)
    assert result["status"] == "error"
    assert result["completed_steps"] == 1
    assert "MUST NOT RUN" not in (tree.live_value(field_ref(active)[1]) or "")


def test_the_refusal_says_which_steps_did_not_run(controlled):
    """A model told only "step 2 failed" will often assume the rest ran."""
    ctx, active = controlled
    ref, _ = field_ref(active)
    result = computer_tools._run_steps({"steps": [
        {"verb": "type", "ref": ref, "text": "ran"},
        {"verb": "click", "ref": "e99999@1"},
        {"verb": "type", "ref": ref, "text": "never"},
        {"verb": "read"},
    ]}, ctx)
    assert "Stopped at step 2 of 4" in result["summary"]
    assert "3-4 did NOT run" in result["summary"]


def test_a_step_whose_effect_is_contradicted_stops_the_batch(controlled,
                                                             monkeypatch):
    """The reason batching had to wait for the Verifier. A write that reports
    success without landing does not fail a batch — it makes every later step
    operate a window that is not in the state they assume."""
    ctx, active = controlled
    ref, _ = field_ref(active)

    def no_op(element, text):
        return f"set {element.role} to {text!r}"

    monkeypatch.setattr(actions, "set_value", no_op)
    result = computer_tools._run_steps({"steps": [
        {"verb": "type", "ref": ref, "text": "THIS NEVER LANDS"},
        {"verb": "read"},
    ]}, ctx)
    assert result["status"] == "error", "a write that did nothing passed"
    assert result["completed_steps"] == 0


def test_a_stopped_batch_carries_the_failing_step_s_code(controlled):
    """The recovery strategy has to survive being wrapped in a batch, or every
    batch failure becomes an unclassified STOP."""
    ctx, active = controlled
    ref, _ = field_ref(active)
    result = computer_tools._run_steps({"steps": [
        {"verb": "type", "ref": ref, "text": "ok"},
        {"verb": "click", "ref": "e99999@1"},
    ]}, ctx)
    assert result["code"] and result["recovery"]


# ── The substrate paying off ────────────────────────────────────────────────

def test_refs_survive_the_batch_changing_the_window(controlled):
    """Every step is written against ONE read — that is what a batch is — so
    by step three the refs are two generations old. Without rebinding they
    would land on whatever now occupies those positions."""
    ctx, active = controlled
    ref, field = field_ref(active)
    generation = active.generation

    result = computer_tools._run_steps({"steps": [
        {"verb": "type", "ref": ref, "text": "one"},
        {"verb": "read"},
        {"verb": "read"},
        {"verb": "type", "ref": ref, "text": "four"},
    ]}, ctx)
    assert result["status"] == "success", result["summary"]
    assert active.generation > generation + 1, "the reads did not advance"
    assert tree.live_value(field) == "four", (
        "the stale ref did not rebind to the same control")


def test_a_ref_too_old_to_rebind_stops_the_batch(controlled):
    """Rebinding has a horizon. Past it the model is not slightly behind, it
    is describing a different window, and guessing would be worse than
    stopping."""
    ctx, active = controlled
    ref, _ = field_ref(active)
    for _ in range(sessions.REBIND_HISTORY + 2):
        active.read_tree()
    result = computer_tools._run_steps(
        {"steps": [{"verb": "type", "ref": ref, "text": "x"}]}, ctx)
    assert result["status"] == "error"
    assert result["code"] == "TARGET_STALE"


# ── Severity ────────────────────────────────────────────────────────────────

def test_a_batch_is_classified_by_its_worst_step():
    """Nine reads and one keystroke that sends a message is a send."""
    batch = [operations.Operation("read")] * 9 + [operations.Operation("keys")]
    assert operations.batch_severity(batch) == operations.IRREVERSIBLE


def test_a_batch_announces_its_worst_case_before_it_runs(controlled):
    """This package's safety argument is that the user watches actions happen
    and can cut the session mid-run. A batch breaks that unless the
    announcement covers the whole batch — by the time step one appears, steps
    two through five are already committed to."""
    ctx, active = controlled
    ref, _ = field_ref(active)
    computer_tools._run_steps({"steps": [
        {"verb": "type", "ref": ref, "text": "a"},
        {"verb": "keys", "keys": "end"},
    ]}, ctx)
    announcement = [e for e in active.log if e["kind"] == "batch"][-1]
    assert "about to run 2 steps" in announcement["description"]
    assert operations.IRREVERSIBLE in announcement["description"]


def test_an_action_records_the_side_effect_class_it_actually_had(controlled):
    """A click is declared IRREVERSIBLE because the application decides what a
    click means. A click on a toggle whose prior state was captured really is
    reversible, and the log should say which of the two just happened."""
    ctx, active = controlled
    ref, _ = field_ref(active)
    computer_tools._type_into({"ref": ref, "text": "recorded"}, ctx)
    entry = [e for e in active.log if e["kind"] == "type"][-1]
    assert entry["provenance"]["side_effect"] == operations.REVERSIBLE


def test_every_batchable_verb_is_a_declared_operation():
    """A verb a batch can run but the operation table does not describe would
    be executed without anybody having decided what it costs."""
    for verb in computer_tools._BATCH_STEPS:
        assert verb in operations.VERBS, verb
