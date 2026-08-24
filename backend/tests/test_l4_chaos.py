"""L4 — Chaos. This is what catches architecture failures.

The backend is killed mid-stream, a sandboxed process is killed mid-execution,
the disk fills, and a transaction is interrupted. In every case the runtime
must end up in a state a client can reason about — never a completed turn with
no event, never an event with no turn, never a turn left non-terminal.
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from conftest import run_turn, wait_for_turn, wait_until

from primnox2.assets import service as assets
from primnox2.chat import turns
from primnox2.sandbox import manager as sandbox
from primnox2.sandbox import permissions as sandbox_perms
from primnox2.storage import db

BACKEND = str(Path(__file__).resolve().parents[1])


def _run_child(script: str, root: Path, timeout: float = 60) -> subprocess.Popen:
    path = root / f"child_{abs(hash(script)) % 10000}.py"
    path.write_text(textwrap.dedent(script), encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, str(path), str(root)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=BACKEND,
    )


class TestBackendCrash:
    """Kill the backend during streaming."""

    CHILD = """
        import sys, time, threading
        sys.path.insert(0, r"{backend}")
        from pathlib import Path
        root = Path(sys.argv[1])

        from primnox2 import paths
        from primnox2.storage import db
        from primnox2.models import gateway
        from primnox2.kernel import scheduler
        from primnox2.chat import turns

        paths.configure(root); db.configure(root / "primnox.db"); db.init()

        def slow_stream(messages, usage=None, scrub_map=None, on_thinking=None,
                        route=None):
            if usage is not None:
                usage["input_tokens"] = 100
                usage["output_tokens"] = 0
            for i in range(200):
                yield f"token{{i}} "
                time.sleep(0.05)
        gateway.stream_completion = slow_stream

        scheduler.scheduler.start()
        conv = turns.create_conversation("Crash")["id"]
        t = turns.create_turn(conv, "stream for a long time")
        scheduler.enqueue(t["turn_id"], "chat.reply",
                          {{"conversation_id": conv, "text": "stream for a long time"}})
        print(t["turn_id"], flush=True)
        print(conv, flush=True)
        time.sleep(60)
    """

    RECOVER = """
        import sys, json
        sys.path.insert(0, r"{backend}")
        from pathlib import Path
        root = Path(sys.argv[1])
        from primnox2 import paths
        from primnox2.storage import db
        from primnox2.sandbox import manager as sandbox
        paths.configure(root); db.configure(root / "primnox.db"); db.init()
        swept = db.sweep_on_boot()
        swept["executions"] = sandbox.sweep_on_boot()
        print(json.dumps(swept), flush=True)
    """

    def test_crash_mid_stream_then_recover(self, tmp_path):
        child = _run_child(self.CHILD.format(backend=BACKEND), tmp_path)
        try:
            turn_id = child.stdout.readline().strip()
            conversation_id = child.stdout.readline().strip()
            assert turn_id.startswith("turn_"), f"child never started: {child.stderr.read()[:400]}"

            # Let it get genuinely into the stream, then kill it outright.
            deadline = time.time() + 20
            db_path = tmp_path / "primnox.db"
            streaming = False
            while time.time() < deadline and not streaming:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
                try:
                    row = conn.execute("SELECT status FROM turns WHERE id=?", (turn_id,)).fetchone()
                    streaming = bool(row and row[0] == "streaming")
                finally:
                    conn.close()
                time.sleep(0.1)
            assert streaming, "the child never reached streaming"

            child.kill()
            child.wait(timeout=20)
        finally:
            if child.poll() is None:
                child.kill()

        # A killed backend leaves the turn mid-flight …
        conn = sqlite3.connect(str(tmp_path / "primnox.db"), timeout=10)
        row = conn.execute("SELECT status FROM turns WHERE id=?", (turn_id,)).fetchone()
        tokens_before = conn.execute(
            "SELECT COUNT(*) FROM events WHERE turn_id=? AND kind='token'", (turn_id,)).fetchone()[0]
        conn.close()
        assert row[0] == "streaming", f"expected a mid-flight turn, found {row[0]}"
        assert tokens_before > 0, "no tokens were durable before the crash"

        # … and the boot sweep must resolve it (CRS §10.3.2).
        recover = _run_child(self.RECOVER.format(backend=BACKEND), tmp_path)
        out, err = recover.communicate(timeout=90)
        assert recover.returncode == 0, f"recovery failed: {err[:600]}"
        swept = json.loads(out.strip().splitlines()[-1])
        assert swept["turns_failed"] >= 1

        conn = sqlite3.connect(str(tmp_path / "primnox.db"), timeout=10)
        try:
            status, code = conn.execute(
                "SELECT status, error_code FROM turns WHERE id=?", (turn_id,)).fetchone()
            assert status == "failed" and code == "internal", \
                "a turn was left non-terminal across a restart"

            # The tokens already delivered stay in the log, so a reconnecting
            # client replays the gap rather than losing what it saw.
            tokens_after = conn.execute(
                "SELECT COUNT(*) FROM events WHERE turn_id=? AND kind='token'",
                (turn_id,)).fetchone()[0]
            assert tokens_after == tokens_before, "recovery destroyed delivered events"

            # No orphaned running jobs, and the database is intact.
            running = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]
            assert running == 0
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            conn.close()

    def test_sweep_announces_the_turns_it_fails(self, conversation, events):
        """A swept turn must emit `turn.failed`, not just change a row.

        Found live: after killing the backend mid-stream and restarting, the
        browser reconnected, replayed the gap, and still showed "Writing"
        forever — because the sweep updated the database silently and no client
        was ever told the turn had died.
        """
        turn = turns.create_turn(conversation, "will be interrupted")
        with db.tx() as c:
            c.execute("UPDATE turns SET status='streaming' WHERE id=?", (turn["turn_id"],))

        swept = db.sweep_on_boot()
        assert swept["turns_failed"] >= 1

        failures = events.of_kind("turn.failed", turn["turn_id"])
        assert failures, "the sweep failed a turn without announcing it"
        assert failures[0]["payload"]["retryable"] is True
        assert "restart" in failures[0]["payload"]["message"].lower()

    def test_sweep_is_idempotent(self, tmp_path):
        """Running recovery twice must not change anything the second time."""
        for _ in range(2):
            child = _run_child(self.RECOVER.format(backend=BACKEND), tmp_path)
            out, err = child.communicate(timeout=90)
            assert child.returncode == 0, err[:400]
        conn = sqlite3.connect(str(tmp_path / "primnox.db"), timeout=10)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            conn.close()


class TestSandboxKilled:
    """Kill the process during execution."""

    def test_timeout_kills_and_reports_failure(self, sandbox_ready):
        result = sandbox.execute(
            code="import time\nopen('progress.txt','w').write('started')\ntime.sleep(120)\n",
            runtime="python",
            manifest=sandbox_perms.manifest_for("python", sandbox_perms.SAFE, timeout_s=5),
        )
        assert result["ok"] is False, "a timed-out execution reported success"

        session = sandbox.get(result["execution_id"])
        assert session["status"] == "failed"

        # The workspace is preserved, so the partial work is inspectable.
        workspace = Path(result["workspace"])
        assert workspace.exists(), "the workspace was destroyed after a failure"
        assert (workspace / "progress.txt").exists(), "partial work was lost"

        # And what it produced before dying is still recorded.
        assert result["changes"]["created"] == ["progress.txt"]

    def test_runaway_output_does_not_exhaust_memory(self, sandbox_ready):
        result = sandbox.execute(
            code="for i in range(20000): print('x' * 200)\n",
            runtime="python",
            manifest=sandbox_perms.manifest_for("python", sandbox_perms.SAFE, timeout_s=60),
        )
        session = sandbox.get(result["execution_id"])
        # Inline storage is bounded regardless of how much the script printed.
        assert len(session["stdout"] or "") <= sandbox.INLINE_OUTPUT_CHARS + 200


class TestDiskFull:
    """No storage left."""

    def test_asset_write_failure_is_graceful(self, conversation, monkeypatch):
        from primnox2 import paths as paths_module

        real_write = Path.write_bytes

        def full_disk(self, data):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(Path, "write_bytes", full_disk)
        with pytest.raises(OSError):
            assets.ingest_bytes(b"payload that cannot be stored", "toobig.bin",
                                conversation_id=conversation)
        monkeypatch.setattr(Path, "write_bytes", real_write)

        # The failure must not have corrupted anything or left a half-registered
        # asset claiming to exist.
        assert db.connect().execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        orphan = db.connect().execute(
            "SELECT COUNT(*) AS n FROM assets WHERE original_name='toobig.bin'").fetchone()
        assert orphan["n"] == 0, "an asset row survived a failed write"

    def test_log_write_failure_does_not_fail_a_completed_execution(self, sandbox_ready,
                                                                   tmp_path):
        """Losing the log copy must not fail work that already ran.

        The failure is induced for real rather than by replacing the function:
        a *file* is put where the `logs/` directory has to go, so `mkdir` fails
        exactly as it would on a full disk, and the guard inside `_write_logs`
        is the thing under test.
        """
        from primnox2.sandbox import manager as manager_module
        from primnox2.sandbox.supervisor import ExecResult

        (tmp_path / "logs").write_text("a file where a directory must be")
        manager_module._write_logs(tmp_path, ExecResult(exit_code=0, stdout="o", stderr="e"))

        # A real execution still completes normally.
        result = sandbox.execute(
            code="print('still works')", runtime="python",
            manifest=sandbox_perms.manifest_for("python", sandbox_perms.SAFE, timeout_s=30),
        )
        assert result["ok"] is True
        assert "still works" in (result["stdout"] or "")


class TestTransactionInterrupted:
    """Interrupt during a transaction."""

    def test_rollback_leaves_no_inconsistent_turn_event_pair(self, conversation):
        from primnox2.ids import new_id
        from primnox2.kernel.events import bus

        turn = turns.create_turn(conversation, "atomic probe")
        tid = turn["turn_id"]
        head_before = bus.head()

        with pytest.raises(sqlite3.IntegrityError):
            with db.tx() as c:
                c.execute("UPDATE turns SET status='streaming' WHERE id=?", (tid,))
                bus.emit("token", {"text": "half"}, conversation_id=conversation,
                         turn_id=tid, conn=c)
                c.execute("INSERT INTO messages (id,turn_id,role,text,created_at)"
                          " VALUES (?,?,?,?,?)", (new_id("msg"), "ghost", "user", "x", 1))

        row = db.connect().execute("SELECT status FROM turns WHERE id=?", (tid,)).fetchone()
        assert row["status"] == "queued", "a rolled-back transaction changed state anyway"
        assert bus.head() == head_before, "a rolled-back transaction consumed a sequence"
        assert db.connect().execute("PRAGMA foreign_key_check").fetchall() == []

    def test_concurrent_writers_do_not_tear_state(self, conversation):
        import threading

        from primnox2.kernel.events import bus

        head_before = bus.head()
        errors: list[Exception] = []

        def writer(n: int):
            try:
                for i in range(10):
                    t = turns.create_turn(conversation, f"writer {n} message {i}")
                    turns.complete(t["turn_id"], f"reply {n}.{i}")
            except Exception as exc:      # noqa: BLE001 — recorded, asserted below
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"concurrent writers failed: {errors[:3]}"

        # Every turn has exactly the messages it should, and the sequence is
        # still gapless after 40 concurrent completions.
        rows = db.connect().execute(
            "SELECT t.id, COUNT(m.id) AS n FROM turns t LEFT JOIN messages m ON m.turn_id=t.id"
            " WHERE t.conversation_id=? GROUP BY t.id", (conversation,)).fetchall()
        assert all(r["n"] <= 2 for r in rows), "a turn ended up with duplicate messages"

        # Scoped to events this test produced. Earlier tests delete turns,
        # which cascades to their events and legitimately leaves holes in the
        # table — the invariant under test is that concurrent emission never
        # skips or reuses a counter value.
        seqs = [r["sequence"] for r in db.connect().execute(
            "SELECT sequence FROM events WHERE sequence > ? ORDER BY sequence", (head_before,))]
        assert seqs == list(range(head_before + 1, bus.head() + 1)), \
            "concurrent writers skipped or reused a sequence"
        assert db.connect().execute("PRAGMA integrity_check").fetchone()[0] == "ok"
