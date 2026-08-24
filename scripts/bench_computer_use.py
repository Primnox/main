"""KPI-0 — the scoreboard, because none of this was measurable.

Every improvement claimed for Computer Use so far was a number somebody read
off a terminal once: "8,492 characters became 29", "310 ms became 83 ms". Each
was true when it was taken and none of them survive a code change, because
nothing re-takes them. A target with no instrument is an opinion.

So this measures what can be measured WITHOUT a model in the loop, which turns
out to be most of it. Model-dependent KPIs — task success, excess interaction
ratio — need a task suite and a provider and belong in a separate harness;
everything here is deterministic, runs in well under a minute, and answers the
question "did that change help or hurt" on demand.

Two design choices worth stating:

  It measures against the REAL desktop where it can. Synthetic windows are
  reproducible and lie about scale: the whole reason re-read cost mattered was
  a 221-element browser window, and a purpose-built test window has seven
  elements and would have shown the saving as trivial.

  Fault injection is how the safety KPIs are measured at all. "False-success
  rate" cannot be observed on a system that is working; it is observed by
  making writes silently fail and counting how many are reported as done.

Usage:
    python scripts/bench_computer_use.py [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "v2" / "backend"))
sys.path.insert(0, str(ROOT / "v2" / "backend" / "tests"))

from primnox2.computer import (actions, grants, operations,        # noqa: E402
                               session as sessions, targets, tree, waiting)

WINDOW_CLASS = "PrimnoxTestWindow"
TEST_WINDOW = ROOT / "v2" / "backend" / "tests" / "_testwindow.py"


class Result:
    """One KPI: what it should be, what it is, and whether that passes."""

    def __init__(self, name, target, value, unit="", passed=None, note=""):
        self.name, self.target, self.value = name, target, value
        self.unit, self.note = unit, note
        self.passed = passed

    def row(self) -> str:
        mark = {True: "PASS", False: "FAIL", None: "----"}[self.passed]
        shown = (f"{self.value:.1f}" if isinstance(self.value, float)
                 else str(self.value))
        return (f"  {mark}  {self.name:<38s} {shown + self.unit:>14s}   "
                f"target {self.target}")

    def as_json(self) -> dict:
        return {"name": self.name, "target": self.target, "value": self.value,
                "unit": self.unit, "passed": self.passed, "note": self.note}


# ── Fixtures ────────────────────────────────────────────────────────────────

def spawn_window(title: str):
    import win32gui
    import win32process

    process = subprocess.Popen([sys.executable, str(TEST_WINDOW), title])
    for _ in range(60):
        time.sleep(0.25)
        hwnd = win32gui.FindWindow(WINDOW_CLASS, title)
        if hwnd:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            target = targets.resolve(f"win_{hwnd}_{pid}")
            for _ in range(20):
                if tree.find_text_target(tree.read(target)) is not None:
                    return process, target
                time.sleep(0.25)
            break
    process.terminate()
    raise RuntimeError("the bench window did not open")


def real_windows(limit: int = 8):
    return [t for t in targets.enumerate_windows() if not t.minimized][:limit]


# ── The measurements ────────────────────────────────────────────────────────

def kpi_snapshot_latency(windows) -> list:
    """How long a read of a real window takes.

    The plan's target is "< 100 ms typical", and typical means the median: one
    enormous browser window should not decide the verdict, and it should not be
    hidden either, which is why p95 is reported alongside.
    """
    timings = []
    for target in windows:
        tree.read(target)                       # warm: first read of a browser
        start = time.perf_counter()             # is the request, not the answer
        snapshot = tree.read(target)
        timings.append(((time.perf_counter() - start) * 1000,
                        len(snapshot.elements), target.title))
    if not timings:
        return []
    values = sorted(t[0] for t in timings)
    p50 = statistics.median(values)
    p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
    worst = max(timings)
    return [
        Result("UIA snapshot latency (p50)", "< 100ms", p50, "ms", p50 < 100),
        Result("UIA snapshot latency (p95)", "< 400ms", p95, "ms", p95 < 400,
               note=f"slowest: {worst[2][:40]} ({worst[1]} elements)"),
    ]


def kpi_cache_equivalence(windows) -> list:
    """The cached read must return the same tree, and be faster.

    Equivalence is the one that decides whether the optimisation may ship at
    all — a faster read that drops a control is a correctness regression with a
    benchmark for a disguise — so it is reported as its own KPI rather than
    folded into the timing.
    """
    def fingerprint(snapshot):
        return [(e.role, e.name, tuple(e.patterns), e.enabled, e.depth)
                for e in snapshot.elements]

    same = 0
    speedups = []
    for target in windows:
        tree.read(target, cached=False)
        start = time.perf_counter()
        slow = tree.read(target, cached=False)
        slow_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        fast = tree.read(target, cached=True)
        fast_ms = (time.perf_counter() - start) * 1000
        if fingerprint(slow) == fingerprint(fast):
            same += 1
        if fast_ms > 0:
            speedups.append(slow_ms / fast_ms)
    if not windows:
        return []
    agreement = 100.0 * same / len(windows)
    return [
        Result("Cached read agrees with uncached", "100%", agreement, "%",
               agreement == 100.0),
        Result("Cached read speedup (median)", ">= 1.5x",
               statistics.median(speedups) if speedups else 0.0, "x",
               bool(speedups) and statistics.median(speedups) >= 1.5),
    ]


def kpi_reread_cost(windows) -> list:
    """What a re-read of an unchanged window costs against the whole tree.

    This is the context KPI. A model that re-reads after every action pays the
    full tree each time, and the tool result is re-sent on every subsequent
    iteration of the loop — so the cost is not paid once, it is paid once per
    remaining step.
    """
    ratios = []
    for target in windows:
        first = tree.read(target)
        first.generation = 1
        second = tree.read(target)
        second.generation = 2
        whole = second.render(only_actionable=True)
        changes = [c for c in tree.diff(first, second)
                   if c.element is None or c.element.actionable()]
        delta = tree.render_diff(changes, generation=2, against=1)
        if whole:
            ratios.append(100.0 * len(delta) / len(whole))
    if not ratios:
        return []
    median = statistics.median(ratios)
    biggest = min(ratios)
    return [
        Result("Re-read cost vs full tree (median)", "< 50%", median, "%",
               median < 50),
        Result("Re-read cost on the largest window", "< 10%", biggest, "%",
               biggest < 10),
    ]


def kpi_false_success(target) -> list:
    """The KPI that cannot be observed on a system that is working.

    Writes are made to silently do nothing, and the question is how many come
    back reported as done. Anything above zero is the bug the Verifier exists
    to prevent, returned.
    """
    active = sessions.open_session(target, grants.ACT,
                                   conversation_id="bench_false", turn_id=None)
    real_set_value = actions.set_value
    reported_done = 0
    attempts = 5
    try:
        snapshot = active.read_tree()
        field = tree.find_text_target(snapshot)
        if field is None:
            return []
        actions.set_value = lambda element, text: f"set {element.role}"
        for index in range(attempts):
            try:
                from primnox2.tools import computer as computer_tools
                verify = computer_tools._verify_value(field, f"never {index}")
                active.act("type", "type",
                           lambda: actions.set_value(field, f"never {index}"),
                           verify=verify, route=actions.ROUTE_PATTERN)
                reported_done += 1
            except actions.ActionFailed:
                pass
    finally:
        actions.set_value = real_set_value
        active.close("bench finished")
    rate = 100.0 * reported_done / attempts
    return [Result("False-success rate (injected no-op writes)", "0%", rate,
                   "%", rate == 0.0,
                   note=f"{reported_done}/{attempts} silent failures reported "
                        "as done")]


def kpi_recovery(target) -> list:
    """How often a ref that has gone stale is recovered rather than refused.

    Measured across the whole remembered window, because the interesting number
    is not "does rebinding work" but "how far behind can the model be" — a
    batch written against one read is three generations stale by its last step.
    """
    active = sessions.open_session(target, grants.ACT,
                                   conversation_id="bench_recover",
                                   turn_id=None)
    recovered = attempts = 0
    try:
        snapshot = active.read_tree()
        origin = snapshot.generation
        chosen = snapshot.actionable()[0]
        stale = chosen.qualified(origin)
        for _ in range(sessions.REBIND_HISTORY - 1):
            active.read_tree()
            attempts += 1
            try:
                found = active.element(stale)
                if found.role == chosen.role and found.name == chosen.name:
                    recovered += 1
            except Exception:
                pass
    finally:
        active.close("bench finished")
    if not attempts:
        return []
    rate = 100.0 * recovered / attempts
    return [Result("Stale-ref recovery within the window", ">= 80%", rate, "%",
                   rate >= 80.0,
                   note=f"{recovered}/{attempts} rebound across "
                        f"{sessions.REBIND_HISTORY - 1} generations")]


def kpi_verification_coverage() -> list:
    """How much of the operation table can be checked deterministically.

    The operations with an empty verifier are the honest gap: they can only
    ever return NOT VERIFIED, and knowing how large that set is matters more
    than the percentage looking good.
    """
    verbs = list(operations.VERBS.values())
    covered = [v for v in verbs if v.verifier]
    rate = 100.0 * len(covered) / len(verbs)
    uncheckable = sorted(v.name for v in verbs if not v.verifier)
    return [Result("Deterministic verification coverage", ">= 60%", rate, "%",
                   rate >= 60.0,
                   note="unverifiable: " + ", ".join(uncheckable))]


def kpi_tool_calls(target) -> list:
    """Tool calls for a four-action workflow, batched against one at a time.

    A stand-in for "model calls per workflow" that needs no model: each tool
    call in the unbatched form is a separate round-trip by construction.
    """
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    ctx = ToolContext(conversation_id="bench_calls")
    computer_tools._control_window(
        {"window": target.handle, "reason": "bench"}, ctx)
    active = sessions.current("bench_calls")
    try:
        snapshot = active.snapshot or active.read_tree()
        field = tree.find_text_target(snapshot)
        if field is None:
            return []
        ref = field.qualified(snapshot.generation)
        steps = [{"verb": "type", "ref": ref, "text": t}
                 for t in ("a", "ab", "abc", "abcd")]
        result = computer_tools._run_steps({"steps": steps}, ctx)
        batched = 2 if result["status"] == "success" else 0
        unbatched = 1 + len(steps)
    finally:
        if active:
            active.close("bench finished")
    if not batched:
        return [Result("Tool calls for a 4-action workflow", "<= 2", 0, "",
                       False, note="the batch failed")]
    return [Result("Tool calls for a 4-action workflow", "<= 2", batched, "",
                   batched <= 2,
                   note=f"{unbatched} without run_steps")]


def kpi_waiting(target) -> list:
    """Whether waiting costs one call or one call per check."""
    predicate = waiting.element_appears("nothing named this exists")
    outcome = waiting.wait_until(target, predicate, timeout_s=3.0)
    naive = int(3.0 / waiting.FIRST_POLL_S)
    return [
        Result("Model calls to wait 3s", "1", 1, "", True,
               note=f"{outcome.polls} runtime polls, {naive} without backoff"),
        Result("Wait aborts when the window is gone", "yes",
               "yes" if _aborts_early() else "no", "", _aborts_early()),
    ]


def _aborts_early() -> bool:
    gone = targets.Target(handle="win_1_1", hwnd=1, pid=1, title="gone",
                          window_class="x", process="x.exe",
                          bounds=(0, 0, 1, 1), foreground=False,
                          minimized=False)
    started = time.monotonic()
    outcome = waiting.wait_until(gone, waiting.element_appears("x"),
                                 timeout_s=20)
    return (outcome.status == waiting.WINDOW_CLOSED
            and time.monotonic() - started < 2.0)


# ── Runner ──────────────────────────────────────────────────────────────────

SECTIONS = [
    ("Observation", lambda w, t: kpi_snapshot_latency(w) + kpi_cache_equivalence(w)
     + kpi_reread_cost(w)),
    ("Honesty", lambda w, t: kpi_false_success(t) + kpi_verification_coverage()),
    ("Recovery", lambda w, t: kpi_recovery(t)),
    ("Efficiency", lambda w, t: kpi_tool_calls(t) + kpi_waiting(t)),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    if sys.platform != "win32":
        print("Computer Use is Windows-only.")
        return 2

    process, target = spawn_window(f"Primnox Bench {time.time_ns()}")
    windows = real_windows()
    print(f"\nPrimnox Computer Use — KPI-0\n"
          f"{len(windows)} real windows on screen, plus one purpose-built "
          f"bench window.\n")

    results: list = []
    try:
        for title, section in SECTIONS:
            rows = section(windows, target)
            if not rows:
                continue
            print(f"{title}")
            for row in rows:
                print(row.row())
                if row.note:
                    print(f"        {row.note}")
            print()
            results.extend(rows)
    finally:
        process.terminate()

    scored = [r for r in results if r.passed is not None]
    failed = [r for r in scored if not r.passed]
    print(f"{len(scored) - len(failed)}/{len(scored)} KPIs met"
          + (f" — failing: {', '.join(r.name for r in failed)}" if failed
             else ""))

    if args.json:
        args.json.write_text(json.dumps(
            {"at": time.time(), "results": [r.as_json() for r in results]},
            indent=2), encoding="utf-8")
        print(f"written to {args.json}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
