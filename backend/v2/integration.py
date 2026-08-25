"""The seam between V1 and the V2 substrate.

Everything else in `v2/` is written to be independent of how Primnox
currently works. This module is the opposite: it is shaped around the calls
V1 already makes, so that adopting V2 is a small diff at a few call sites
rather than a rewrite.

Four entry points, matching the four places V1's tool loop actually needs
something:

* :func:`plan_turn` — before the request goes out: route it, size the step
  budget, and build the context block.
* :func:`observe_tool_result` — where `brain.py` currently appends a full
  tool result to `messages`. Returns the compact string to append instead,
  with the full output kept in the result store.
* :func:`compact_if_needed` — when a turn runs long, without touching the
  cached prefix.
* :func:`record_turn_outcome` — after the turn: cost telemetry, and an
  episodic event so the work is recallable tomorrow.

Nothing here imports `brain`, `server` or `core`; the dependency runs one
way. That keeps V2 testable without the app, and keeps a failure in V2 from
being able to take the chat path down with it — every function here is
written so the worst case is that V1 behaves exactly as it did before.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from v2 import compaction, context as context_builder, episodes, result_store, router, step_budget

try:  # pragma: no cover - logging is incidental to behaviour
    from logger import get_logger

    log = get_logger("v2.integration")
except Exception:  # pragma: no cover
    import logging

    log = logging.getLogger("v2.integration")


@dataclass
class TurnPlan:
    """Everything decided before a request is sent."""

    question: str
    route: router.Route
    budget: step_budget.Plan
    context_block: str = ""
    context_tokens: int = 0
    provenance: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def max_steps(self) -> int:
        return self.budget.max_steps

    def as_dict(self) -> dict:
        return {
            "route": self.route.label,
            "sources": self.route.sources,
            "intent": self.route.intent,
            "max_steps": self.max_steps,
            "cache": self.budget.cache,
            "result_budget_tokens": self.budget.result_budget_tokens,
            "context_tokens": self.context_tokens,
            "notes": self.notes,
        }


def plan_turn(
    question: str,
    *,
    project: str | None = None,
    session: str | None = None,
    task: str | None = None,
    prefix_tokens: int = 0,
    context_budget_tokens: int = context_builder.DEFAULT_BUDGET_TOKENS,
    searcher=None,
    reader=None,
    classifier=None,
) -> TurnPlan:
    """Route, budget and build context for one request.

    On any internal failure this degrades to an empty context with a
    default-sized budget: a request that would have worked before V2 must
    still work, and a planning bug must not become a chat outage.
    """
    decision = router.route(question, classifier=classifier)
    budget = step_budget.plan(question, decision, prefix_tokens=prefix_tokens)

    try:
        built = context_builder.build(
            question,
            project=project,
            session=session,
            task=task,
            route=decision,
            budget_tokens=context_budget_tokens,
            searcher=searcher,
            reader=reader,
        )
    except Exception as exc:
        log.warning("context build failed (%s); continuing without V2 context", exc)
        return TurnPlan(question=question, route=decision, budget=budget,
                        notes=[f"context unavailable: {exc}"])

    return TurnPlan(
        question=question,
        route=decision,
        budget=budget,
        context_block=built.render(),
        context_tokens=built.tokens,
        provenance=built.provenance(),
        notes=built.notes,
    )


def observe_tool_result(
    tool: str,
    result,
    *,
    session: str | None = None,
    task: str | None = None,
    project: str | None = None,
    args: dict | None = None,
    budget_tokens: int | None = None,
    sensitivity: str = "normal",
) -> str:
    """Store a tool result and return what should go into the transcript.

    Drop-in for the place V1 appends `str(result)` to the message list. The
    return value is a compact observation plus a `res_…` handle; the full
    output stays retrievable with :func:`v2.result_store.get`.

    If the store is unavailable, the original result is returned unchanged —
    a degraded, expensive turn beats a failed one.
    """
    try:
        stored = result_store.put(
            tool, result, args=args, session=session, task=task, project=project,
            sensitivity=sensitivity,
            budget_tokens=budget_tokens or result_store.DEFAULT_OBSERVATION_TOKENS,
        )
    except Exception as exc:
        log.warning("result store unavailable (%s); passing the raw result through", exc)
        return str(result)
    return result_store.reference(stored)


def compact_if_needed(
    messages: list[dict],
    *,
    boundary_index: int = 0,
    keep_recent: int = compaction.DEFAULT_KEEP_RECENT,
    min_tokens: int = compaction.MIN_TOKENS_TO_COMPACT,
    summarizer=None,
) -> compaction.CompactionResult:
    """Compact a long turn, leaving the cached prefix untouched.

    Returns the input unchanged when there is nothing worth compacting, so
    this is safe to call on every step of a tool loop.
    """
    try:
        return compaction.compact(
            messages, boundary_index=boundary_index, keep_recent=keep_recent,
            min_tokens=min_tokens, summarizer=summarizer,
        )
    except Exception as exc:
        log.warning("compaction failed (%s); leaving the transcript alone", exc)
        return compaction.CompactionResult(
            messages=messages, boundary_index=boundary_index, compacted=False,
            tokens_before=0, tokens_after=0, reason=f"compaction failed: {exc}",
        )


def record_turn_outcome(
    plan: TurnPlan,
    *,
    steps_used: int,
    billed_tokens: int = 0,
    success: bool = True,
    session: str | None = None,
    task: str | None = None,
    project: str | None = None,
    summary: str | None = None,
    latency_ms: float | None = None,
) -> dict:
    """Record what the turn cost, and leave an episodic trace of it.

    The event is what makes today's work answerable tomorrow; the telemetry
    is what makes "cost per successful task" a measured number rather than
    an assertion. Failures here are logged and swallowed — bookkeeping must
    never fail a turn that already succeeded.
    """
    outcome: dict = {"telemetry_id": None, "event_id": None}
    try:
        outcome["telemetry_id"] = step_budget.record_turn(
            predicted_steps=plan.budget.predicted_steps,
            steps_used=steps_used,
            billed_tokens=billed_tokens,
            success=success,
            cached=plan.budget.cache,
            task=task,
            session=session,
            route_label=plan.route.label,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        log.warning("could not record turn telemetry (%s)", exc)

    try:
        event = episodes.record_event(
            "message" if success else "error",
            summary or plan.question[:200],
            project=project,
            task=task,
            session=session,
            importance=0.6 if success else 0.9,
        )
        outcome["event_id"] = event["id"]
    except Exception as exc:
        log.warning("could not record turn event (%s)", exc)

    return outcome


def note_activity(
    kind: str,
    summary: str,
    *,
    project: str | None = None,
    session: str | None = None,
    entities: list[str] | None = None,
    result_ref: str | None = None,
    occurred_at=None,
) -> str | None:
    """Record an ambient observation from V1's watchers.

    The screen observer, the feed loop and the meeting recorder all see
    things worth remembering. This is how they contribute to episodic memory
    without needing to know anything about it. Returns the event ID, or None
    if the write failed — never a false confirmation.
    """
    try:
        event = episodes.record_event(
            kind, summary, project=project, session=session, entities=entities,
            result_ref=result_ref, occurred_at=occurred_at,
        )
        return event["id"]
    except Exception as exc:
        log.warning("could not record activity (%s)", exc)
        return None
