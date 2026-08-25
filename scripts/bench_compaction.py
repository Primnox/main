"""What compaction actually saves, on one workload, across three regimes.

The 59.5% figure in `bf95b46` was measured by hand and never checked in, so
the number could be quoted but not re-derived — and a number nobody can
re-run is a claim, not a measurement. This is that measurement, fixed in
place, so the next change to the compaction path is graded against it rather
than against a commit message.

WHAT IS BEING COUNTED. Not the size of a result — the number of times it is
sent. The scheduler appends the assistant's tool call and the formatted
result to `messages` and re-sends the WHOLE list on the next iteration, so
the first result of an eight-step turn is billed eight times and the last
once. Billed cost is therefore the sum over steps of the entire prompt at
that step, which is what this sums.

THREE REGIMES, ONE WORKLOAD. The workload is identical in all three — same
tools, same outputs, same order — because the only honest comparison holds
everything but the mechanism fixed:

    verbatim   every result appended in full, no compaction at all
    held       `Ledger` at its old threshold: the first ~1,200 tokens of
               tool output stay verbatim, so the first big result is exempt
    eager      `Ledger` at threshold 0, which is what `strategy()` now
               selects for a turn predicted to run long

Each is billed under three cache regimes, because compaction and caching are
not separable here — see `billed`.

THE WORKLOAD IS SYNTHETIC AND SAYS SO. Running the real tools would need a
sandbox, a graph and a network, and would make the number move for reasons
that have nothing to do with compaction. Instead the results are the shapes
the real handlers produce: `_clip` holds `run_shell`, `read_asset` and
`search_assets` at the inline cap, while `graph_query`,
`recall_conversation` and `read_skill` return their output unclipped — which
is why the large results here are large.

Nothing asserts. It prints.

Usage:
    python scripts/bench_compaction.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

QUESTION = ("find every place the scheduler decides how much of a tool result "
            "to send, and tell me which of them can be removed")

TARGET = 95.0


def setup() -> tuple[str, str]:
    """A real conversation and turn, not placeholder ids.

    `_promote_large_output` writes the body to an asset and `attach` has a
    foreign key onto `turns`, so a fabricated turn id makes every promotion
    fail silently — `_store_output` swallows the error so that losing an
    archive copy cannot fail a tool that already ran. The bench then measures
    a `Ledger` with nothing to point at and reports it compacting nothing,
    which is a property of the harness and not of the mechanism.
    """
    from primnox2 import paths
    from primnox2.chat import turns
    from primnox2.storage import db
    from v2 import store

    root = pathlib.Path(tempfile.mkdtemp(prefix="primnox-compaction"))
    paths.configure(root)
    db.configure(root / "primnox.db")
    db.init()
    store.configure(root / "primnox_v2.db")

    conversation = turns.create_conversation("compaction bench")
    turn = turns.create_turn(conversation["id"], QUESTION)
    return conversation["id"], turn["turn_id"]


def _lines(count: int, width: int, prefix: str) -> str:
    """Output with real structure, because the summarisers read structure.

    A block of `x` characters would let the line-oriented excerpters look
    better than they are: `_describe_lines` shows a head and a tail, and on
    uniform filler both are perfectly representative. Numbered, varied lines
    are the case where an excerpt can actually be wrong.
    """
    return "\n".join(
        f"{prefix}:{i}: " + f"symbol_{i % 37} " * max(1, width // 10)
        for i in range(count)
    )


def workload() -> list[dict]:
    """Eight steps of the turn in QUESTION, as the handlers would return them.

    Sizes come from the handlers, not from a wish: the clipped tools sit at
    the inline cap because `_clip` puts them there, and the unclipped ones
    carry what they actually found.
    """
    from primnox2.tools.builtins import _inline_chars

    cap = _inline_chars()
    traceback_tail = "\nModuleNotFoundError: No module named 'v2'"
    return [
        # grep through the shell — clipped, like every `_clip`ed handler.
        {"tool": "run_shell", "status": "success",
         "summary": "42 matches in 11 files",
         "output": _lines(60, 60, "backend/primnox2/kernel/scheduler.py")[:cap]},
        # graph_query — NOT clipped. Returns whatever the subgraph is.
        {"tool": "graph_query", "status": "success",
         "summary": "31 nodes, 47 edges",
         "output": json.dumps({"nodes": [
             {"id": f"n{i}", "src": f"backend/primnox2/tools/mod_{i}.py",
              "loc": f"L{i * 7}", "community": "observations.py",
              "summary": f"symbol_{i} decides what a result costs to send"}
             for i in range(120)]}, indent=1)},
        {"tool": "read_asset", "status": "success",
         "summary": "8,412 characters",
         "output": _lines(60, 60, "observations.py")[:cap]},
        # A failure. Compaction has to survive the case where the useful line
        # is the LAST one, not the first.
        {"tool": "run_python", "status": "error",
         "summary": "ModuleNotFoundError: No module named 'v2'",
         "output": ("Traceback (most recent call last):\n"
                    + _lines(40, 50, "  File step4.py, line")[:cap - 200]
                    + traceback_tail)},
        # recall_conversation — unclipped.
        {"tool": "recall_conversation", "status": "success",
         "summary": "14 earlier exchanges",
         "output": _lines(300, 70, "turn")},
        {"tool": "search_assets", "status": "success",
         "summary": "6 documents matched",
         "output": _lines(60, 60, "asset")[:cap]},
        # read_skill — unclipped, and skills are long.
        {"tool": "read_skill", "status": "success",
         "summary": "testing/SKILL.md, 22,104 characters",
         "output": _lines(340, 65, "SKILL")},
        {"tool": "run_python", "status": "success",
         "summary": "wrote 3 files",
         "output": _lines(60, 60, "out")[:cap]},
    ]


class _Ctx:
    """The three fields `_promote_large_output` reaches through to."""

    def __init__(self, conversation_id: str, turn_id: str) -> None:
        self.job_id = "job_bench"
        self.turn_id = turn_id
        self.conversation_id = conversation_id


def prepared(ctx: _Ctx) -> list[tuple[dict, str]]:
    """Each result with its asset ref promoted, and its formatted text.

    Promotion is run here rather than assumed, because `Ledger` refuses to
    compact anything without a `result_ref` — so a workload that skipped this
    step would measure the bug `bf95b46` fixed instead of the mechanism it
    was fixing.
    """
    from primnox2.tools import runtime
    from primnox2.tools.runtime import _promote_large_output

    out = []
    for result in workload():
        result = dict(result)
        _promote_large_output(result["tool"], result, ctx)
        out.append((result, runtime.format_result(result)))
    return out


def regimes(rows) -> dict[str, tuple[list[str], str]]:
    """The three transcripts, built ONCE.

    Once matters. `result_store.put` deduplicates on content, so calling this
    twice would make the second pass resolve every result to "identical to
    res_… already retrieved" and report a saving that only exists because the
    benchmark ran itself twice.
    """
    from primnox2.tools import observations

    # The threshold that ships as the default: the first ~1,200 tokens of tool
    # output are kept verbatim, so the first large result of a turn is exempt.
    held = observations.Ledger(threshold=observations.COMPACT_AFTER_TOKENS,
                               session="bench-held")
    held_contents = [held.record(text, dict(result)) for result, text in rows]

    # The same ledger with the threshold dropped, which is what `strategy()`
    # now selects for a turn predicted to run long.
    eager = observations.Ledger(threshold=0, session="bench-eager")
    eager_contents = [eager.record(text, dict(result)) for result, text in rows]

    return {
        "verbatim": ([text for _, text in rows], "every result in full"),
        "held": (held_contents,
                   f"threshold {observations.COMPACT_AFTER_TOKENS}, compacted "
                   + (", ".join(held.compacted) or "nothing")
                   + f", {held.stored_but_sent_whole} stored but sent whole"),
        "eager": (eager_contents,
                  "threshold 0, compacted "
                  + (", ".join(eager.compacted) or "nothing")),
    }


# A cache read is billed at roughly a tenth of an input token and a cache
# write at roughly a quarter more than one — the multipliers `bench_api_overhead`
# already uses, kept identical here so the two benchmarks can be read together.
CACHE_READ = 0.10
CACHE_WRITE = 1.25


def billed(preamble: str, contents: list[str], call: str,
           *, cache: str = "none") -> tuple[int, list[int]]:
    """Sum of every prompt the turn sends — not the size of the last one.

    Step k sends the preamble plus every call and result before it, so the
    cost of result 1 is multiplied by the number of steps that follow it.
    That multiplication is the whole finding, and it is why a mechanism that
    shrinks one result by 90% can save more than 90% of a turn.

    Three billing modes, because the difference between the second and the
    third is the entire remaining gap to the target:

        none     everything at one input token, no marker anywhere
        system   only the system block is marked — WHAT SHIPS TODAY. The
                 preamble is read back cheaply, and every tool result is
                 re-sent at full price on every step after it.
        prefix   the marker moves to the end of the conversation each step,
                 so everything already sent reads at a tenth and only what
                 was appended since is written.

    `prefix` is legitimate here and would not be under a different compaction
    design. A prefix cache matches on exact bytes, so a reducer that rewrote
    earlier messages would invalidate the whole prefix and collect a write it
    never reads back. Both mechanisms measured here decide once, at append
    time, and never touch a sent message — which is what lets the cache column
    be added to the compaction column instead of fighting it.
    """
    from primnox2.context.service import estimate_tokens

    head = estimate_tokens(preamble)
    deltas = [head]
    for content in contents:
        deltas.append(estimate_tokens(call) + estimate_tokens(content))

    per_step, prefix = [], 0
    # One call per result, plus the final call that answers with no tool.
    for step in range(len(contents) + 1):
        delta = deltas[step]
        if cache == "prefix":
            cost = prefix * CACHE_READ + delta * CACHE_WRITE
        elif cache == "system":
            # The preamble is written once and read back on every later call;
            # the conversation that grew after it is billed in full each time.
            body = prefix - head if step else 0
            cost = (head * (CACHE_WRITE if step == 0 else CACHE_READ)
                    + body + delta * (0 if step == 0 else 1))
        else:
            cost = prefix + delta
        per_step.append(round(cost))
        prefix += delta
    return sum(per_step), per_step


def main() -> int:
    conversation_id, turn_id = setup()
    from primnox2.context.service import budget_for_model, estimate_tokens
    from primnox2.tools import runtime

    rows = prepared(_Ctx(conversation_id, turn_id))
    promoted = sum(1 for result, _ in rows if result.get("result_ref"))
    built = regimes(rows)
    preamble = runtime.system_prompt() + "\n" + QUESTION
    call = '<tool name="graph_query">{"question": "..."}</tool>'
    budget = budget_for_model()
    order = ("verbatim", "held", "eager")

    print(f"\nWORKLOAD — {len(rows)} steps, "
          f"{sum(estimate_tokens(t) for _, t in rows):,} tokens of tool output")
    print(f"  preamble {estimate_tokens(preamble):,} tokens, "
          f"window {budget:,}, {promoted}/{len(rows)} results promoted to an "
          f"asset")
    print(f"\n  {'step':>4s}  {'tool':22s} {'full':>8s} {'held':>8s} {'eager':>8s}")
    for i, (result, _) in enumerate(rows):
        sizes = [estimate_tokens(built[name][0][i]) for name in order]
        print(f"  {i + 1:4d}  {result['tool']:22s} "
              f"{sizes[0]:8,d} {sizes[1]:8,d} {sizes[2]:8,d}")

    # The ladder, in the order the work actually has to happen. Each rung
    # names what would have to change to stand on it.
    ladder = [
        ("verbatim", "none", "no compaction, no cache — the baseline"),
        ("held", "none", "threshold 1200, no cache"),
        ("held", "system", "WAS SHIPPING — threshold 1200, system block marked"),
        ("eager", "none", "threshold 0, no cache"),
        ("verbatim", "prefix", "prefix cache alone, no compaction"),
        ("eager", "system", "threshold 0, system block only"),
        ("eager", "prefix", "SHIPS NOW — threshold 0 + a moving breakpoint"),
    ]
    totals = {(name, mode): billed(preamble, built[name][0], call, cache=mode)
              for name, mode, _ in ladder}
    base = totals[("verbatim", "none")][0]

    print(f"\nBILLED — every step of the turn, summed. Baseline is verbatim "
          f"with no cache.")
    print(f"  {'regime':10s} {'cache':8s} {'billed':>10s} {'saved':>8s} "
          f"{'last':>9s} {'% window':>9s}  what")
    for name, mode, label in ladder:
        total, per_step = totals[(name, mode)]
        last = per_step[-1]
        print(f"  {name:10s} {mode:8s} {total:10,d} "
              f"{100 * (base - total) / base:7.1f}% {last:8,d}t "
              f"{100 * last / budget:8.1f}%  {label}")

    # The floor. Compaction cannot touch the preamble, which is re-sent on
    # every call, so it bounds what any result-side mechanism can reach —
    # and naming that bound is the difference between a target and a wish.
    calls = len(rows) + 1
    floor = estimate_tokens(preamble) * calls
    print(f"\n  FLOOR — the preamble is re-sent on all {calls} calls: "
          f"{floor:,} tokens, {100 * floor / base:.1f}% of the baseline.")
    print(f"  No result-side mechanism can save more than "
          f"{100 - 100 * floor / base:.1f}% uncached. Reaching {TARGET:.0f}% "
          f"needs the preamble billed as a cache read, or made smaller.")

    saved = {key: 100 * (base - total) / base
             for key, (total, _) in totals.items()}
    today = saved[("held", "system")]
    best = max(saved, key=saved.get)
    verdict = ("MET" if saved[best] >= TARGET
               else f"SHORT BY {TARGET - saved[best]:.1f} points")
    print(f"\n  Was {today:.1f}%. Target {TARGET:.0f}%. Now "
          f"{best[0]}+{best[1]} at {saved[best]:.1f}%. {verdict}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
