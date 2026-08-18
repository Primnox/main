"""Module 16 — Failure Injection.

Leaves the database in the states a crash produces — turns mid-flight, jobs
marked running, execution sessions never closed — and then runs the boot sweep
and asks what the user sees afterwards.

WHY THIS IS THE MODULE THAT MATTERS. Everything else assumes the process lives.
A laptop closing mid-reply is not an edge case, it is Tuesday. The failure to
catch here is not a crash but a SILENT one: a turn stuck in `streaming` shows a
spinner that never resolves, and the user's only recourse is to delete the chat.
"""
from __future__ import annotations

import time

from primnox2.chat import turns as chat
from primnox2.storage import db

from ..scoring import CRITICAL, HIGH, ModuleResult

KEY, NAME = "M16", "Failure Injection"
NON_TERMINAL = ("queued", "building_context", "thinking", "streaming", "tool_running")


def run(ctx) -> ModuleResult:
    result = ModuleResult(key=KEY, name=NAME)
    started = time.perf_counter()

    cid = chat.create_conversation("Crucible M16")["id"]
    wounded = []
    for status in NON_TERMINAL:
        tid = chat.create_turn(cid, f"interrupted during {status}")["turn_id"]
        with db.tx() as c:
            c.execute("UPDATE turns SET status=? WHERE id=?", (status, tid))
        wounded.append((tid, status))

    # Jobs abandoned mid-flight, both kinds: an idempotent one that should be
    # requeued and a non-idempotent one that must be failed rather than replayed.
    with db.tx() as c:
        c.execute("UPDATE jobs SET status='running' WHERE turn_id IN "
                  "(SELECT id FROM turns WHERE conversation_id=?)", (cid,))

    before = db.connect().execute(
        "SELECT COUNT(*) n FROM events WHERE conversation_id=?", (cid,)).fetchone()["n"]

    swept = db.sweep_on_boot()

    conn = db.connect()
    stuck = [dict(r) for r in conn.execute(
        "SELECT id, status FROM turns WHERE conversation_id=? AND status NOT IN "
        "('completed','failed','cancelled')", (cid,))]
    running_jobs = conn.execute(
        "SELECT COUNT(*) n FROM jobs WHERE status='running'").fetchone()["n"]
    after = conn.execute(
        "SELECT COUNT(*) n FROM events WHERE conversation_id=?", (cid,)).fetchone()["n"]
    emitted = after - before

    # The sweep must also TELL the client. A database row quietly corrected
    # while the open UI still shows a spinner is not recovery.
    # get_history returns a LIST of turns, not a dict. Worth stating: the HTTP
    # layer wraps it as {"turns": [...]}, so the two surfaces disagree in shape
    # and a caller that moves between them gets an AttributeError.
    history = chat.get_history(cid)
    rows = history if isinstance(history, list) else history.get("turns", [])
    spinner = [t for t in rows if t.get("status") in NON_TERMINAL]

    result.measurements = {
        "turns_wounded": len(wounded),
        "swept": swept,
        "turns_still_non_terminal": len(stuck),
        "jobs_still_running": running_jobs,
        "events_emitted_by_sweep": emitted,
        "history_rows_showing_a_spinner": len(spinner),
    }

    if stuck:
        result.find(
            title=f"{len(stuck)} turns remain non-terminal after the boot sweep",
            severity=CRITICAL, owner="Storage",
            what_happened=(f"States left behind: {sorted({t['status'] for t in stuck})}. "
                           "The UI shows a spinner with nothing behind it."),
            reproduction=("Set turns to each non-terminal status; call "
                          "db.sweep_on_boot(); query for non-terminal turns."),
            probable_cause="The sweep's status list does not cover every state.",
            suggested_fix=("Derive the sweep from the TERMINAL set rather than "
                           "listing states, so a new status is swept by default."),
        )

    if running_jobs:
        result.find(
            title=f"{running_jobs} jobs left in `running` after the sweep",
            severity=HIGH, owner="Scheduler",
            what_happened="Nothing will pick these up; they are invisible zombies.",
            reproduction="Mark jobs running; sweep; count status='running'.",
            probable_cause="The sweep requeues idempotent jobs but misses the rest.",
            suggested_fix="Fail non-idempotent running jobs explicitly.",
        )

    if emitted == 0 and wounded:
        result.find(
            title="The boot sweep corrects the database silently",
            severity=HIGH, owner="Event Bus",
            what_happened=("Turns were moved to a terminal state without emitting "
                           "`turn.failed`. A client open across the restart never "
                           "learns, and keeps its spinner until reload."),
            reproduction="Count events before and after db.sweep_on_boot().",
            probable_cause="The sweep updates rows without going through the bus.",
            suggested_fix=("Emit one event per swept turn inside the same "
                           "transaction as the update."),
        )

    if spinner:
        result.find(
            title=f"{len(spinner)} conversations still render as in-flight",
            severity=HIGH, owner="Frontend Shell",
            what_happened="History returns turns in a non-terminal state after recovery.",
            reproduction="Wound turns, sweep, then read /conversations/{id}/history.",
            probable_cause="History reports the stored status without reconciling.",
            suggested_fix="Treat a non-terminal turn with no live job as failed on read.",
        )

    clean = not stuck and not running_jobs
    result.score(
        correctness=10 if clean else 0,
        consistency=10 if clean else 4,
        recovery=10 if (clean and emitted) else 5 if clean else 0,
        performance=10,
        ux_stability=10 if not spinner else 3,
    )
    result.duration_s = time.perf_counter() - started
    return result
