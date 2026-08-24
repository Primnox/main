"""Where a turn's tokens and milliseconds actually go.

`test_perf_budgets.py` asserts five latencies stay under their limits, which
answers "did anything get worse" and not "what is this costing". This answers
the second question, and the two things it reports are the ones that decide
whether an assistant feels cheap or expensive to run:

  COMPOSITION — how much of the context window is spent before the user has
  said anything. Every fixed block is paid on every turn, and re-sent on every
  iteration of the tool loop, so a block that looks small once is not.

  COLD versus WARM — the perf suite measures a warm process, because by the
  time it runs, earlier tests have started the worker pool. Measured alone,
  first-token latency is 1.8-4.7 seconds against a 400 ms budget, with a
  SCRIPTED model, so none of it is the LLM. Somebody who launches the app and
  types immediately pays that, and no test currently reports it.

Nothing here asserts. It prints, so the numbers can be compared across
changes rather than merely gated.

Usage:
    python scripts/bench_efficiency.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def setup():
    from primnox2 import paths
    from primnox2.storage import db

    root = pathlib.Path(tempfile.mkdtemp(prefix="primnox-efficiency"))
    paths.configure(root)
    db.configure(root / "primnox.db")
    db.init()
    return root


def composition():
    """What a turn costs before the user has typed anything."""
    from primnox2.context import service as context
    from primnox2.memory import service as memory
    from primnox2.settings import tunables
    from primnox2.skills import loader as skills
    from primnox2.tools import runtime

    budget = context.budget_for_model()
    prompt = runtime.system_prompt()

    # Split the prompt into the part that is grammar and rules, and the part
    # that is the tool catalogue — they scale differently. The catalogue grows
    # with every tool added; the rules do not.
    from primnox2.tools.registry import describe_for_prompt
    catalogue = describe_for_prompt()

    # Distinct facts. `remember()` deduplicates by similarity, so storing one
    # sentence twenty times stores it ONCE — an earlier version of this
    # reported the memory block at 22 tokens for that reason.
    for i in range(30):
        memory.remember(f"The user prefers setting number {i} configured "
                        f"the way they described in project {i}")
    memory_block = memory.render_for_prompt()
    memory_tokens = min(context.estimate_tokens(memory_block),
                        tunables.get("context.memory_tokens"))

    rows = [
        ("system prompt (rules + grammar)",
         context.estimate_tokens(prompt) - context.estimate_tokens(catalogue)),
        ("tool catalogue", context.estimate_tokens(catalogue)),
        ("memory block (at 20+ facts)", memory_tokens),
        ("skills index", context.estimate_tokens(skills.index() or "")),
    ]
    fixed = sum(tokens for _, tokens in rows)

    print(f"\nCONTEXT COMPOSITION — budget {budget:,} tokens")
    print(f"  {'block':38s} {'tokens':>8s} {'% budget':>9s}")
    for label, tokens in rows:
        print(f"  {label:38s} {tokens:8,d} {100 * tokens / budget:8.2f}%")
    print(f"  {'-' * 38} {'-' * 8} {'-' * 9}")
    print(f"  {'FIXED OVERHEAD, every turn':38s} {fixed:8,d} "
          f"{100 * fixed / budget:8.2f}%")
    print(f"  {'left for history + the user':38s} {budget - fixed:8,d} "
          f"{100 * (budget - fixed) / budget:8.2f}%")
    print(f"\n  Re-sent on every iteration of the tool loop, so an eight-step "
          f"turn\n  pays roughly {8 * fixed:,} tokens of overhead before any "
          f"content.")
    return fixed, budget


def tool_loop():
    """What a turn ACTUALLY costs once tools are in play.

    The composition table above reports the fixed blocks once, and that is the
    number people quote. It is not the number they are billed. The scheduler
    appends the assistant's tool call and the formatted result to the message
    list and re-sends the WHOLE list on the next iteration, so a turn that
    takes eight steps pays for its own history eight times over.

    Built from the same pieces the scheduler uses — `system_prompt`,
    `format_result`, and the inline-output cap that governs how large a result
    is allowed to be — rather than multiplying the fixed cost by eight and
    calling it an answer.
    """
    from primnox2.context import service as context
    from primnox2.settings import tunables
    from primnox2.tools import runtime

    budget = context.budget_for_model()
    fixed = context.estimate_tokens(runtime.system_prompt())
    user = context.estimate_tokens("read that file and summarise it for me")

    # A result at the inline cap, which is what a tool returning anything
    # substantial actually sends. `_bounded`/`_clip` hold it here.
    cap = tunables.get("tools.inline_output_chars")
    result = runtime.format_result({
        "tool": "read_asset", "status": "success",
        "summary": "read 1 document", "output": "x" * cap})
    call = context.estimate_tokens('<tool name="read_asset">{"asset_id": "a1"}</tool>')
    result_cost = context.estimate_tokens(result)

    print(f"\nTOOL LOOP — what each iteration sends")
    print(f"  inline output cap {cap} chars, so one result is "
          f"~{result_cost:,} tokens")
    print(f"  {'step':>5s} {'sent this step':>15s} {'cumulative':>12s} "
          f"{'% budget':>9s}")

    sent = fixed + user
    cumulative = sent
    print(f"  {1:5d} {sent:14,d}t {cumulative:11,d}t "
          f"{100 * sent / budget:8.2f}%")
    for step in range(2, 9):
        # Each previous step left behind a call and a result.
        sent += call + result_cost
        cumulative += sent
        flag = "  <-- over budget" if sent > budget else ""
        print(f"  {step:5d} {sent:14,d}t {cumulative:11,d}t "
              f"{100 * sent / budget:8.2f}%{flag}")

    print(f"\n  A one-step turn costs {fixed + user:,} tokens. An eight-step "
          f"turn is\n  billed {cumulative:,} — {cumulative / (fixed + user):.1f}x "
          f"— and the last request alone\n  is {100 * sent / budget:.0f}% of "
          f"the window.")
    print(f"\n  `tools.max_steps` caps this at "
          f"{tunables.get('tools.max_steps')} steps, which is the only thing\n"
          f"  standing between a tool loop and the context window.")


def latency():
    """The cold start, which is the only latency a user actually notices.

    An earlier version of this timed `context.build`, `system_prompt` and
    `render_for_prompt` and reported all three under a millisecond — true, and
    useless, because none of them is where the time goes. `test_perf_budgets`
    measures first-token latency at 1.8-4.7 seconds when it runs FIRST in a
    process and passes comfortably when anything else has run before it, with
    a scripted model in both cases. So the cost is the worker pool coming up,
    and it is paid once, by whoever launches the app and types straight away.
    """
    import threading

    from primnox2.kernel import scheduler

    print("\nCOLD START — the worker pool, with no model involved")
    print(f"  {'stage':38s} {'ms':>9s}")

    start = time.perf_counter()
    scheduler.scheduler.start()
    started = (time.perf_counter() - start) * 1000
    print(f"  {'scheduler.start()':38s} {started:8.1f}ms")

    # A worker is only useful once it is actually in its claim loop.
    ready = time.perf_counter()
    for _ in range(500):
        if any(t.is_alive() for t in scheduler.scheduler._threads):
            break
        time.sleep(0.002)
    alive = (time.perf_counter() - ready) * 1000
    print(f"  {'first worker alive':38s} {alive:8.1f}ms")

    print(f"  {'worker threads':38s} "
          f"{len([t for t in scheduler.scheduler._threads if t.is_alive()]):8d}")
    print(f"  {'live threads in process':38s} {threading.active_count():8d}")

    scheduler.scheduler.stop()
    print("\n  Measured against a SCRIPTED model, `test_perf_budgets` puts "
          "first\n  token at 1.8-4.7s when this path is cold and well under "
          "400ms when\n  it is warm. The suite only ever sees warm, because "
          "earlier tests\n  have already started the pool.")


def main() -> int:
    setup()
    fixed, budget = composition()
    tool_loop()
    latency()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
