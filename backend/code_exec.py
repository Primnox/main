"""Sandboxed Python/shell execution — the actual privilege boundary is the
dedicated Windows account provisioned by sandbox_account.py, not anything
in this module alone. This module launches code AS that separate account
(via LogonUser + CreateProcessAsUser), inside a Job Object that caps
aggregate memory and process count (fork-bomb defense), with a minimal
environment and a fresh, disposable per-execution working directory.

Every execution requires explicit user approval via permission_manager —
no exceptions, no "safe-looking code" auto-approval (see the plan's
"Explicitly deferred" section for why that was considered and rejected).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from logger import get_logger
from sandbox_account import SANDBOX_USERNAME, KEYRING_SERVICE, sandbox_account_configured

log = get_logger("code_exec")

DEFAULT_TIMEOUT_SECONDS = 15
MAX_OUTPUT_CHARS = 8000
# Disk: how much the CodeExecution directory may hold before oldest-first
# eviction. Nothing to do with runtime memory.
CODE_EXEC_QUOTA_BYTES = 200 * 1024 * 1024  # 200 MB
# RAM: the Job Object's aggregate memory cap. This was previously the same
# constant as the disk quota above, which capped the sandboxed process at
# 200 MB of memory — far too little to even import a native extension.
# numpy/OpenBLAS died with "Memory allocation still failed after 10
# retries" and PIL's _imaging DLL failed to load at all, so every
# reportlab/pandas-shaped workload was impossible (confirmed live).
MAX_MEMORY_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_ACTIVE_PROCESSES = 64  # concrete fork-bomb defense via the Job Object

# Windows needs these to even start python.exe/cmd.exe — deliberately an
# allowlist (not "os.environ minus secrets"), so nothing unanticipated
# (API keys, install paths) leaks in via inheritance. APPDATA is
# deliberately excluded — that's where settings.json lives.
_ENV_ALLOWLIST = ("SystemRoot", "PATH", "TEMP", "TMP", "PATHEXT", "WINDIR", "COMSPEC", "USERPROFILE")

# Reused workspaces are namespaced so the quota sweeper and any directory
# listing can tell them apart from throwaway per-execution session dirs.
_WORKSPACE_PREFIX = "ws_"
# Staged skill files (see skills/adapted_skill.py) and the scripts we write
# in are inputs, not results — reporting them as "files created" would bury
# the one artifact the user actually asked for under ~1.1 MB of OOXML
# schemas that ship with the docx/pptx/xlsx skills.
_EXCLUDED_PREFIXES = ("skill\\", "skill/")
_SCRIPT_NAMES = frozenset({"script.py", "script.js"})


def _minimal_env() -> dict:
    import os
    env = {}
    for key in _ENV_ALLOWLIST:
        val = os.environ.get(key)
        if val:
            env[key] = val
    env.setdefault("COMSPEC", r"C:\Windows\System32\cmd.exe")
    # The sandbox account can't see the user's global npm root (it lives
    # under this user's AppData, which is deliberately not shared), so
    # `require('pptxgenjs')` would fail no matter what's installed. Point
    # node at the shared runtime instead. NODE_PATH rather than relying on
    # node's walk-up resolution because the runtime deliberately isn't an
    # ancestor of the per-run workspace.
    from sandbox_manager import runtime_node_modules
    env["NODE_PATH"] = str(runtime_node_modules())
    return env


def _new_session_dir() -> tuple[str, Path]:
    from sandbox_manager import code_exec_dir
    session_id = uuid.uuid4().hex[:8]
    d = code_exec_dir() / session_id
    d.mkdir(parents=True, exist_ok=True)
    return session_id, d


def _workspace_dir(workspace_id: str) -> tuple[str, Path]:
    """A named, *reused* execution directory, as opposed to
    _new_session_dir()'s fresh-every-call one.

    Real Claude Skills are multi-step filesystem workflows — the pptx skill
    unzips a deck, edits ppt/slides/slideN.xml, rezips, then validates, each
    as a separate execution. With a new uuid directory per call, step 2
    cannot see what step 1 wrote, which makes that entire class of skill
    impossible rather than merely awkward.

    The id is sanitized to a single path component: it originates from a
    chat session id, and a caller passing "../../settings" must not be able
    to steer execution (or the quota sweeper) outside CodeExecution.
    """
    from sandbox_manager import code_exec_dir
    safe = re.sub(r"[^A-Za-z0-9_-]", "", workspace_id)[:64]
    if not safe:
        raise ValueError(f"workspace_id {workspace_id!r} has no usable characters")
    dir_name = f"{_WORKSPACE_PREFIX}{safe}"
    d = code_exec_dir() / dir_name
    d.mkdir(parents=True, exist_ok=True)
    return dir_name, d


def _snapshot(session_dir: Path) -> dict[str, int]:
    """Relative path -> mtime_ns, for everything currently in the directory."""
    snap = {}
    for p in session_dir.rglob("*"):
        if p.is_file():
            try:
                snap[str(p.relative_to(session_dir))] = p.stat().st_mtime_ns
            except OSError:
                pass
    return snap


def _files_created(
    session_dir: Path,
    exclude: frozenset[str] = frozenset(),
    before: dict[str, int] | None = None,
) -> list[str]:
    """Files this run produced. In a fresh session dir that's simply
    everything present; in a reused workspace it has to be a diff, or every
    run would re-report the staged skill files and every artifact from
    previous steps as newly created."""
    out = []
    for p in session_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(session_dir))
        if rel in exclude or any(rel.startswith(pre) for pre in _EXCLUDED_PREFIXES):
            continue
        if before is not None:
            try:
                if before.get(rel) == p.stat().st_mtime_ns:
                    continue  # untouched by this run
            except OSError:
                continue
        out.append(rel)
    return sorted(out)


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n...[truncated, {len(text) - MAX_OUTPUT_CHARS} more chars]"


def _build_command(language: str, code: str, session_dir: Path) -> str:
    if language == "python":
        script_path = session_dir / "script.py"
        script_path.write_text(code, encoding="utf-8")
        # sys.executable is a real interpreter in dev; in a PyInstaller build
        # it's primnox_backend.exe itself — see the plan's known follow-up
        # (bundled embeddable interpreter) for the packaged-build fix.
        return f'"{sys.executable}" "{script_path}"'
    elif language == "shell":
        # Must go through cmd.exe: CreateProcessAsUser executes a command
        # line directly, with no shell involved, so redirects (>), pipes,
        # chaining (&&) and builtins (echo, dir, set) are all inert. Running
        # `echo hi > out.txt && dir` bare didn't redirect or chain — it
        # resolved `echo` to an unrelated echo.exe found on PATH and passed
        # the rest through as literal argv (confirmed live). Quoting the
        # whole command after /c is what keeps its own quotes intact.
        comspec = _minimal_env()["COMSPEC"]
        return f'"{comspec}" /c "{code}"'
    elif language == "node":
        # The official pptx and docx skills build their output with
        # pptxgenjs / docx-js — npm libraries with no Python equivalent — so
        # a Python-only sandbox can't run them at all, only describe them.
        script_path = session_dir / "script.js"
        script_path.write_text(code, encoding="utf-8")
        return f'"{_node_executable()}" "{script_path}"'
    else:
        raise ValueError(f"unknown language: {language!r}")


def _node_executable() -> str:
    """Absolute path to node.exe. Resolved here rather than left to PATH
    lookup because the sandbox account's PATH is the machine's, and a
    node installed only for this user wouldn't be on it."""
    found = shutil.which("node")
    if not found:
        raise ValueError(
            "node isn't installed or isn't on PATH — required for skills that "
            "generate documents with pptxgenjs or docx-js."
        )
    return found


# CreateProcessAsUser needs these on the CALLING process's own token — they
# come from local Administrators-group membership by default, but Windows'
# UAC token filtering strips them (not merely disables them) from the normal,
# non-elevated token a desktop process runs with, even when that process's
# user account is an administrator. Only a genuinely elevated process has
# them at all. Confirmed live: CreateProcessAsUser failed with
# "(1314, 'CreateProcessAsUser', 'A required privilege is not held by the
# client.')" when Primnox's backend ran unelevated.
_REQUIRED_PRIVILEGES = ("SeAssignPrimaryTokenPrivilege", "SeIncreaseQuotaPrivilege")


class SandboxPrivilegeError(PermissionError):
    """Raised when this process's token doesn't hold (and can't be granted)
    a privilege CreateProcessAsUser needs — practically always means Primnox
    itself isn't running elevated."""


def _enable_own_privileges(names: tuple[str, ...] = _REQUIRED_PRIVILEGES) -> None:
    import win32security
    import win32api
    import win32con
    import winerror

    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(),
        win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY,
    )
    try:
        for name in names:
            luid = win32security.LookupPrivilegeValue(None, name)
            win32security.AdjustTokenPrivileges(token, False, [(luid, win32security.SE_PRIVILEGE_ENABLED)])
            # AdjustTokenPrivileges doesn't raise when a privilege wasn't
            # present in the token at all — it just silently adjusts zero
            # of them. GetLastError is the only way to notice.
            if win32api.GetLastError() == winerror.ERROR_NOT_ALL_ASSIGNED:
                raise SandboxPrivilegeError(
                    f"{name} is not available on Primnox's process token — "
                    "Primnox must be running with administrator privileges "
                    "for sandboxed code execution to work."
                )
    finally:
        token.Close()


def _create_sandboxed_process(command_line: str, cwd: Path, env: dict, timeout: float) -> dict:
    """The actual Win32 process-creation primitive: LogonUser as the
    sandbox account, CreateProcessAsUser inside a Job Object with
    memory/process-count limits, pipe-captured stdout/stderr. Isolated into
    its own function so the surrounding logic (permission gate, session
    dirs, quota, trace logging) is unit-testable by mocking this one call
    rather than needing a real second Windows account in every test run."""
    import keyring
    import win32con
    import win32security
    import win32process
    import win32job
    import win32event
    import win32pipe
    import win32file
    import win32api
    import pywintypes

    password = keyring.get_password(KEYRING_SERVICE, SANDBOX_USERNAME)
    if not password:
        return {"success": False, "stdout": "", "stderr": "sandbox account not configured.", "return_code": -1, "timed_out": False}

    _enable_own_privileges()

    token = win32security.LogonUser(
        SANDBOX_USERNAME, ".", password,
        win32con.LOGON32_LOGON_BATCH, win32con.LOGON32_PROVIDER_DEFAULT,
    )

    # Without a loaded profile the child's HKEY_CURRENT_USER resolves to
    # .DEFAULT, which some native extensions can't initialize against —
    # Pillow's _imaging failed with "DLL initialization routine failed"
    # while numpy/lxml/sqlite3 loaded fine. LoadUserProfile is the
    # documented companion to CreateProcessAsUser; best-effort because a
    # failure here only costs us the profile-dependent libraries, not the
    # whole sandbox.
    profile_handle = None
    try:
        import win32profile
        profile_handle = win32profile.LoadUserProfile(
            token, {"UserName": SANDBOX_USERNAME, "Flags": 0}
        )
    except Exception as e:
        log.warning(f"Could not load sandbox user profile (continuing without it): {e}")

    sec_attr = pywintypes.SECURITY_ATTRIBUTES()
    sec_attr.bInheritHandle = True
    stdout_read, stdout_write = win32pipe.CreatePipe(sec_attr, 0)
    stderr_read, stderr_write = win32pipe.CreatePipe(sec_attr, 0)
    # The parent's own copies of the read ends must NOT be inherited by the
    # child, or ReadFile on them will block forever (the child would hold
    # its own dangling write-capable reference to what should be parent-only).
    win32api.SetHandleInformation(stdout_read, win32con.HANDLE_FLAG_INHERIT, 0)
    win32api.SetHandleInformation(stderr_read, win32con.HANDLE_FLAG_INHERIT, 0)

    startup_info = win32process.STARTUPINFO()
    # A process created for a different user gets no window station/desktop
    # by default, and any DLL that attaches to one during initialization then
    # fails before main() runs (STATUS_DLL_INIT_FAILED / 0xC0000142) — node
    # died this way, as did Pillow's _imaging. winsta0\default is the
    # interactive one, which this account deliberately cannot reach; a
    # private station is both what makes those load and stronger isolation
    # than sharing the user's desktop would be.
    startup_info.lpDesktop = "winsta0\\default"
    startup_info.dwFlags = win32process.STARTF_USESTDHANDLES
    startup_info.hStdOutput = stdout_write
    startup_info.hStdError = stderr_write
    startup_info.hStdInput = win32file.CreateFile(
        "NUL", win32con.GENERIC_READ, 0, None, win32con.OPEN_EXISTING, 0, None
    )

    job = win32job.CreateJobObject(None, "")
    limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    limits["BasicLimitInformation"]["LimitFlags"] = (
        win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | win32job.JOB_OBJECT_LIMIT_JOB_MEMORY
        | win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    )
    limits["JobMemoryLimit"] = MAX_MEMORY_BYTES
    limits["BasicLimitInformation"]["ActiveProcessLimit"] = MAX_ACTIVE_PROCESSES
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)

    hProcess = None
    start = time.time()
    try:
        proc_info = win32process.CreateProcessAsUser(
            token, None, command_line, None, None, True,
            win32process.CREATE_NEW_PROCESS_GROUP, env, str(cwd), startup_info,
        )
        hProcess, hThread, pid, _tid = proc_info
        hThread.Close()

        win32job.AssignProcessToJobObject(job, hProcess)

        # Parent no longer needs the write ends once the child has them —
        # keeping them open here would make ReadFile below block forever
        # waiting for a close that will never come from this side.
        stdout_write.Close()
        stderr_write.Close()

        stdout_data, stderr_data = _drain_pipes(stdout_read, stderr_read, hProcess, timeout)

        wait_result = win32event.WaitForSingleObject(hProcess, 0)
        timed_out = wait_result != win32event.WAIT_OBJECT_0
        if timed_out:
            win32job.TerminateJobObject(job, 1)
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
            return_code = -1
        else:
            return_code = win32process.GetExitCodeProcess(hProcess)

        return {
            "success": (not timed_out) and return_code == 0,
            "stdout": stdout_data,
            "stderr": stderr_data,
            "return_code": return_code,
            "timed_out": timed_out,
            "duration_ms": round((time.time() - start) * 1000, 1),
        }
    finally:
        if hProcess:
            hProcess.Close()
        job.Close()
        # Unload before closing the token — the profile's registry hive stays
        # mounted otherwise, and mounted hives accumulate across runs.
        if profile_handle is not None:
            try:
                import win32profile
                win32profile.UnloadUserProfile(token, profile_handle)
            except Exception as e:
                log.warning(f"Could not unload sandbox user profile: {e}")
        token.Close()


def _drain_pipes(stdout_read, stderr_read, hProcess, timeout: float) -> tuple[str, str]:
    """Reads both pipes to EOF on background threads while the main thread
    waits on the process with a timeout — avoids the classic deadlock where
    a single-threaded reader blocks on one pipe while the child fills the
    other pipe's buffer and stalls."""
    import threading
    import win32event
    import win32file
    import pywintypes

    buffers = {"stdout": [], "stderr": []}

    def _reader(handle, key):
        while True:
            try:
                err, data = win32file.ReadFile(handle, 4096)
            except pywintypes.error:
                break
            if not data:
                break
            buffers[key].append(data.decode("utf-8", errors="replace"))
        try:
            handle.Close()
        except Exception:
            pass

    t_out = threading.Thread(target=_reader, args=(stdout_read, "stdout"), daemon=True)
    t_err = threading.Thread(target=_reader, args=(stderr_read, "stderr"), daemon=True)
    t_out.start()
    t_err.start()

    win32event.WaitForSingleObject(hProcess, int(timeout * 1000))

    t_out.join(timeout=2)
    t_err.join(timeout=2)

    return "".join(buffers["stdout"]), "".join(buffers["stderr"])


def _run(
    language: str,
    code: str,
    session_id: str = "",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    workspace_id: str = "",
    _internal: bool = False,
) -> dict:
    """_internal skips the permission prompt and is ONLY for probe code that
    is a fixed literal in Primnox's own source (see runtime_capabilities.py).
    It is deliberately not exposed on run_python/run_shell/run_node, so no
    model-supplied code can ever reach it. Prompting for our own capability
    probe would train the user to approve executions reflexively, which costs
    real safety to buy none."""
    if not sandbox_account_configured():
        return {"success": False, "error": "sandboxed execution isn't set up yet — enable it in Settings."}

    if not _internal:
        from permission_manager import request_permission
        allowed = request_permission(
            action=f"run_{language}",
            description=f"Run this {language} code?\n\n```{language}\n{code}\n```",
            session_id=session_id,
        )
        if not allowed:
            return {"success": False, "error": "execution cancelled — not approved."}

    try:
        if workspace_id:
            exec_session_id, session_dir = _workspace_dir(workspace_id)
        else:
            exec_session_id, session_dir = _new_session_dir()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    # Only meaningful for a reused workspace; None keeps the fresh-dir case
    # reporting everything present, as before.
    before = _snapshot(session_dir) if workspace_id else None

    try:
        command_line = _build_command(language, code, session_dir)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    env = _minimal_env()
    try:
        result = _create_sandboxed_process(command_line, session_dir, env, timeout)
    except SandboxPrivilegeError as e:
        return {"success": False, "error": str(e)}

    # script.py/script.js is the code we wrote in, not something the code
    # produced — exclude it so "files created" only reflects real output.
    files_created = _files_created(session_dir, exclude=_SCRIPT_NAMES, before=before)

    from sandbox_manager import enforce_quota, code_exec_dir, prune_stale_workspaces, runtime_dir
    # Stale workspaces are reclaimed by age, not by the quota sweeper: a
    # workspace mid-task is full of files older than the throwaway session
    # dirs around it, so oldest-first eviction would target it first and
    # delete a half-finished deck between two steps of the same skill.
    prune_stale_workspaces()
    enforce_quota(
        quota_bytes=CODE_EXEC_QUOTA_BYTES,
        base=code_exec_dir(),
        protect=(runtime_dir(), session_dir),
    )

    log.info("code_execution", extra={
        "session_id": session_id,
        "event": "execution_complete",
        "duration_ms": result.get("duration_ms", 0),
        "return_code": result.get("return_code"),
        "language": language,
    })

    return {
        "success": result.get("success", False),
        "stdout": _truncate(result.get("stdout", "")),
        "stderr": _truncate(result.get("stderr", "")),
        "return_code": result.get("return_code", -1),
        "timed_out": result.get("timed_out", False),
        "duration_ms": result.get("duration_ms", 0),
        "sandbox_id": exec_session_id,
        "files_created": files_created,
    }


def run_python(code: str, session_id: str = "", timeout: float = DEFAULT_TIMEOUT_SECONDS,
               workspace_id: str = "") -> dict:
    return _run("python", code, session_id=session_id, timeout=timeout, workspace_id=workspace_id)


def run_shell(code: str, session_id: str = "", timeout: float = DEFAULT_TIMEOUT_SECONDS,
              workspace_id: str = "") -> dict:
    return _run("shell", code, session_id=session_id, timeout=timeout, workspace_id=workspace_id)


def run_node(code: str, session_id: str = "", timeout: float = DEFAULT_TIMEOUT_SECONDS,
             workspace_id: str = "") -> dict:
    return _run("node", code, session_id=session_id, timeout=timeout, workspace_id=workspace_id)


def run_probe(language: str, code: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Runs Primnox's OWN capability-probe code without a permission prompt.

    Callers must pass a literal defined in Primnox's source — never anything
    derived from a model, a file, or user input. The isolation boundary is
    unchanged (this still executes as the sandbox account, in the Job
    Object); only the approval dialog is skipped, because prompting for code
    the user cannot meaningfully review teaches them to click through
    approvals that do matter.
    """
    return _run(language, code, timeout=timeout,
                workspace_id="_capability_probe", _internal=True)


def workspace_path(workspace_id: str) -> Path:
    """Host-side path of a named workspace, for callers that need to collect
    an artifact the sandboxed code produced (see skills/sandboxed_render.py)."""
    return _workspace_dir(workspace_id)[1]
