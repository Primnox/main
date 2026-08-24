"""Acting on a failure without spending a model turn on it.

`failures.py` classifies what went wrong and declares what should be done
about it. Until now nothing read that second half: every failure, however
mechanical, came back to the model as a sentence, and the model spent a turn
deciding to read the window and try again — which is exactly what the code
already said to do.

That is the wrong division of labour, and it is expensive in the way that
compounds. A stale ref inside a five-step batch does not cost one turn, it
costs the batch: the run stops, the model re-reads, re-plans the remaining
four steps against a new tree, and re-sends them. The correct response was
"look again and retry once", and nothing needed to think about it.

So this is the dispatcher. It answers one question — may the runtime fix this
itself, and how — and the answer is deliberately conservative, because the
failure mode of getting it wrong is an agent that retries its way through a
form nobody asked it to fill in.

**The rule that matters is not idempotence.** It is whether the operation ran
at all. A click is not idempotent — pressing Send twice sends twice — and a
click that failed with TARGET_NOT_FOUND is still safe to retry, because there
was no target, so nothing was pressed. The reverse is also true: a TIMEOUT on
a perfectly repeatable read means only that we stopped waiting, not that
nothing happened, and repeating it is a judgement about the operation rather
than about the failure.

Both questions therefore get asked, of two different tables:

    failures.BEFORE_EXECUTION   did it run?
    operations.Verb.safe_to_repeat()   if it might have, does repeating hurt?
"""
from __future__ import annotations

from dataclasses import dataclass

from . import failures, operations


@dataclass(frozen=True)
class Plan:
    """What to do about one failure, decided before anything is done."""
    strategy: str                  # REGROUND / WAIT / ASK / STOP
    retry: bool                    # may the runtime try again by itself
    reason: str                    # why, in words that go in the log

    @property
    def hands_back(self) -> bool:
        """Whether the model has to be involved at all."""
        return not self.retry


def plan_for(code: "str | None", verb: "str | None", *,
             attempts: int = 0) -> Plan:
    """Decide how one failure should be handled.

    `attempts` is how many automatic attempts have already been spent on this
    operation. Past the cap the answer is always to hand back, whatever the
    strategy says: a target that is still stale after one clean re-read is not
    a timing problem, and a second automatic attempt spends the turn arriving
    at the same place more slowly.
    """
    strategy = failures.recovery_for(code or failures.EXECUTION_FAILED)

    if strategy in (failures.ASK, failures.STOP):
        return Plan(strategy, False,
                    "only the user can settle this" if strategy == failures.ASK
                    else "retrying would fail the same way, or is unsafe")

    if attempts >= failures.MAX_AUTOMATIC_ATTEMPTS:
        return Plan(strategy, False,
                    f"already retried {attempts}x — this is not a timing problem")

    if code in failures.BEFORE_EXECUTION:
        return Plan(strategy, True, "the operation never ran, so retrying it "
                                    "cannot repeat anything")

    # It may have run. Now — and only now — does repeatability matter.
    if verb is None:
        return Plan(strategy, False,
                    "it is not known what was being attempted, so it is not "
                    "known whether repeating it is safe")
    try:
        spec = operations.spec(verb)
    except operations.UnknownVerb:
        return Plan(strategy, False, f"{verb!r} declares nothing about repeating")

    if spec.safe_to_repeat():
        return Plan(strategy, True,
                    f"{verb} is safe to repeat whether or not it ran")
    return Plan(strategy, False,
                f"{verb} may have already taken effect, and repeating it is "
                f"not harmless ({spec.side_effect})")


def describe(plan: Plan, code: "str | None") -> dict:
    """The decision as it is attached to a result, for the log and the model."""
    return {"code": code, "recovery": plan.strategy,
            "retried": plan.retry, "why": plan.reason}
