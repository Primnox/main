"""Process supervision — the Sandbox Manager owns every process it launches.

The supervisor tracks stdout, stderr, wall time and the process tree, and kills
the whole tree when an execution runs past its timeout or is cancelled.

Two backends:

    appcontainer   real isolation — a distinct AppContainer SID,
                   deny-by-default filesystem, no network capability at all.
    unsandboxed    plain subprocess, NO isolation whatsoever.

The second is refused unless `PRIMNOX2_ALLOW_UNSANDBOXED=1` is set.

That refusal is the important line in this file. If isolation is unavailable,
the honest options are "don't run it" or "run it with the user's full
privileges", and quietly choosing the second while still calling the feature a
sandbox would be a security claim the code does not deliver. The execution
record stores which backend actually ran, so nothing downstream has to guess.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import appcontainer
from .permissions import Manifest
from .workspace import SCRIPT_NAMES

# Keep at most this much of each stream in memory. The full text is on disk in
# the session's logs directory, and the manager promotes large output to an
# asset.
MAX_STREAM_CHARS = 2 * 1024 * 1024

KILL_GRACE_S = 5.0

APPCONTAINER, UNSANDBOXED = "appcontainer", "unsandboxed"

_backend_cache: dict[str, str | None] = {}


@dataclass
class ExecResult:
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    backend: str = UNSANDBOXED
    timed_out: bool = False
    cancelled: bool = False
    error: str | None = None
    duration_ms: int = 0
    truncated: bool = False

    @property
    def success(self) -> bool:
        return (self.exit_code == 0 and not self.timed_out
                and not self.cancelled and not self.error)


def available_backend(refresh: bool = False) -> str | None:
    """Which backend would run right now, or None if execution must be refused.

    Provisioning is attempted once and the answer cached — it shells out to
    icacls over the interpreter tree, which is far too slow to repeat before
    every execution.
    """
    if not refresh and "value" in _backend_cache:
        return _backend_cache["value"]

    value: str | None = None
    try:
        if appcontainer.configured() or appcontainer.ensure_provisioned():
            value = APPCONTAINER
    except Exception:
        # A failure to establish isolation is never a reason to fall back to
        # running unisolated. That decision belongs to the env var alone.
        value = None
    if value is None and os.getenv("PRIMNOX2_ALLOW_UNSANDBOXED") == "1":
        value = UNSANDBOXED

    _backend_cache["value"] = value
    return value


def run(
    directory: Path,
    runtime: str,
    manifest: Manifest,
    *,
    on_stdout: Callable[[str], None] | None = None,
    on_stderr: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ExecResult:
    """Execute the script already written into `directory`."""
    backend = available_backend()
    if backend is None:
        return ExecResult(
            backend=UNSANDBOXED,
            error=(
                "No isolation backend is available. AppContainer could not be "
                "provisioned, and running model-generated code without isolation "
                "is refused. Set PRIMNOX2_ALLOW_UNSANDBOXED=1 only on a machine "
                "you are willing to run untrusted code on."
            ),
        )
    if backend == APPCONTAINER:
        return _run_appcontainer(directory, runtime, manifest, on_stdout, on_stderr)
    return _run_plain(directory, runtime, manifest, on_stdout, on_stderr, should_cancel)


def _run_appcontainer(directory, runtime, manifest, on_stdout, on_stderr) -> ExecResult:
    """Isolated execution.

    Output arrives at the end rather than line by line: the AppContainer path
    cannot attach std handles (doing so makes the process die with
    STATUS_DLL_INIT_FAILED), so the child redirects its own streams to capture
    files which are read after exit. The stdout/stderr events still fire —
    fewer of them, later. Isolation is worth that.
    """
    started = time.time()
    code = (directory / SCRIPT_NAMES[runtime]).read_text(encoding="utf-8")
    try:
        raw = appcontainer.run(directory, runtime, code,
                               timeout_s=manifest.timeout_s, memory_mb=manifest.memory_mb)
    except appcontainer.SandboxUnavailable as exc:
        return ExecResult(backend=APPCONTAINER, error=str(exc),
                          duration_ms=int((time.time() - started) * 1000))
    except Exception as exc:
        return ExecResult(backend=APPCONTAINER, error=f"{type(exc).__name__}: {exc}",
                          duration_ms=int((time.time() - started) * 1000))

    stdout = (raw.get("stdout") or "")[:MAX_STREAM_CHARS]
    stderr = (raw.get("stderr") or "")[:MAX_STREAM_CHARS]
    for line in stdout.splitlines():
        if on_stdout:
            on_stdout(line)
    for line in stderr.splitlines():
        if on_stderr:
            on_stderr(line)

    return ExecResult(
        exit_code=raw.get("exit_code"), stdout=stdout, stderr=stderr,
        backend=APPCONTAINER, timed_out=bool(raw.get("timed_out")),
        duration_ms=raw.get("duration_ms", int((time.time() - started) * 1000)),
    )


def _reader(stream, sink: list[str], on_line, budget: list[int]) -> None:
    """Drain one pipe on its own thread, forwarding lines as they arrive."""
    try:
        for raw in iter(stream.readline, ""):
            if not raw:
                break
            if budget[0] > 0:
                sink.append(raw)
                budget[0] -= len(raw)
            if on_line is not None:
                try:
                    on_line(raw.rstrip("\r\n"))
                except Exception:
                    # A failing subscriber must never kill the drain thread —
                    # that would block the process on a full pipe buffer.
                    pass
    except (ValueError, OSError):
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process and everything it spawned.

    Python spawning Node spawning something else has to die as one unit;
    `proc.kill()` alone would orphan the descendants.
    """
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=KILL_GRACE_S)
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=KILL_GRACE_S)
    except Exception:
        pass


def _command(runtime: str, directory: Path) -> list[str]:
    script = directory / SCRIPT_NAMES[runtime]
    if runtime == "python":
        return [sys.executable, "-I", "-u", str(script)]
    if runtime == "node":
        return ["node", "--preserve-symlinks", "--preserve-symlinks-main", str(script)]
    return ["cmd.exe", "/c", str(script)]


def _run_plain(directory, runtime, manifest, on_stdout, on_stderr, should_cancel) -> ExecResult:
    """Unisolated execution. Only reachable with PRIMNOX2_ALLOW_UNSANDBOXED=1.

    Enforces wall-clock timeout and cancellation. It cannot enforce the
    manifest's memory, disk or filesystem policy — there is no Job Object and
    no security boundary here, which is exactly why it is gated.
    """
    started = time.time()
    try:
        proc = subprocess.Popen(
            _command(runtime, directory), cwd=str(directory),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except (OSError, FileNotFoundError) as exc:
        return ExecResult(backend=UNSANDBOXED, error=f"could not start {runtime}: {exc}",
                          duration_ms=int((time.time() - started) * 1000))

    out_buf: list[str] = []
    err_buf: list[str] = []
    budget_out, budget_err = [MAX_STREAM_CHARS], [MAX_STREAM_CHARS]
    threads = [
        threading.Thread(target=_reader, args=(proc.stdout, out_buf, on_stdout, budget_out), daemon=True),
        threading.Thread(target=_reader, args=(proc.stderr, err_buf, on_stderr, budget_err), daemon=True),
    ]
    for t in threads:
        t.start()

    deadline = started + manifest.timeout_s
    timed_out = cancelled = False
    while True:
        if proc.poll() is not None:
            break
        if time.time() > deadline:
            timed_out = True
            _kill_tree(proc)
            break
        # CRS §9.2 — a cancellation checkpoint on the poll loop, so stop takes
        # effect while the process is still running.
        if should_cancel is not None and should_cancel():
            cancelled = True
            _kill_tree(proc)
            break
        time.sleep(0.05)

    for t in threads:
        t.join(timeout=KILL_GRACE_S)

    return ExecResult(
        exit_code=proc.returncode, stdout="".join(out_buf), stderr="".join(err_buf),
        backend=UNSANDBOXED, timed_out=timed_out, cancelled=cancelled,
        duration_ms=int((time.time() - started) * 1000),
        truncated=budget_out[0] <= 0 or budget_err[0] <= 0,
    )
