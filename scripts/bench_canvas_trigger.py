"""Does Primnox decide to open a Canvas when it should — and stay shut when it shouldn't?

Suite 3 of the 400-test plan, and the one worth building first, because it is
the only one whose pass condition needs no judgement. Every other suite ends in
"is this answer good?"; this one ends in "does a row exist in the workspaces
table?". Ground truth is `workspaces.for_turn(turn_id)`, which is what the tool
actually wrote, not what the reply claimed it wrote.

That distinction is the whole reason this exists. The first probe replied

    "I'll create a project plan document for a todo app as an HTML workspace."

and created nothing. A suite that graded the prose would have scored that a
pass.

WHAT IS MEASURED. Precision and recall are reported separately and neither is
averaged away, because the two failures are not equally bad:

  a false positive  — Canvas opens on "what is 2+2?" — is the UI disease. It is
                      loud, it is instant, and the user sees it every time.
  a false negative  — no Canvas on "write me a report" — is recoverable; the
                      user asks again.

So a run that trades precision for recall has got worse even if accuracy is
flat, and the table below has to be able to show that.

Each case gets its OWN conversation. Sharing one would leak the previous
answer's Canvas into the next decision, which is a real effect (see the
Canvas -> chat transitions at the end) but not the one being isolated here.

Usage:
    python scripts/bench_canvas_trigger.py [--limit N] [--out results.json]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

BASE = "http://127.0.0.1:4109"
SETTLE_TIMEOUT_S = 180
POLL_S = 2.0
# A breath between cases. Free-tier gateways meter on request rate as well as
# volume, and a fifty-case sweep issued back-to-back is what a rate limiter is
# built to stop.
PACE_S = 3.0

# (case_id, group, prompt, canvas_expected)
#
# Groups follow the plan's own sections so the report can show WHERE the
# decision breaks rather than only how often. "borderline" is separated out
# because a wrong answer there is a judgement call, not a defect, and folding
# it into the headline number would make the headline meaningless.
CASES: list[tuple[int, str, str, bool]] = [
    # ── definitely NO canvas ────────────────────────────────────────────────
    (1,  "no-canvas", "What is RAM?", False),
    (2,  "no-canvas", "What is Python?", False),
    (3,  "no-canvas", "Who invented Linux?", False),
    (4,  "no-canvas", "What's 20% of 500?", False),
    (5,  "no-canvas", "Explain recursion.", False),
    (6,  "no-canvas", "Give me 5 ideas for a weekend project.", False),
    (7,  "no-canvas", "Why is the sky blue?", False),
    (8,  "no-canvas", "What's the difference between TCP and UDP?", False),
    (9,  "no-canvas", "Tell me a joke.", False),
    (10, "no-canvas", "Translate 'good morning' into French.", False),
    # ── definitely canvas ───────────────────────────────────────────────────
    (11, "canvas", "Write an essay about the history of the transistor.", True),
    (12, "canvas", "Write a report on our Q3 infrastructure costs.", True),
    (13, "canvas", "Create a research document about sleep and memory.", True),
    (14, "canvas", "Create a project plan for migrating a monolith to services.", True),
    (15, "canvas", "Create a business proposal for a local coffee subscription.", True),
    (16, "canvas", "Create a technical specification for a rate limiter.", True),
    (17, "canvas", "Create an architecture document for an offline-first mobile app.", True),
    (18, "canvas", "Create study notes covering the OSI model.", True),
    (19, "canvas", "Create a presentation outline for a product launch.", True),
    (20, "canvas", "Create a long-form comparison of Postgres, MySQL and SQLite.", True),
    # ── editing intent (needs an existing doc; expect canvas) ───────────────
    (21, "edit-intent", "Rewrite this document to be more concise:\n\n"
                        "# Onboarding\nWe do onboarding. It is a process. "
                        "New people join and then they are onboarded.", True),
    (22, "edit-intent", "Improve this:\n\n# Retro notes\nThings went ok. "
                        "Some bugs. We should do better next time.", True),
    (23, "edit-intent", "Fix this essay:\n\nThe industrial revolution were a "
                        "time of change. It changed things alot.", True),
    (24, "edit-intent", "Expand the security section:\n\n# Design\n"
                        "## Storage\nSQLite.\n## Security\nWe hash passwords.", True),
    (25, "edit-intent", "Shorten this:\n\n# Summary\n" + ("This is a long "
                        "and repetitive sentence about the project. " * 12), True),
    (26, "edit-intent", "Reorganize this:\n\n# Notes\nConclusion: ship it.\n"
                        "Background: we had a problem.\nMethod: we fixed it.", True),
    (27, "edit-intent", "Add a conclusion to this:\n\n# Report\n"
                        "## Findings\nLatency dropped 40% after caching.", True),
    (28, "edit-intent", "Turn this into a report:\n\nlatency down 40%, "
                        "errors down 12%, cost up 3%, users happier", True),
    (29, "edit-intent", "Convert this into notes:\n\nThe meeting covered the "
                        "budget, the hiring plan, and the Q4 roadmap.", True),
    (30, "edit-intent", "Make this professional:\n\nhey so the thing is broken "
                        "again lol, can we just fix it plz", True),
    # ── borderline (reported separately) ────────────────────────────────────
    (31, "borderline", "Explain the OSI model and give me a study guide.", True),
    (32, "borderline", "Explain hash tables and make notes I can revise from.", True),
    (33, "borderline", "Compare React and Svelte and give a recommendation.", False),
    (34, "borderline", "Research the health effects of standing desks.", False),
    (35, "borderline", "Research the health effects of standing desks deeply, "
                       "with sources and sections.", True),
    (36, "borderline", "Analyze this data: Jan 40, Feb 55, Mar 51, Apr 78.", False),
    (37, "borderline", "Summarize this long document:\n\n" + ("The system "
                       "processes events in order and retries on failure. " * 25), False),
    (38, "borderline", "Create an action plan for reducing our AWS bill.", True),
    (39, "borderline", "Brainstorm feature ideas and organize them into themes.", False),
    (40, "borderline", "Explain our architecture and include a diagram.", False),
    # ── conversational transitions (two turns; decision is on turn 2) ───────
    (41, "transition", "put that into a document", True),
    (42, "transition", "make that into a plan", True),
    (43, "transition", "turn that into notes", True),
    (44, "transition", "write the full version", True),
    (45, "transition", "what's the capital of France?", False),
    (46, "transition", "make the second section shorter", True),
    (47, "transition", "why did you structure it that way?", False),
    (48, "transition", "add a section about testing", True),
    (49, "transition", "unrelated question - how do I exit vim?", False),
    (50, "transition", "go back to the document and add a summary", True),
]

# Turn 1 for the `transition` cases: establishes something to refer to.
TRANSITION_PRIMER = ("Explain how a write-ahead log keeps a database durable. "
                     "Two short paragraphs.")


def _post(path: str, payload: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(path: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode())


# `awaiting_input` belongs here even though the turn has not finished: the
# model called `ask_user` and is waiting for a human, which will never arrive
# in a benchmark. Leaving it out cost the full 180s timeout on every case that
# chose to ask — and it is not a timeout, it is an answer. "Write an essay
# about the history of the transistor" came back as a question rather than an
# essay, and that is a decision worth scoring, not an outage worth discarding.
_TERMINAL = ("completed", "failed", "cancelled", "awaiting_input")


def _settle(conversation_id: str, timeout_s: int = SETTLE_TIMEOUT_S) -> dict:
    """Block until the newest turn reaches a state it will not leave on its own."""
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        turns = _get(f"/conversations/{conversation_id}/history").get("turns") or []
        if turns:
            last = turns[-1]
            if last.get("status") in _TERMINAL:
                return last
        time.sleep(POLL_S)
    return {**last, "status": last.get("status") or "timeout"}


def _canvas_for(turn_id: str) -> list[dict]:
    """Ground truth: what the workspace tool actually wrote for this turn."""
    from primnox2.workspaces import service as workspaces
    try:
        return workspaces.for_turn(turn_id) or []
    except Exception:
        return []


def _files_for(turn_id: str) -> int:
    """Files the turn produced — a PDF or a deck is a delivery too.

    Counted separately because scoring ONLY workspaces conflates two opposite
    outcomes. Measured that way, ten cases looked like a near-total failure to
    produce anything; the same ten had in fact produced
    `coffee_subscription_proposal.pdf`, `OSI_Model_Study_Notes.pdf`,
    `product_launch.pptx` and four more. The Canvas decision was wrong, but
    the product was not silent, and a report that cannot tell those apart will
    send somebody to fix the wrong thing.
    """
    from primnox2.storage import db
    try:
        return db.connect().execute(
            "SELECT COUNT(*) n FROM turn_assets WHERE turn_id = ?",
            (turn_id,)).fetchone()["n"]
    except Exception:
        return 0


def _boot_backend_modules() -> None:
    """Open the same database the server is using, read-only for our purposes."""
    import os
    from primnox2 import paths
    from primnox2.storage import db
    home = pathlib.Path(os.getenv("PRIMNOX2_HOME",
                                  pathlib.Path.home() / "Documents" / "Primnox2"))
    paths.configure(home)
    db.configure(home / "primnox.db")


def run_case(case: tuple[int, str, str, bool]) -> dict:
    cid_num, group, prompt, expected = case
    started = time.time()
    conv = _post("/conversations", {"title": f"bench-canvas-{cid_num}"})
    conversation_id = conv["id"]

    # The transition cases only make sense after something exists to point at.
    if group == "transition":
        primer = _post(f"/conversations/{conversation_id}/turns",
                       {"text": TRANSITION_PRIMER})
        _settle(conversation_id)
        del primer

    try:
        turn = _post(f"/conversations/{conversation_id}/turns", {"text": prompt})
    except urllib.error.HTTPError as exc:
        return {"id": cid_num, "group": group, "expected": expected,
                "actual": None, "status": f"http_{exc.code}", "ok": False,
                "seconds": round(time.time() - started, 1)}

    turn_id = turn["turn_id"]
    settled = _settle(conversation_id)
    created = bool(_canvas_for(turn_id))
    status = settled.get("status", "unknown")

    # A turn that "completed" having said nothing is not a decision, it is an
    # outage wearing a decision's clothes. When the gateway's quota expired
    # mid-run, ten no-canvas cases came back `completed` in a uniform 2.0s
    # each — against 4-14s when the provider was alive — and every one was
    # scored a PASS, because "no Canvas" is the right answer for those cases
    # and nobody asked whether a reply existed.
    reply = str((settled.get("assistant_message") or {}).get("text") or "")
    if status == "completed" and not reply.strip() and not created:
        status = "empty_reply"

    # A failed turn is not evidence about the decision either way. Counting it
    # as "chose not to open a Canvas" would credit the router for an outage.
    # `awaiting_input` IS evidence: the model reached a decision point and
    # chose to ask rather than build, which on a "write me an essay" is a
    # refusal to act and belongs in the score.
    gradeable = status in ("completed", "awaiting_input")
    ok = (created == expected) if gradeable else False
    files = _files_for(turn_id)
    return {
        "id": cid_num, "group": group, "prompt": prompt[:60],
        "expected": expected, "actual": created, "status": status,
        "asked": status == "awaiting_input",
        "files": files,
        # What the user actually ended up with, which is a different question
        # from whether the Canvas decision was right.
        "delivered": "canvas" if created else ("file" if files else "nothing"),
        "ok": ok, "seconds": round(time.time() - started, 1),
        "error": (settled.get("error") or {}).get("code") if status == "failed" else None,
    }


def report(rows: list[dict]) -> None:
    graded = [r for r in rows if r["status"] in ("completed", "awaiting_input")]
    broken = [r for r in rows if r["status"] not in ("completed", "awaiting_input")]
    asked = [r for r in graded if r.get("asked")]

    tp = sum(1 for r in graded if r["expected"] and r["actual"])
    fp = sum(1 for r in graded if not r["expected"] and r["actual"])
    fn = sum(1 for r in graded if r["expected"] and not r["actual"])
    tn = sum(1 for r in graded if not r["expected"] and not r["actual"])

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    accuracy = (tp + tn) / len(graded) if graded else float("nan")

    print()
    print("CANVAS TRIGGER - %d cases, %d graded, %d unusable"
          % (len(rows), len(graded), len(broken)))
    print()
    print("  confusion            canvas opened    stayed shut")
    print("    should open        %11d    %11d   <- misses" % (tp, fn))
    print("    should not open    %11d    %11d" % (fp, tn))
    print()
    print("  precision  %6.1f%%   of the Canvases it opened, how many belonged" %
          (precision * 100))
    print("  recall     %6.1f%%   of the Canvases it owed, how many it opened" %
          (recall * 100))
    print("  accuracy   %6.1f%%" % (accuracy * 100))
    print()
    print("  by group")
    for group in ("no-canvas", "canvas", "edit-intent", "borderline", "transition"):
        g = [r for r in graded if r["group"] == group]
        if not g:
            continue
        hit = sum(1 for r in g if r["ok"])
        print("    %-12s %2d/%-2d" % (group, hit, len(g)))

    # Delivery, reported next to the decision and never folded into it. A run
    # can get the Canvas call wrong while still handing the user a document,
    # and the two numbers move independently: widening the skill's triggers
    # took delivery from 4/10 to 8/10 without changing the Canvas rule at all.
    wanted = [r for r in graded if r["expected"]]
    if wanted:
        kinds = {"canvas": 0, "file": 0, "nothing": 0}
        for r in wanted:
            kinds[r["delivered"]] += 1
        print()
        print("  delivery on the %d cases that asked for a document" % len(wanted))
        print("    canvas   %2d   editable workspace" % kinds["canvas"])
        print("    file     %2d   pdf/pptx/docx asset" % kinds["file"])
        print("    nothing  %2d   answered in chat, or nothing at all" % kinds["nothing"])
        print("    -------------")
        print("    delivered %2d/%d" % (kinds["canvas"] + kinds["file"], len(wanted)))

    if asked:
        # Tracked on its own because it is neither a Canvas nor a refusal — the
        # model stopped and asked. On a direct "write me a report" that is a
        # failure to act; on a vague one it may be the right call.
        print()
        print("  asked a question instead of acting: %d" % len(asked))
        for r in asked:
            print("    #%-2d %-11s %s" % (r["id"], r["group"], r["prompt"][:48]))

    wrong = [r for r in graded if not r["ok"]]
    if wrong:
        print()
        print("  wrong decisions")
        for r in wrong:
            direction = "opened, should not have" if r["actual"] else "did not open, should have"
            print("    #%-2d %-11s %-24s %s" % (r["id"], r["group"], direction, r["prompt"][:44]))

    if broken:
        print()
        print("  UNUSABLE - the turn never completed, so the decision was never made")
        for r in broken:
            print("    #%-2d %-10s %s" % (r["id"], r["status"], r.get("error") or ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="run only the first N cases")
    ap.add_argument("--group", default="", help="run only one group")
    ap.add_argument("--out", default="", help="write raw results as JSON")
    args = ap.parse_args()

    try:
        _get("/health", timeout=5)
    except Exception:
        print(f"backend not reachable at {BASE} - start it first")
        return 2
    _boot_backend_modules()

    cases = CASES
    if args.group:
        cases = [c for c in cases if c[1] == args.group]
    if args.limit:
        cases = cases[: args.limit]

    # STOP ON A DEAD PROVIDER. Fifty cases against a quota-limited gateway is
    # how an entire connection gets spent: a 24-hour lockout arrived partway
    # through a sweep, and the run carried on issuing another thirty requests
    # into a 503 while recording them as results. Three consecutive failures
    # is not a flaky turn, it is the endpoint being gone.
    consecutive_failures = 0
    rows: list[dict] = []
    for case in cases:
        row = run_case(case)
        rows.append(row)
        if row["status"] in ("failed", "empty_reply", "timeout", "http_503"):
            consecutive_failures += 1
            if consecutive_failures >= 3:
                print("\n  ABORTED after 3 consecutive failures — the provider "
                      "is not answering.\n  Results below cover only the cases "
                      "that actually ran.", flush=True)
                break
        else:
            consecutive_failures = 0
        time.sleep(PACE_S)
        mark = "ok " if row["ok"] else "MISS"
        print("  %s #%-2d %-11s expected=%-5s actual=%-5s %5.1fs  %s"
              % (mark, row["id"], row["group"], row["expected"],
                 row["actual"], row["seconds"],
                 "" if row["status"] == "completed" else row["status"]),
              flush=True)

    report(rows)
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(f"\n  raw results -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
