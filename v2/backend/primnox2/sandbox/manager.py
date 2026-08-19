"""Execution sessions — the Sandbox Manager's public surface.

One call, `execute()`, drives the whole lifecycle:

    validate manifest → create session → snapshot → run → snapshot → diff
    → persist → emit → clean up

Every stage emits an event on the same bus chat uses, so the frontend renders
execution the way it already renders tokens. There is no separate execution
channel and no special-case client logic (CRS §12.5).

A Turn may own several execution sessions — Python, then shell, then another
Python — which is why the session is its own object rather than a field on the
job. The job says what to do; the session records what happened.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from ..ids import new_id
from ..kernel.events import bus
from ..storage import db
from . import permissions, snapshots, supervisor, workspace

EXEC = "exec"

# Kept inline in the database and the event payload. Anything larger is
# written to the session's logs directory and referenced instead (CRS §6.2.4:
# events are not a blob store).
INLINE_OUTPUT_CHARS = 8000

now_ms = lambda: int(time.time() * 1000)

# Enough to hold any plausible generated script without letting a runaway
# payload bloat the row.
MAX_RECORDED_CODE = 100_000


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= INLINE_OUTPUT_CHARS:
        return text, False
    return text[:INLINE_OUTPUT_CHARS] + "\n… output truncated …", True


class ExecutionSession:
    """One run. Addressable, cancellable, and durable across a crash."""

    def __init__(self, *, runtime: str, manifest: permissions.Manifest,
                 job_id: str | None = None, turn_id: str | None = None,
                 conversation_id: str | None = None, code: str = "") -> None:
        self.id = new_id(EXEC)
        self.runtime = runtime
        # Kept so a surprising result can be traced back to its cause. Without
        # it a run that produced a nearly empty document could not be blamed on
        # the model or on the parser — there was nothing to look at.
        self.code = code
        self.manifest = manifest
        self.job_id = job_id
        self.turn_id = turn_id
        self.conversation_id = conversation_id
        self.directory: Path | None = None
        self.ephemeral = True

    # ── events ───────────────────────────────────────────────────────────
    def emit(self, kind: str, payload: dict) -> None:
        """Conversation scope when the session belongs to one, ambient
        otherwise — a watch-folder ingest has no conversation to name."""
        payload = {"execution_id": self.id, **payload}
        if self.conversation_id:
            bus.emit(kind, payload, conversation_id=self.conversation_id, turn_id=self.turn_id)
        else:
            bus.emit(kind, payload, scope="ambient")

    # ── persistence ──────────────────────────────────────────────────────
    def _insert(self) -> None:
        with db.tx() as c:
            c.execute(
                "INSERT INTO execution_sessions"
                " (id,job_id,turn_id,workspace_id,runtime,manifest,status,session_dir,code,created_at)"
                " VALUES (?,?,?,?,?,?, 'created', ?,?,?)",
                (self.id, self.job_id, self.turn_id, self.manifest.workspace_id,
                 self.runtime, json.dumps(self.manifest.to_dict()),
                 str(self.directory) if self.directory else None,
                 (self.code or "")[:MAX_RECORDED_CODE], now_ms()),
            )

    def _update(self, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        with db.tx() as c:
            c.execute(f"UPDATE execution_sessions SET {cols} WHERE id=?",
                      (*fields.values(), self.id))


def execute(
    *,
    code: str,
    runtime: str = "python",
    manifest: permissions.Manifest | None = None,
    job_id: str | None = None,
    turn_id: str | None = None,
    conversation_id: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
    keep_workspace: bool = False,
) -> dict:
    """Run code under the Sandbox Manager and return a structured result.

    `should_cancel` is polled while the process runs (CRS §9.2). Cancellation
    kills the process tree; whatever it wrote to disk before dying is still
    snapshotted, because a stopped execution is not a reason to throw away
    what it produced.
    """
    manifest = manifest or permissions.manifest_for(runtime)
    session = ExecutionSession(
        runtime=runtime, manifest=manifest, code=code,
        job_id=job_id, turn_id=turn_id, conversation_id=conversation_id,
    )

    # The Kernel validates the manifest before anything launches.
    errors = permissions.validate(manifest)
    if errors:
        session.directory = None
        session._insert()
        session._update(status="failed", error="; ".join(errors), finished_at=now_ms())
        session.emit("sandbox.failed", {"reason": "invalid_manifest", "errors": errors})
        return _result(session, ok=False, error="; ".join(errors), code="invalid_manifest")

    directory, ephemeral = workspace.resolve(session.id, manifest.workspace_id)
    session.directory, session.ephemeral = directory, ephemeral
    session._insert()

    try:
        workspace.install_helpers(directory, runtime)
        workspace.write_script(directory, runtime, code)
    except (OSError, ValueError) as exc:
        session._update(status="failed", error=str(exc), finished_at=now_ms())
        session.emit("sandbox.failed", {"reason": "workspace_unavailable", "message": str(exc)})
        return _result(session, ok=False, error=str(exc), code="workspace_unavailable")

    session.emit("sandbox.created", {
        "runtime": runtime,
        "manifest": manifest.to_dict(),
        "summary": manifest.describe(),
        "ephemeral": ephemeral,
    })

    before = snapshots.snapshot(directory)
    session._update(status="running", started_at=now_ms())
    session.emit("sandbox.progress", {"phase": "running"})

    result = supervisor.run(
        directory, runtime, manifest,
        on_stdout=lambda line: session.emit("sandbox.stdout", {"line": line}),
        on_stderr=lambda line: session.emit("sandbox.stderr", {"line": line}),
        should_cancel=should_cancel,
    )

    # Snapshot even on failure: a script that crashed halfway still changed
    # files, and hiding that is how a "failed" execution silently leaves a
    # half-written tree behind.
    after = snapshots.snapshot(directory)
    changes = snapshots.diff(before, after)

    # Files an execution produced become assets, so the user can actually open
    # them. Without this the only way to reach a generated PDF is to be told a
    # filesystem path and go digging — which is the same as not producing it.
    artifacts = _register_artifacts(session, directory, changes)
    session.emit("sandbox.snapshot", {
        "changes": changes,
        "summary": snapshots.summarize(changes),
        "artifacts": artifacts,
    })

    _write_logs(directory, result)
    stdout, out_clipped = _clip(result.stdout)
    stderr, err_clipped = _clip(result.stderr)

    status = _status_for(result)
    session._update(
        status=status, backend=result.backend, exit_code=result.exit_code,
        stdout=stdout, stderr=stderr, snapshot=json.dumps(changes),
        error=result.error, finished_at=now_ms(),
    )

    payload = {
        "status": status, "exit_code": result.exit_code, "backend": result.backend,
        "duration_ms": result.duration_ms, "changes": changes,
        "stdout": stdout, "stderr": stderr,
        "truncated": out_clipped or err_clipped or result.truncated,
    }
    if status == "completed":
        session.emit("sandbox.completed", payload)
    else:
        session.emit("sandbox.failed", {**payload, "reason": _reason_for(result)})

    # An ephemeral directory that produced nothing is destroyed. One that did
    # is kept, so "accept or revert" has something to act on.
    destroyed = False
    if ephemeral and not keep_workspace and snapshots.is_empty(changes):
        destroyed = workspace.destroy(directory)
        if destroyed:
            session._update(status="destroyed" if status == "completed" else status)
            session.emit("sandbox.destroyed", {"reason": "no_changes"})

    return _result(
        session, ok=(status == "completed"), stdout=stdout, stderr=stderr,
        exit_code=result.exit_code, changes=changes, backend=result.backend,
        duration_ms=result.duration_ms, error=result.error,
        code=None if status == "completed" else _reason_for(result),
        destroyed=destroyed,
    )


def _status_for(r: supervisor.ExecResult) -> str:
    if r.cancelled:
        return "cancelled"
    if r.success:
        return "completed"
    return "failed"


def _reason_for(r: supervisor.ExecResult) -> str:
    if r.cancelled:
        return "cancelled_by_user"
    if r.timed_out:
        return "timeout"
    if r.error:
        return "sandbox_unavailable" if "isolation backend" in r.error else "launch_failed"
    return "nonzero_exit"


# Files larger than this stay on disk and are referenced by path only. Copying
# a multi-gigabyte artifact into the content-addressed store would cost more
# than it buys.
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def _register_artifacts(session: "ExecutionSession", directory: Path,
                        changes: dict) -> list[dict]:
    """Turn files this execution wrote into openable assets."""
    from ..assets import service as assets  # local: avoids an import cycle

    out: list[dict] = []
    for rel in (changes.get("created", []) + changes.get("modified", [])):
        path = directory / rel
        try:
            if not path.is_file() or path.stat().st_size > MAX_ARTIFACT_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        try:
            asset = assets.ingest_bytes(
                data, Path(rel).name, source="tool_output",
                conversation_id=session.conversation_id, turn_id=session.turn_id,
            )
        except Exception:
            # A failed registration must never fail an execution that already
            # produced the file.
            continue
        out.append({"asset_id": asset["id"], "name": Path(rel).name,
                    "path": rel, "bytes": len(data)})
    return out


def _write_logs(directory: Path, r: supervisor.ExecResult) -> None:
    """Full streams to disk, so truncation in the event payload never loses them."""
    try:
        logs = directory / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        if r.stdout:
            (logs / "stdout.log").write_text(r.stdout, encoding="utf-8", errors="replace")
        if r.stderr:
            (logs / "stderr.log").write_text(r.stderr, encoding="utf-8", errors="replace")
    except OSError:
        # Losing the log file must not fail an execution that already ran.
        pass


def _result(session: ExecutionSession, *, ok: bool, **extra) -> dict:
    return {
        "execution_id": session.id,
        "ok": ok,
        "runtime": session.runtime,
        "workspace": str(session.directory) if session.directory else None,
        **extra,
    }


# ── recovery ─────────────────────────────────────────────────────────────────
def sweep_on_boot() -> int:
    """A session still marked running is a process that outlived the runtime.

    Its OS process is gone with the old interpreter, so the row is the only
    thing left to correct (CRS §10.3).
    """
    with db.tx() as c:
        return c.execute(
            "UPDATE execution_sessions SET status='failed',"
            "       error='interrupted by shutdown', finished_at=?"
            " WHERE status IN ('created','running')",
            (now_ms(),),
        ).rowcount


def get(execution_id: str) -> dict | None:
    row = db.connect().execute(
        "SELECT * FROM execution_sessions WHERE id=?", (execution_id,)
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["manifest"] = json.loads(d["manifest"]) if d["manifest"] else {}
    d["snapshot"] = json.loads(d["snapshot"]) if d["snapshot"] else None
    return d


def for_turn(turn_id: str) -> list[dict]:
    rows = db.connect().execute(
        "SELECT id, runtime, status, exit_code, backend, created_at, finished_at"
        "  FROM execution_sessions WHERE turn_id=? ORDER BY created_at",
        (turn_id,),
    )
    return [dict(r) for r in rows]
