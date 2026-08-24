"""Fixing a failure without spending a model turn on it.

The taxonomy has declared `REGROUND / WAIT / ASK / STOP` since it landed, and
nothing read the second half. Every failure, however mechanical, came back to
the model as prose, and the model spent a turn deciding to re-read the window
and try again — which is exactly what the code already said to do.

The decision these tests pin down is subtler than "retry idempotent things",
and getting it backwards is how an agent retries its way through a form nobody
asked it to fill in. The question is NOT primarily whether the operation is
idempotent. It is whether it ran at all:

  A click is not idempotent — pressing Send twice sends twice — and a click
  that failed with TARGET_NOT_FOUND is safe to retry, because there was no
  target, so nothing was pressed.

  A read is idempotent, and a read that failed with TIMEOUT is a different
  matter: we stopped waiting, which is not the same as nothing happening.
  There, repeatability is the right question.

Both get asked, of two tables: `failures.BEFORE_EXECUTION` for the first,
`operations.Verb.safe_to_repeat` for the second.
"""
from __future__ import annotations

import sys

import pytest

from primnox2.computer import failures, operations, recovery


# ── The decision, which is pure and worth testing on its own ────────────────

def test_a_click_that_never_ran_is_retried():
    """The case that proves the rule is not about idempotence. `click` is the
    least repeatable operation in the table, and this retries it."""
    plan = recovery.plan_for(failures.TARGET_NOT_FOUND, "click")
    assert plan.retry is True
    assert plan.strategy == failures.REGROUND
    assert "never ran" in plan.reason


def test_a_click_that_may_have_run_is_not_retried():
    """TIMEOUT means we stopped waiting, not that nothing happened. The
    application may be part-way through pressing Send."""
    plan = recovery.plan_for(failures.TIMEOUT, "click")
    assert plan.retry is False
    assert "may have already taken effect" in plan.reason


def test_a_repeatable_operation_survives_an_ambiguous_failure():
    plan = recovery.plan_for(failures.TIMEOUT, "read")
    assert plan.retry is True
    assert "safe to repeat" in plan.reason


def test_typing_the_same_text_twice_is_still_typing_it_once():
    """SetValue replaces rather than appends, which is what makes an
    ambiguous failure recoverable here and not for a click."""
    assert operations.spec("type").safe_to_repeat() is True
    assert recovery.plan_for(failures.TIMEOUT, "type").retry is True


def test_a_permission_refusal_is_never_retried():
    plan = recovery.plan_for(failures.PERMISSION_DENIED, "click")
    assert plan.retry is False
    assert plan.strategy == failures.STOP


def test_ambiguity_is_handed_back_rather_than_resolved():
    """There are two windows and the runtime does not get to pick one."""
    plan = recovery.plan_for(failures.TARGET_AMBIGUOUS, "click")
    assert plan.retry is False
    assert plan.strategy == failures.ASK
    assert plan.hands_back


def test_the_second_attempt_is_the_last():
    """A target still stale after one clean re-read is not a timing problem,
    and a second automatic attempt spends the turn arriving at the same place
    more slowly."""
    assert recovery.plan_for(failures.TARGET_NOT_FOUND, "click",
                             attempts=0).retry is True
    assert recovery.plan_for(failures.TARGET_NOT_FOUND, "click",
                             attempts=failures.MAX_AUTOMATIC_ATTEMPTS).retry is False


def test_an_unknown_operation_is_not_retried():
    """Something the operation table does not describe has not had anybody
    decide whether repeating it is safe."""
    plan = recovery.plan_for(failures.TIMEOUT, "frobnicate")
    assert plan.retry is False
    assert "declares nothing" in plan.reason


def test_not_knowing_what_was_attempted_means_not_retrying():
    plan = recovery.plan_for(failures.TIMEOUT, None)
    assert plan.retry is False


def test_an_unclassified_failure_stops():
    plan = recovery.plan_for(None, "click")
    assert plan.retry is False
    assert plan.strategy == failures.STOP


def test_every_before_execution_code_is_a_real_code():
    for code in failures.BEFORE_EXECUTION:
        assert code in failures.RECOVERY, f"{code} has no recovery policy"


def test_nothing_that_leaves_the_machine_is_ever_repeated():
    external = operations.Verb("send", operations.EXTERNAL, idempotent=True,
                               reversible=False, routes=("uia_pattern",))
    assert external.safe_to_repeat() is False


# ── End to end, through the tool funnel ────────────────────────────────────

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="Computer Use is Windows-only")

if sys.platform == "win32":
    from primnox2.computer import session as sessions
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext
    from test_computer_use import window            # noqa: F401


@pytest.fixture
def controlled(window):                              # noqa: F811
    ctx = ToolContext(conversation_id=f"conv_recover_{id(window)}")
    opened = computer_tools._control_window(
        {"window": window.handle, "reason": "recovery tests"}, ctx)
    assert opened["status"] != "error", opened
    try:
        yield ctx, sessions.current(ctx.conversation_id)
    finally:
        active = sessions.current(ctx.conversation_id)
        if active:
            active.close("test finished")


@windows_only
def test_a_recoverable_failure_is_fixed_without_the_model(controlled):
    """The whole point. The first attempt fails with something the code says
    to re-ground on; the runtime re-reads and retries; the model is handed a
    success rather than a turn spent deciding to look again."""
    ctx, active = controlled
    calls: list[int] = []

    def sometimes():
        calls.append(1)
        if len(calls) == 1:
            raise LookupError("there is no element 'e999' in the last read")
        return computer_tools._ok("done on the second attempt")

    result = computer_tools._guard(sometimes, verb="click", ctx=ctx, args={})
    assert result["status"] == "success"
    assert len(calls) == 2, "the operation was not retried"
    assert result["recovered"] == failures.REGROUND


@windows_only
def test_recovery_re_reads_before_retrying(controlled):
    """A retry that does not re-ground is just the same call again. The point
    of the re-read is that the ref then rebinds against a new tree."""
    ctx, active = controlled
    before = active.generation
    calls: list[int] = []

    def sometimes():
        calls.append(1)
        if len(calls) == 1:
            raise LookupError("no such element")
        return computer_tools._ok("ok")

    computer_tools._guard(sometimes, verb="click", ctx=ctx, args={})
    assert active.generation > before, "the window was not re-read"


@windows_only
def test_the_recovery_is_said_out_loud(controlled):
    """Recovery nobody can see is recovery nobody can audit — and "it worked
    on the second try" matters when the same step starts failing every time."""
    ctx, _ = controlled
    calls: list[int] = []

    def sometimes():
        calls.append(1)
        if len(calls) == 1:
            raise LookupError("the button had moved")
        return computer_tools._ok("clicked")

    result = computer_tools._guard(sometimes, verb="click", ctx=ctx, args={})
    assert "retried once" in result["summary"]
    assert "the button had moved" in result["summary"]


@windows_only
def test_a_second_failure_reports_the_second_failure(controlled):
    """Reporting the first would send the model to look at a window that has
    since been re-read."""
    ctx, _ = controlled

    def always(counter=[0]):
        counter[0] += 1
        raise LookupError(f"failure number {counter[0]}")

    result = computer_tools._guard(always, verb="click", ctx=ctx, args={})
    assert result["status"] == "error"
    assert "failure number 2" in result["summary"]
    assert result["retried"] == failures.REGROUND


@windows_only
def test_an_unrecoverable_failure_is_not_retried(controlled):
    """A permission refusal retried automatically is an agent arguing with a
    gate."""
    ctx, _ = controlled
    calls: list[int] = []

    def denied():
        calls.append(1)
        raise computer_tools.grants.Denied("that window is not under control")

    result = computer_tools._guard(denied, verb="click", ctx=ctx, args={})
    assert result["status"] == "error"
    assert len(calls) == 1, "a permission refusal was retried"


@windows_only
def test_recovery_is_off_when_there_is_no_context(controlled):
    """`_guard` is called without a context in places that cannot re-ground.
    Those must keep their old behaviour exactly."""
    calls: list[int] = []

    def once():
        calls.append(1)
        raise LookupError("nope")

    result = computer_tools._guard(once)
    assert result["status"] == "error"
    assert len(calls) == 1
