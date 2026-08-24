"""The operation table — what the executor is allowed to assume.

These are not tests of behaviour; nothing here performs an operation. They are
tests of a set of CLAIMS, and the claims are load-bearing: a batch executor
asks "is this safe to run unattended", a recovery engine asks "is this safe to
retry", a policy gate asks "does this need confirmation", and all three get
their answer from this table rather than from reading the code that performs
the work. A wrong entry here is a wrong answer everywhere at once, silently.

So the properties worth pinning are the ones where being wrong is expensive
and being wrong is easy: that a click is never quietly classified as cheap,
that a batch takes the severity of its worst member rather than its average,
and that an operation nobody declared is refused instead of defaulted.

No Windows dependency — the table is a description, and descriptions should be
checkable on any machine.
"""
from __future__ import annotations

import pytest

from primnox2.computer import actions, operations as ops


# ── The table itself ────────────────────────────────────────────────────────

def test_every_verb_declares_a_known_side_effect_class():
    for name, verb in ops.VERBS.items():
        assert verb.side_effect in ops.SEVERITY, f"{name} has no severity"


def test_every_declared_route_exists():
    """A route the executor cannot dispatch is a plan for a runtime failure
    written down in advance."""
    for name, verb in ops.VERBS.items():
        assert verb.routes, f"{name} declares no route"
        for route in verb.routes:
            assert route in actions.RUNGS, f"{name} routes via unknown {route!r}"


def test_the_preferred_route_is_never_lower_than_a_fallback():
    """The ladder is only useful climbed downwards. A verb whose first choice
    sits below its second would descend on success, which is backwards."""
    for name, verb in ops.VERBS.items():
        rungs = [int(actions.RUNGS[r][1:]) for r in verb.routes]
        assert rungs == sorted(rungs, reverse=True), (
            f"{name} prefers a lower rung than it falls back to: {verb.routes}")


def test_an_undeclared_verb_is_refused_rather_than_defaulted():
    """A default would let a new operation reach the executor without anybody
    deciding what it costs."""
    with pytest.raises(ops.UnknownVerb):
        ops.spec("frobnicate")


def test_the_refusal_names_what_is_available():
    with pytest.raises(ops.UnknownVerb) as raised:
        ops.spec("frobnicate")
    assert "click" in str(raised.value)


# ── The two claims that must not be collapsed ───────────────────────────────

def test_clicking_is_classified_by_what_it_might_be_not_by_how_it_looks():
    """`click` is one call and the application decides what it means. Expand a
    panel and send the message are the same operation from here."""
    assert ops.spec("click").side_effect == ops.IRREVERSIBLE
    assert ops.spec("click").reversible is False


def test_a_captured_toggle_narrows_a_click_to_reversible():
    """Refusing to narrow would push every checkbox through the confirmation
    built for irreversible things, which teaches the user to click through
    it — worse than not having it."""
    click = ops.Operation("click", {"ref": "e4@2"})
    assert click.side_effect() == ops.IRREVERSIBLE
    assert click.side_effect(reversal_captured=True) == ops.REVERSIBLE


def test_scrolling_is_harmless_and_not_idempotent():
    """The case that proves the two fields are independent: nothing durable
    changes, and doing it twice goes twice as far."""
    scroll = ops.spec("scroll")
    assert scroll.side_effect == ops.READ
    assert scroll.idempotent is False


def test_typing_is_repeatable_and_recorded_as_reversible():
    typing = ops.spec("type")
    assert typing.idempotent is True
    assert typing.reversible is True
    assert typing.safe_to_repeat() is True


def test_nothing_that_leaves_the_machine_is_ever_safe_to_repeat():
    """Idempotence is a claim about local state. Once an operation is out on a
    network, what may already have happened is beyond reach of any reasoning
    done here — so the local claim stops applying."""
    external = ops.Verb("send", ops.EXTERNAL, idempotent=True,
                        reversible=False, routes=(actions.ROUTE_PATTERN,))
    assert external.safe_to_repeat() is False


def test_an_operation_with_no_verifier_says_so_rather_than_implying_one():
    """The empty verifier is the honest entry: these are the operations that
    can only ever come back NOT VERIFIED."""
    assert ops.spec("click").verifier == ""
    assert ops.spec("keys").verifier == ""
    assert ops.spec("type").verifier != ""


# ── Batches ─────────────────────────────────────────────────────────────────

def test_a_batch_takes_the_severity_of_its_worst_member():
    """Averaging would make nine reads and one send look like a read."""
    batch = [ops.Operation("read")] * 9 + [ops.Operation("keys")]
    assert ops.batch_severity(batch) == ops.IRREVERSIBLE


def test_an_empty_batch_is_a_read():
    assert ops.batch_severity([]) == ops.READ


# ── Round-tripping ──────────────────────────────────────────────────────────

def test_an_operation_survives_a_round_trip():
    original = ops.Operation("type", {"ref": "e12@481"}, {"text": "hello"})
    assert ops.Operation.from_json(original.to_json()) == original


def test_a_round_trip_refuses_an_undeclared_verb_at_the_boundary():
    """Where an unknown verb arrives from outside — a stored workflow, another
    process — is exactly where it must be caught, not once it is running."""
    with pytest.raises(ops.UnknownVerb):
        ops.Operation.from_json({"verb": "rm -rf", "arguments": {}})


# ── The bridge to recorded workflows ────────────────────────────────────────

def test_a_recorded_step_becomes_the_operation_it_always_was():
    from primnox2.computer import workflows

    step = workflows.step_for("type", {"role": "Edit", "name": "To",
                                       "ordinal": 0}, {"text": "hi"})
    operation = workflows.operation_for(step)
    assert operation.verb == "type"
    assert operation.target["selector"]["name"] == "To"
    assert operation.arguments["text"] == "hi"


def test_a_coordinate_step_carries_a_point_rather_than_a_selector():
    from primnox2.computer import workflows

    step = workflows.step_for("click", None, {"x": 12, "y": 40})
    assert workflows.operation_for(step).target == {"point": [12, 40]}


def test_recording_an_undeclared_verb_fails_when_it_is_recorded():
    """Caught here it is a message to whoever is recording. Caught at replay
    it is a workflow that stops halfway, in front of somebody who does not
    know what it was for."""
    from primnox2.computer import workflows

    with pytest.raises(ops.UnknownVerb):
        workflows.step_for("frobnicate", None, {})


def test_a_workflow_warns_about_what_it_cannot_undo_before_it_runs():
    from primnox2.computer import workflows

    doc = workflows.document("send it", "win_1_1", "Mail", [
        workflows.step_for("type", {"role": "Edit", "name": "To"}, {"text": "x"}),
        workflows.step_for("keys", None, {"keys": "ctrl+enter"}),
    ])
    described = workflows.describe(doc)
    assert "irreversible" in described
    assert "step 2" in described


def test_a_harmless_workflow_carries_no_warning():
    """A warning on everything is a warning on nothing."""
    from primnox2.computer import workflows

    doc = workflows.document("fill it", "win_1_1", "Form", [
        workflows.step_for("type", {"role": "Edit", "name": "To"}, {"text": "x"}),
        workflows.step_for("scroll", None, {"clicks": -3}),
    ])
    assert "cannot undo" not in workflows.describe(doc)
