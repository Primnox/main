"""The cost surface: steps x result size x caching.

Every earlier measurement here optimised a single point — one turn, four
steps, one result size — and a single point cannot tell you which knob to
turn. This maps the surface, because the shape is the finding:

    cost is proportional to steps TIMES accumulated tool output

If that is right, then halving the steps and halving the result size each beat
any amount of caching, and caching is a correction applied on top of whichever
shape you end up with.

Held identical across every cell: provider, model, question, preamble, and the
tool result's content. Only three things vary — how many steps the loop runs,
how large each result is, and whether the conversation carries a second cache
breakpoint.

The second breakpoint is the part worth being sceptical about. Cache WRITES
are billed above ordinary input tokens, and a conversation that grows every
step rewrites its cache every step, so caching the conversation buys a read
and pays a write. Whether that wins depends on how many times a prefix recurs
— which is exactly what varying the step count measures.

Costs real money: roughly 45 calls at a few thousand input tokens each. The
key is read from `.env` and never printed.

Usage:
    python scripts/bench_cost_surface.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

QUESTION = "What is the capital of France, and why did it end up there?"
STEP_COUNTS = (1, 2, 4, 8)
RESULT_CAPS = (500, 1000, 2000)


def run_loop(call, base, key, model, preamble, result, steps, cache_convo):
    """One turn of `steps` iterations. Returns (sent, billed, calls)."""
    from bench_api_overhead import billed, sent

    messages = [{"role": "user", "content": QUESTION}]
    total_sent = total_billed = 0
    for _ in range(steps):
        convo = [dict(m) for m in messages]
        if cache_convo:
            # The marker goes on the LAST block, so everything before it is
            # the cached prefix for the next call. Marking anything earlier
            # would cache a prefix that never grows and miss the point.
            convo[-1] = {
                "role": convo[-1]["role"],
                "content": [{"type": "text", "text": convo[-1]["content"],
                             "cache_control": {"type": "ephemeral"}}]}
        usage = call(base, key, model, preamble, convo)
        total_sent += sent(usage)
        total_billed += billed(usage)
        messages = messages + [
            {"role": "assistant",
             "content": '<tool name="graph_query">{"query": "paris"}</tool>'},
            {"role": "user", "content": result},
        ]
        time.sleep(0.6)
    return total_sent, total_billed


def main() -> int:
    from bench_api_overhead import billed, call, sent
    from bench_prompt_cache import config

    settings = config()
    base, key, model = (settings["PRIMNOX_BASE_URL"],
                        settings["PRIMNOX_API_KEY"],
                        settings["PRIMNOX_MODEL"])
    if not key or not base:
        print("no cloud key in .env")
        return 2

    from primnox2 import paths
    from primnox2.storage import db

    root = pathlib.Path(tempfile.mkdtemp(prefix="surface"))
    paths.configure(root)
    db.configure(root / "primnox.db")
    db.init()

    from primnox2.memory import service as memory
    from primnox2.tools import runtime

    for i in range(25):
        memory.remember(f"The user prefers approach {i} for their project {i}")
    preamble = runtime.system_prompt()

    print(f"provider {base}  model {model}")
    bare = call(base, key, model, None,
                [{"role": "user", "content": QUESTION}])
    floor = billed(bare)
    print(f"bare call: {sent(bare)} sent, {floor:.0f} billed\n")
    time.sleep(0.6)

    def result_of(cap):
        return runtime.format_result({
            "tool": "graph_query", "status": "success",
            "summary": "4 matches", "output": "x" * cap})

    # ── Steps, at the current 2000-char cap ─────────────────────────────
    print("STEPS  (result cap 2000 chars)")
    print(f"  {'steps':>5s} {'no cache':>10s} {'cached':>9s} "
          f"{'delta':>8s} {'vs bare':>9s}  per step")
    plain_by_steps = {}
    for steps in STEP_COUNTS:
        _, plain = run_loop(call, base, key, model, preamble,
                            result_of(2000), steps, False)
        _, cached = run_loop(call, base, key, model, preamble,
                             result_of(2000), steps, True)
        plain_by_steps[steps] = plain
        delta = 100 * (plain - cached) / max(1, plain)
        print(f"  {steps:5d} {plain:9,.0f}t {cached:8,.0f}t "
              f"{delta:7.0f}% {plain / max(1, floor):8.0f}x "
              f"{plain / steps:9,.0f}t")

    # Is the growth linear in steps, or worse?
    one, eight = plain_by_steps[1], plain_by_steps[8]
    print(f"\n  1 step costs {one:,.0f}; 8 steps costs {eight:,.0f} — "
          f"{eight / max(1, one):.1f}x for 8x the steps.")
    print(f"  Linear would be {8 * one:,.0f}. "
          f"{'Worse than linear' if eight > 8 * one else 'Better than linear'}"
          f" — accumulated results are the difference.")

    # ── Result size, at 4 steps ─────────────────────────────────────────
    print("\nRESULT SIZE  (4 steps)")
    print(f"  {'cap':>6s} {'no cache':>10s} {'cached':>9s} {'delta':>8s}")
    for cap in RESULT_CAPS:
        _, plain = run_loop(call, base, key, model, preamble,
                            result_of(cap), 4, False)
        _, cached = run_loop(call, base, key, model, preamble,
                             result_of(cap), 4, True)
        delta = 100 * (plain - cached) / max(1, plain)
        print(f"  {cap:5d}c {plain:9,.0f}t {cached:8,.0f}t {delta:7.0f}%")

    print("\n  Read the two tables together: if halving the result cap saves "
          "more\n  than caching does, then result size is the lever and "
          "caching is a\n  correction on top of it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
