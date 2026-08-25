"""Working execution state: what the current task is doing, right now.

The transcript records what was said and what tools returned. It is a poor
description of where a task actually stands, and it grows without bound. This
module holds the other thing — a small, append-updated record of the work
itself:

    Task: reduce tool-call cost
    Goal:      cut repeated context transmission
    Done:      ✓ benchmarked 1/2/4/8 steps   ✓ measured cache behaviour
    Current:   → design immutable compaction
    Next:      → integrate state references
    Known:     tool transcripts accumulate superlinearly

A model that can see that does not need the transcript to know what to do
next, which is what makes a long task affordable and an interrupted one
resumable.

Two rules the architecture is explicit about, enforced here rather than left
to the caller:

* **Outcomes are four-valued.** completed, failed, *partial*, and *unknown*.
  A tool that crashed after writing a file did not fail cleanly, and calling
  it "failed" invites a destructive blind retry. :func:`finish` will not
  mark a task complete while anything under it is unfinished.
* **Current intent outranks stale plans.** When the user changes what they
  want, :func:`retarget` drops the pending plan but keeps the observations
  already paid for — the findings are still true even though the goal moved.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from primnox2.context.service import estimate_tokens
from v2 import ids, store
from v2.world_model import ValidationError, project_id

try:  # pragma: no cover - logging is incidental to behaviour
    from logger import get_logger

    log = get_logger("v2.task_state")
except Exception:  # pragma: no cover
    import logging

    log = logging.getLogger("v2.task_state")


# Task-level status. "blocked" is distinct from "failed": it means work
# stopped for a reason outside the task, and resuming is still meaningful.
TASK_STATUSES = {"active", "blocked", "completed", "failed", "partial", "abandoned"}
OPEN_STATUSES = {"active", "blocked"}

# Action-level status. "unknown" is the load-bearing one: it is what an
# action becomes when a tool died mid-flight and nobody has yet checked what
# it actually did to the system.
ACTION_STATUSES = {"pending", "running", "completed", "failed", "partial", "unknown", "skipped"}
UNRESOLVED_ACTIONS = {"pending", "running", "unknown", "partial"}

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id                 TEXT PRIMARY KEY,
        goal               TEXT NOT NULL,
        constraints        TEXT NOT NULL DEFAULT '[]',
        project_id         TEXT,
        session_id         TEXT,
        status             TEXT NOT NULL DEFAULT 'active',
        latest_observation TEXT,
        next_actions       TEXT NOT NULL DEFAULT '[]',
        known              TEXT NOT NULL DEFAULT '[]',
        result_refs        TEXT NOT NULL DEFAULT '[]',
        outcome            TEXT,
        created_at         TEXT NOT NULL,
        updated_at         TEXT NOT NULL,
        finished_at        TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_tasks_open ON tasks(status, updated_at)",
    """
    CREATE TABLE IF NOT EXISTS actions (
        id          TEXT PRIMARY KEY,
        task_id     TEXT NOT NULL,
        sequence    INTEGER NOT NULL,
        description TEXT NOT NULL,
        status      TEXT NOT NULL DEFAULT 'pending',
        detail      TEXT,
        error       TEXT,
        result_ref  TEXT,
        created_at  TEXT NOT NULL,
        started_at  TEXT,
        finished_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_actions_task ON actions(task_id, sequence)",
]


def _init() -> None:
    store.ensure_schema("task_state", _SCHEMA)


def _task_row(row) -> dict:
    out = dict(row)
    for key in ("constraints", "next_actions", "known", "result_refs"):
        try:
            out[key] = json.loads(out[key] or "[]")
        except (TypeError, ValueError):
            out[key] = []
    return out


def _touch_stamp(conn) -> str:
    """A stamp strictly newer than every other task's.

    `open_tasks` orders by `updated_at` alone, so two tasks written inside the
    same clock tick order arbitrarily — and `resume()` then returns whichever
    SQLite happened to pick, which is "continue what I was doing" resuming the
    wrong task. Reproduced at roughly one run in ten: start a second task, then
    observe the first, and both land on the same `utc_now()` value.

    Bumping past the current maximum rather than adding a tiebreak column keeps
    the ordering inside the index that already exists (idx_tasks_open), and
    makes "most recently touched" true by construction instead of by timer
    resolution. The stamps stay ISO-8601 and therefore still sort
    lexicographically, which is the property `utc_now()` exists to provide.
    """
    now = store.utc_now()
    row = conn.execute("SELECT MAX(updated_at) AS newest FROM tasks").fetchone()
    newest = (row["newest"] if row is not None else None) or ""
    if now > newest:
        return now
    try:
        return (datetime.fromisoformat(newest) + timedelta(microseconds=1)).isoformat()
    except ValueError:                                        # pragma: no cover
        # Unparseable stamp from some older write — appending still sorts after
        # it, which is all the ordering needs.
        return newest + "1"


def _touch(conn, task_id: str) -> None:
    conn.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (_touch_stamp(conn), task_id))


# ── Lifecycle ────────────────────────────────────────────────────────────────


def start(
    goal: str,
    *,
    constraints: list[str] | None = None,
    project: str | None = None,
    session: str | None = None,
    plan: list[str] | None = None,
) -> dict:
    """Open a task. `plan` seeds the pending actions, in order."""
    if not goal or not goal.strip():
        raise ValidationError("a task needs a goal")
    _init()

    now = store.utc_now()
    task_id = ids.new_id("task")
    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, goal, constraints, project_id, session_id, status,
                               latest_observation, next_actions, known, result_refs, outcome,
                               created_at, updated_at, finished_at)
            VALUES (?,?,?,?,?, 'active', NULL, '[]', '[]', '[]', NULL, ?, ?, NULL)
            """,
            (task_id, goal.strip(), json.dumps(list(constraints or [])),
             project_id(project), session, now, now),
        )
        for index, description in enumerate(plan or []):
            conn.execute(
                """
                INSERT INTO actions (id, task_id, sequence, description, status, created_at)
                VALUES (?,?,?,?, 'pending', ?)
                """,
                (ids.new_id("event"), task_id, index, description, now),
            )
    return get(task_id)


def get(task_id: str) -> dict | None:
    """A task with its actions attached, or None."""
    _init()
    conn = store.connect()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    task = _task_row(row)
    task["actions"] = [
        dict(a)
        for a in conn.execute(
            "SELECT * FROM actions WHERE task_id = ? ORDER BY sequence ASC", (task_id,)
        ).fetchall()
    ]
    return task


def open_tasks(*, project: str | None = None, session: str | None = None, limit: int = 20) -> list[dict]:
    """Unfinished tasks, most recently touched first."""
    _init()
    clauses = [f"status IN ({','.join('?' * len(OPEN_STATUSES))})"]
    params: list = sorted(OPEN_STATUSES)
    if project is not None:
        clauses.append("project_id = ?")
        params.append(project_id(project))
    if session is not None:
        clauses.append("session_id = ?")
        params.append(session)
    params.append(limit)
    rows = store.connect().execute(
        f"SELECT id FROM tasks WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [get(r["id"]) for r in rows]


def resume(*, project: str | None = None, session: str | None = None) -> dict | None:
    """The task to continue — the most recently touched unfinished one.

    This is what "continue what I was doing" resolves against. Note the
    difference from "the last thing discussed": a conversation can wander
    away from an unfinished task without finishing it, and the task is what
    the user meant.
    """
    found = open_tasks(project=project, session=session, limit=1)
    return found[0] if found else None


# ── Actions ──────────────────────────────────────────────────────────────────


def add_action(task_id: str, description: str, *, status: str = "pending") -> dict:
    """Append an action to a task's plan."""
    if status not in ACTION_STATUSES:
        raise ValidationError(f"unknown action status {status!r}; known: {sorted(ACTION_STATUSES)}")
    _init()
    now = store.utc_now()
    action_id = ids.new_id("event")
    with store.transaction() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(sequence), -1) AS seq FROM actions WHERE task_id = ?", (task_id,)
        ).fetchone()
        conn.execute(
            """
            INSERT INTO actions (id, task_id, sequence, description, status, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (action_id, task_id, row["seq"] + 1, description, status, now),
        )
        _touch(conn, task_id)
    return get_action(action_id)


def get_action(action_id: str) -> dict | None:
    _init()
    row = store.connect().execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    return dict(row) if row else None


def set_action(
    action_id: str,
    status: str,
    *,
    detail: str | None = None,
    error: str | None = None,
    result_ref: str | None = None,
) -> dict | None:
    """Record what happened to an action.

    `result_ref` points into the result store, so an action can carry the
    evidence of what it did without carrying the output itself.
    """
    if status not in ACTION_STATUSES:
        raise ValidationError(f"unknown action status {status!r}; known: {sorted(ACTION_STATUSES)}")
    _init()
    now = store.utc_now()
    finished = None if status in {"pending", "running"} else now
    started = now if status == "running" else None
    with store.transaction() as conn:
        cur = conn.execute(
            """
            UPDATE actions
               SET status = ?,
                   detail = COALESCE(?, detail),
                   error = COALESCE(?, error),
                   result_ref = COALESCE(?, result_ref),
                   started_at = COALESCE(started_at, ?),
                   finished_at = ?
             WHERE id = ?
            """,
            (status, detail, error, result_ref, started, finished, action_id),
        )
        if cur.rowcount:
            row = conn.execute("SELECT task_id FROM actions WHERE id = ?", (action_id,)).fetchone()
            _touch(conn, row["task_id"])
    return get_action(action_id)


def complete_action(action_id: str, *, detail: str | None = None, result_ref: str | None = None):
    return set_action(action_id, "completed", detail=detail, result_ref=result_ref)


def fail_action(action_id: str, error: str, *, result_ref: str | None = None):
    return set_action(action_id, "failed", error=error, result_ref=result_ref)


def partial_action(action_id: str, detail: str, *, result_ref: str | None = None):
    """An action that did some of what it meant to — the honest middle case."""
    return set_action(action_id, "partial", detail=detail, result_ref=result_ref)


def unknown_action(action_id: str, reason: str):
    """An action whose real-world effect is not known.

    What a crashed tool leaves behind. The next step is to look at the actual
    system, not to retry blindly — a retry of a half-finished write is how
    "recovery" becomes data loss.
    """
    return set_action(action_id, "unknown", error=reason)


def verify(task_id: str, verifier) -> list[dict]:
    """Re-check completed/unknown actions against the real system.

    `verifier(action)` returns True (it really happened), False (it did not)
    or None (cannot tell). This is the resumption step the architecture asks
    for: state says A and B completed, so check A and B against the
    filesystem before carrying on to C.
    """
    task = get(task_id)
    if task is None:
        return []
    changed: list[dict] = []
    for action in task["actions"]:
        if action["status"] not in {"completed", "unknown", "partial"}:
            continue
        try:
            outcome = verifier(action)
        except Exception as exc:
            log.warning("verifier raised for action %s (%s)", action["id"], exc)
            outcome = None
        if outcome is True and action["status"] != "completed":
            changed.append(set_action(action["id"], "completed", detail="verified against the system"))
        elif outcome is False and action["status"] != "pending":
            changed.append(set_action(action["id"], "pending", detail="not present on the system; will redo"))
        elif outcome is None and action["status"] == "completed":
            changed.append(set_action(action["id"], "unknown", error="could not be verified"))
    return changed


# ── State updates ────────────────────────────────────────────────────────────


def observe(task_id: str, observation: str, *, result_ref: str | None = None) -> dict | None:
    """Record the latest observation, and the result it came from."""
    _init()
    with store.transaction() as conn:
        row = conn.execute("SELECT result_refs FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        try:
            refs = json.loads(row["result_refs"] or "[]")
        except (TypeError, ValueError):
            refs = []
        if result_ref and result_ref not in refs:
            refs.append(result_ref)
        conn.execute(
            "UPDATE tasks SET latest_observation = ?, result_refs = ?, updated_at = ? WHERE id = ?",
            (observation, json.dumps(refs), _touch_stamp(conn), task_id),
        )
    return get(task_id)


def learn(task_id: str, fact: str) -> dict | None:
    """Attach something worth carrying forward within this task.

    Deliberately not durable memory: a task-local finding ("the failure only
    reproduces with the cache warm") is useful now and may never be worth
    keeping. Promoting it into the world model is a separate, explicit act.
    """
    _init()
    with store.transaction() as conn:
        row = conn.execute("SELECT known FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        try:
            known = json.loads(row["known"] or "[]")
        except (TypeError, ValueError):
            known = []
        if fact not in known:
            known.append(fact)
        conn.execute(
            "UPDATE tasks SET known = ?, updated_at = ? WHERE id = ?",
            (json.dumps(known), _touch_stamp(conn), task_id),
        )
    return get(task_id)


def set_next(task_id: str, actions: list[str]) -> dict | None:
    """Replace the candidate next actions."""
    _init()
    with store.transaction() as conn:
        conn.execute(
            "UPDATE tasks SET next_actions = ?, updated_at = ? WHERE id = ?",
            (json.dumps(list(actions)), _touch_stamp(conn), task_id),
        )
    return get(task_id)


def retarget(
    task_id: str,
    *,
    goal: str | None = None,
    constraints: list[str] | None = None,
    drop_pending: bool = True,
) -> dict | None:
    """Change what the task is for, when the user changes their mind.

    "Actually, don't refactor it — just find the bug" invalidates the plan,
    not the findings. Pending actions are skipped (recorded as skipped, not
    deleted, so the record shows the plan changed); completed work and
    observations are kept, because they were paid for and are still true.
    """
    _init()
    with store.transaction() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        existing = _task_row(row)
        merged = existing["constraints"] + [c for c in (constraints or []) if c not in existing["constraints"]]
        conn.execute(
            "UPDATE tasks SET goal = ?, constraints = ?, next_actions = '[]', updated_at = ? WHERE id = ?",
            (goal.strip() if goal else existing["goal"], json.dumps(merged), _touch_stamp(conn), task_id),
        )
        if drop_pending:
            conn.execute(
                """
                UPDATE actions SET status = 'skipped', detail = 'superseded by a change of goal',
                                   finished_at = ?
                 WHERE task_id = ? AND status IN ('pending', 'running')
                """,
                (store.utc_now(), task_id),
            )
    return get(task_id)


def finish(task_id: str, status: str | None = None, *, outcome: str | None = None) -> dict | None:
    """Close a task, deriving an honest status when none is given.

    Left to derive, the status follows the actions: anything failed makes it
    partial (or failed, if nothing succeeded at all), anything still
    unresolved makes it partial, and only an all-clear makes it completed.
    An explicitly passed "completed" is refused while unresolved work
    remains — reporting a task done when part of it never ran is the failure
    mode this guards against.
    """
    task = get(task_id)
    if task is None:
        return None

    actions = task["actions"]
    failed = [a for a in actions if a["status"] == "failed"]
    unresolved = [a for a in actions if a["status"] in UNRESOLVED_ACTIONS]
    succeeded = [a for a in actions if a["status"] == "completed"]

    if status is None:
        if failed and not succeeded:
            status = "failed"
        elif failed or unresolved:
            status = "partial"
        else:
            status = "completed"
    elif status == "completed" and (failed or unresolved):
        raise ValidationError(
            f"task {task_id} cannot be completed: "
            f"{len(failed)} failed and {len(unresolved)} unresolved action(s) remain"
        )
    elif status not in TASK_STATUSES:
        raise ValidationError(f"unknown task status {status!r}; known: {sorted(TASK_STATUSES)}")

    with store.transaction() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, outcome = ?, finished_at = ?, updated_at = ? WHERE id = ?",
            (status, outcome, store.utc_now(), _touch_stamp(conn), task_id),
        )
    return get(task_id)


# ── Reading state back ───────────────────────────────────────────────────────


def tried(task_id: str) -> dict:
    """What has already been attempted, and how it went.

    Answers "what have you tried?" from the record rather than from a reread
    of the transcript, and keeps a loop from re-running an approach that has
    already failed.
    """
    task = get(task_id)
    if task is None:
        return {"succeeded": [], "failed": [], "unresolved": []}
    return {
        "succeeded": [a["description"] for a in task["actions"] if a["status"] == "completed"],
        "failed": [
            {"action": a["description"], "error": a["error"]}
            for a in task["actions"]
            if a["status"] == "failed"
        ],
        "unresolved": [
            {"action": a["description"], "status": a["status"], "detail": a["detail"] or a["error"]}
            for a in task["actions"]
            if a["status"] in UNRESOLVED_ACTIONS
        ],
    }


def next_step(task_id: str) -> dict | None:
    """The first unresolved action — where to pick the task back up.

    Unknown and partial outcomes come first: something whose real effect is
    in doubt has to be settled before new work is layered on top of it.
    """
    task = get(task_id)
    if task is None:
        return None
    for wanted in ("unknown", "partial", "running", "pending"):
        for action in task["actions"]:
            if action["status"] == wanted:
                return action
    return None


def snapshot(task_id: str) -> dict | None:
    """A compact, structured view of the task for context construction."""
    task = get(task_id)
    if task is None:
        return None
    attempted = tried(task_id)
    upcoming = next_step(task_id)
    return {
        "task_id": task["id"],
        "goal": task["goal"],
        "constraints": task["constraints"],
        "status": task["status"],
        "completed": attempted["succeeded"],
        "failed": attempted["failed"],
        "unresolved": attempted["unresolved"],
        "known": task["known"],
        "latest_observation": task["latest_observation"],
        "next": upcoming["description"] if upcoming else None,
        "next_candidates": task["next_actions"],
        "result_refs": task["result_refs"],
    }


def render(task_id: str, *, max_items: int = 6) -> str:
    """Render the task state as the compact block a prompt should carry.

    Small on purpose: this is what replaces the execution transcript, so it
    has to stay a fraction of the size of what it replaces. Lists are capped
    and the overflow is counted rather than shown.
    """
    state = snapshot(task_id)
    if state is None:
        return ""

    def bullets(items: list, marker: str) -> list[str]:
        shown = items[:max_items]
        lines = [f"  {marker} {item}" for item in shown]
        if len(items) > len(shown):
            lines.append(f"  … {len(items) - len(shown)} more")
        return lines

    out = [f"Task: {state['goal']}", f"Status: {state['status']}"]
    if state["constraints"]:
        out.append("Constraints:")
        out += bullets(state["constraints"], "·")
    if state["completed"]:
        out.append("Completed:")
        out += bullets(state["completed"], "✓")
    if state["failed"]:
        out.append("Failed:")
        out += bullets([f"{f['action']} — {f['error']}" for f in state["failed"]], "✗")
    if state["unresolved"]:
        out.append("Unresolved:")
        out += bullets(
            [f"{u['action']} [{u['status']}]" for u in state["unresolved"]], "?"
        )
    if state["known"]:
        out.append("Known:")
        out += bullets(state["known"], "·")
    if state["latest_observation"]:
        out.append(f"Latest: {state['latest_observation']}")
    if state["next"]:
        out.append(f"Next: → {state['next']}")
    if state["result_refs"]:
        out.append(f"Results: {', '.join(state['result_refs'][:max_items])}")
    return "\n".join(out)


def render_tokens(task_id: str) -> int:
    """Estimated token cost of the rendered state block."""
    return estimate_tokens(render(task_id))


# ── Deletion ─────────────────────────────────────────────────────────────────


def forget_session(session: str) -> int:
    """Delete tasks (and their actions) recorded under a session."""
    _init()
    with store.transaction() as conn:
        rows = conn.execute("SELECT id FROM tasks WHERE session_id = ?", (session,)).fetchall()
        for row in rows:
            conn.execute("DELETE FROM actions WHERE task_id = ?", (row["id"],))
        return conn.execute("DELETE FROM tasks WHERE session_id = ?", (session,)).rowcount


def purge_project(project: str) -> dict:
    """Delete a project's tasks and their actions."""
    _init()
    scope = project_id(project)
    with store.transaction() as conn:
        rows = conn.execute("SELECT id FROM tasks WHERE project_id = ?", (scope,)).fetchall()
        actions = 0
        for row in rows:
            actions += conn.execute("DELETE FROM actions WHERE task_id = ?", (row["id"],)).rowcount
        tasks = conn.execute("DELETE FROM tasks WHERE project_id = ?", (scope,)).rowcount
    return {"project_id": scope, "tasks_deleted": tasks, "actions_deleted": actions}
