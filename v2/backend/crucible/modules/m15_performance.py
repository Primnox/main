"""Module 15 — Performance, measured where the user feels it.

Budgets are chosen from what a person notices, not from what is easy to hit:
100ms is instant, 300ms is responsive, a second is a pause you can see.

Only the operations on the critical path of a reply are graded. A slow export is
an annoyance; a slow context build delays every message.
"""
from __future__ import annotations

import statistics
import time

from primnox2.chat import turns as chat
from primnox2.context import service as context
from primnox2.memory import service as memory

from ..scoring import HIGH, MEDIUM, ModuleResult

KEY, NAME = "M15", "Performance"

# seconds — (warn, fail)
BUDGETS = {
    "create_turn": (0.05, 0.20),
    "context_build_short": (0.10, 0.30),
    "context_build_long": (0.30, 1.00),
    "history_read": (0.10, 0.40),
    "memory_search": (0.05, 0.20),
    "conversation_list": (0.05, 0.20),
}


def _time(fn, runs: int = 5) -> dict:
    samples = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return {"median": statistics.median(samples), "worst": max(samples)}


def run(ctx) -> ModuleResult:
    result = ModuleResult(key=KEY, name=NAME)
    started = time.perf_counter()

    short = chat.create_conversation("Crucible M15 short")["id"]
    tid = chat.create_turn(short, "hello")["turn_id"]
    chat.complete(tid, "hi")

    long_cid = chat.create_conversation("Crucible M15 long")["id"]
    for i in range(ctx.scale("perf_history_turns", 120)):
        t = chat.create_turn(long_cid, f"turn {i} about indexing and retrieval")["turn_id"]
        chat.complete(t, f"reply {i}")

    for _ in range(30):
        memory.remember(f"A distinct preference about topic {_} and tooling.")

    measured = {
        "create_turn": _time(lambda: chat.create_turn(short, "probe")),
        "context_build_short": _time(lambda: context.build(short, "what did I say")),
        "context_build_long": _time(lambda: context.build(long_cid, "summarise turn 40")),
        "history_read": _time(lambda: chat.get_history(long_cid)),
        "memory_search": _time(lambda: memory.search("preference tooling")),
        "conversation_list": _time(lambda: chat.list_conversations()),
    }

    result.measurements = {
        k: {"median_ms": round(v["median"] * 1000, 1),
            "worst_ms": round(v["worst"] * 1000, 1),
            "budget_ms": round(BUDGETS[k][1] * 1000)}
        for k, v in measured.items()
    }

    breaches = []
    for name, v in measured.items():
        warn, fail = BUDGETS[name]
        if v["median"] > fail:
            breaches.append((name, v["median"], fail, HIGH))
        elif v["median"] > warn:
            breaches.append((name, v["median"], warn, MEDIUM))

    for name, actual, budget, severity in breaches:
        on_reply_path = name.startswith(("create_turn", "context_build"))
        result.find(
            title=f"{name} median {actual * 1000:.0f}ms exceeds {budget * 1000:.0f}ms",
            severity=severity if on_reply_path else MEDIUM,
            owner="Context Service" if "context" in name else "Storage",
            what_happened=("On the critical path of every reply."
                           if on_reply_path else "User-visible but not per-message."),
            reproduction=f"crucible module {KEY}; time {name} over 5 runs.",
            probable_cause="Unbounded query or per-row work in a loop.",
            suggested_fix="Bound at the SQL level; measure again before optimising further.",
            evidence=str(result.measurements[name]),
        )

    within = sum(1 for n, v in measured.items() if v["median"] <= BUDGETS[n][1])
    result.score(
        correctness=10,
        consistency=10,
        recovery=10,
        performance=round(10 * within / len(measured)),
        ux_stability=round(10 * within / len(measured)),
    )
    result.duration_s = time.perf_counter() - started
    return result
