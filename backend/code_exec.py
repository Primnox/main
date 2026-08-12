"""Sandboxed Python/shell/Node execution, with two interchangeable backends
behind one interface (run_python/run_shell/run_node/run_probe):

1. The AppContainer backend (appcontainer_sandbox.py) — preferred. Runs the
   sandboxed process under an AppContainer security identity via plain
   CreateProcess, in the SAME session as Primnox itself (no separate logon
   at all). Node.js and Pillow's native extension — both broken under
   backend 2 — are confirmed live to work here, because there's no separate
   logon session to be missing a window-station SID for in the first place.
   See docs/sandbox-runtime-limitations.md for the full root-cause
   investigation and appcontainer_sandbox.py's module docstring for how
   isolation still holds (SID-based deny-by-default, confirmed live against
   settings.json/memory.db/chat.db/network).

2. The Windows-account backend (sandbox_account.py) — fallback. A
   dedicated, low-privileged Windows account, launched via LogonUser +
   CreateProcessAsUser inside a Job Object. Kept permanently, not just
   during migration: needs no AppContainer support to be present, and
   already covers everything Primnox generates today (PDFs, Excel,
   Python-only skills) with isolation already verified live.

Backend selection happens once per `_run()` call via `_active_backend()`,
preferring AppContainer when `appcontainer_sandbox.appcontainer_configured()`
says it's ready.

Every execution requires explicit user approval via permission_manager —
no exceptions, no "safe-looking code" auto-approval (see the plan's
"Explicitly deferred" section for why that was considered and rejected).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
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
# deliberately excluded — that's where settings.json lives (AppData\Roaming).
# LOCALAPPDATA is a DIFFERENT tree (AppData\Local) and is required, not
# optional, for the AppContainer backend specifically: CreateProcessW with
# both a custom environment block AND an AppContainer security-capabilities
# attribute fails outright with ERROR_ENVVAR_NOT_FOUND (203) without it —
# confirmed live, isolated down to this one variable. AppContainer redirects
# a process's per-container storage under %LOCALAPPDATA%\Packages\..., and
# apparently needs the base value present to compute that redirection
# during process creation itself, before the sandboxed code ever runs.
_ENV_ALLOWLIST = ("SystemRoot", "PATH", "TEMP", "TMP", "PATHEXT", "WINDIR", "COMSPEC", "USERPROFILE", "LOCALAPPDATA")

# Reused workspaces are namespaced so the quota sweeper and any directory
# listing can tell them apart from throwaway per-execution session dirs.
_WORKSPACE_PREFIX = "ws_"
# Staged skill files (see skills/adapted_skill.py) and the scripts we write
# in are inputs, not results — reporting them as "files created" would bury
# the one artifact the user actually asked for under ~1.1 MB of OOXML
# schemas that ship with the docx/pptx/xlsx skills.
_EXCLUDED_PREFIXES = ("skill\\", "skill/")
_SCRIPT_NAMES = frozenset({"script.py", "script.js"})
# Output-capture plumbing (AppContainer backend only) — not something the
# sandboxed code "created", just how its stdout/stderr get back to us.
_APPCONTAINER_CAPTURE_NAMES = frozenset({"_ac_stdout.txt", "_ac_stderr.txt", "_ac_wrapper.py", "_ac_wrapper.js", "package.json"})


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


# ---------------------------------------------------------------------------
# AppContainer backend — preferred. See the module docstring for why, and
# appcontainer_sandbox.py for provisioning/isolation. Confirmed live: node.exe
# and `import PIL._imaging` both succeed under this backend; the
# Windows-account backend (below) cannot run either.
# ---------------------------------------------------------------------------

_APPCONTAINER_STDOUT_NAME = "_ac_stdout.txt"
_APPCONTAINER_STDERR_NAME = "_ac_stderr.txt"


def _active_backend() -> str:
    """"appcontainer" or "windows". Resolved fresh on every call, but cheap
    in practice — appcontainer_sandbox.appcontainer_configured() is local
    Win32 calls, not a subprocess spawn, unlike the WSL2 backend this
    project tried and discarded earlier."""
    try:
        import appcontainer_sandbox
        if appcontainer_sandbox.appcontainer_configured():
            return "appcontainer"
    except Exception as e:
        log.warning(f"AppContainer backend check failed, falling back to the Windows-account sandbox: {e}")
    return "windows"


def _build_appcontainer_command(language: str, code: str, session_dir: Path) -> str:
    """Builds the COMPLETE, ready-to-launch top-level command for the
    AppContainer backend — unlike the Windows-account backend's
    _build_command(), the caller (_create_appcontainer_process) does no
    further wrapping at all.

    Output capture strategy differs by language, for reasons found live,
    the hard way, in this session:

    - python/node: the interpreter is launched DIRECTLY as the top-level
      AppContainer process, on a small generated WRAPPER script that
      redirects its OWN stdout/stderr to files from *inside* the process
      (Python: reassigning sys.stdout/sys.stderr; Node: overriding
      process.stdout.write/process.stderr.write) before running the user's
      code. This is deliberate, not incidental: launching python.exe/
      node.exe directly is confirmed live to work every time; wrapping them
      in an outer `cmd.exe /c "..."` for shell-level redirection is
      confirmed live to intermittently fail with a bare "Access is denied."
      specifically when cmd.exe (itself running as the AppContainer) tries
      to spawn node.exe as ITS OWN child — reproduced with clean ACLs and a
      freshly-provisioned profile, cause not fully understood (not a file
      permission issue — confirmed the target files ARE readable; possibly
      an AppContainer-specific restriction on child-process creation for
      that specific case). In-process redirection sidesteps the whole
      question by never spawning node.exe as anyone's child at all.

    - shell: cmd.exe MUST be the interpreter — there's no way around it
      being "the thing that runs the code" — so it's launched directly
      (not nested), with the SAME inline `cmd.exe /c "{code} > out 2> err"`
      approach the Windows-account backend already uses and accepts the
      quoting trade-off for. A separate attempt to sidestep that trade-off
      by writing the shell code to a .bat file and invoking `cmd.exe /c
      "{batfile}"` was tried and produced an EARLIER, more opaque failure
      (empty output, not even the batch file's own redirect firing) than
      the inline approach — worse, not better, so inlining was kept despite
      the quoting risk it carries. Shell code that itself launches other
      interpreters (python/node) as sub-processes may hit the same
      unresolved child-process restriction noted above; this is a known,
      undiagnosed limitation of the shell path specifically.
    """
    stdout_path = session_dir / _APPCONTAINER_STDOUT_NAME
    stderr_path = session_dir / _APPCONTAINER_STDERR_NAME

    if language == "python":
        script_path = session_dir / "script.py"
        script_path.write_text(code, encoding="utf-8")
        wrapper_path = session_dir / "_ac_wrapper.py"
        wrapper_path.write_text(
            "import sys\n"
            f"sys.stdout = open(r'{stdout_path}', 'w', encoding='utf-8')\n"
            f"sys.stderr = open(r'{stderr_path}', 'w', encoding='utf-8')\n"
            f"_src = open(r'{script_path}', encoding='utf-8').read()\n"
            f"exec(compile(_src, r'{script_path}', 'exec'))\n",
            encoding="utf-8",
        )
        return f'"{sys.executable}" "{wrapper_path}"'
    elif language == "node":
        script_path = session_dir / "script.js"
        script_path.write_text(code, encoding="utf-8")
        # Node's own startup realpath-resolves its entry script, which on
        # Windows walks UP the directory tree. Confirmed live: that walk's
        # lstat() on bare `C:\` itself fails with EPERM under the
        # AppContainer SID — which was never granted anything above the
        # workspace directory, correct isolation behavior, but it broke
        # Node before the wrapper's own code ever ran. --preserve-symlinks-main
        # skips that resolution entirely (confirmed live: fixes it with no
        # ACL changes). A package.json here too, belt-and-suspenders — it
        # alone did NOT fix the EPERM (tested), but stops a *separate*
        # upward walk (CommonJS-vs-ESM package-scope lookup) that isn't
        # symlink resolution and so isn't covered by the flag above.
        (session_dir / "package.json").write_text("{}", encoding="utf-8")
        wrapper_path = session_dir / "_ac_wrapper.js"
        # String.raw + backtick template avoids re-opening the same
        # backslash-escaping question Windows paths always raise in a
        # generated string — the path is embedded as a JS raw string, not
        # re-parsed as an expression.
        wrapper_path.write_text(
            "const fs = require('fs');\n"
            f"const __out = fs.openSync(String.raw`{stdout_path}`, 'w');\n"
            f"const __err = fs.openSync(String.raw`{stderr_path}`, 'w');\n"
            "process.stdout.write = (chunk, enc, cb) => { fs.writeSync(__out, chunk); if (typeof cb === 'function') cb(); return true; };\n"
            "process.stderr.write = (chunk, enc, cb) => { fs.writeSync(__err, chunk); if (typeof cb === 'function') cb(); return true; };\n"
            "try {\n"
            f"  require(String.raw`{script_path}`);\n"
            "} catch (e) {\n"
            "  process.stderr.write(String((e && e.stack) || e) + '\\n');\n"
            "  process.exitCode = 1;\n"
            "}\n",
            encoding="utf-8",
        )
        # --preserve-symlinks-main alone only skips realpath-resolution for
        # the entry module (the wrapper itself) — the wrapper's OWN
        # require() of the user's script.js hit the identical EPERM
        # independently (confirmed live), since that's a SEPARATE
        # resolution call. --preserve-symlinks covers require() calls too;
        # both flags are needed together.
        return f'"{_node_executable()}" --preserve-symlinks --preserve-symlinks-main "{wrapper_path}"'
    elif language == "shell":
        comspec = _minimal_env()["COMSPEC"]
        return f'"{comspec}" /c "{code} > "{stdout_path}" 2> "{stderr_path}""'
    else:
        raise ValueError(f"unknown language: {language!r}")


class _SecurityCapabilities(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.c_void_p),
        ("CapabilityCount", ctypes.wintypes.DWORD),
        ("Reserved", ctypes.wintypes.DWORD),
    ]


class _StartupInfoW(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.wintypes.DWORD), ("lpReserved", ctypes.wintypes.LPWSTR),
        ("lpDesktop", ctypes.wintypes.LPWSTR), ("lpTitle", ctypes.wintypes.LPWSTR),
        ("dwX", ctypes.wintypes.DWORD), ("dwY", ctypes.wintypes.DWORD),
        ("dwXSize", ctypes.wintypes.DWORD), ("dwYSize", ctypes.wintypes.DWORD),
        ("dwXCountChars", ctypes.wintypes.DWORD), ("dwYCountChars", ctypes.wintypes.DWORD),
        ("dwFillAttribute", ctypes.wintypes.DWORD), ("dwFlags", ctypes.wintypes.DWORD),
        ("wShowWindow", ctypes.wintypes.WORD), ("cbReserved2", ctypes.wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p), ("hStdInput", ctypes.c_void_p),
        ("hStdOutput", ctypes.c_void_p), ("hStdError", ctypes.c_void_p),
    ]


class _StartupInfoExW(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfoW), ("lpAttributeList", ctypes.c_void_p)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", ctypes.wintypes.HANDLE), ("hThread", ctypes.wintypes.HANDLE),
        ("dwProcessId", ctypes.wintypes.DWORD), ("dwThreadId", ctypes.wintypes.DWORD),
    ]


_PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_UNICODE_ENVIRONMENT = 0x00000400


def _build_environment_block(env: dict) -> ctypes.Array:
    """Converts a plain dict into the null-terminated wide-string block
    CreateProcessW's lpEnvironment expects: "KEY=VALUE\\0" per entry,
    concatenated, with an extra trailing \\0. Requires
    CREATE_UNICODE_ENVIRONMENT in dwCreationFlags — without it Windows
    reads this as ANSI and corrupts every entry."""
    block = "".join(f"{k}={v}\0" for k, v in env.items()) + "\0"
    return ctypes.create_unicode_buffer(block)


def _create_appcontainer_process(command: str, cwd: Path, timeout: float) -> dict:
    """The AppContainer-shaped sibling to _create_sandboxed_process() —
    identical return shape, so _run() doesn't need to know which backend
    produced it.

    No pywin32 support exists for AppContainer or the extended
    STARTUPINFOEX security-capabilities attribute at all (confirmed: zero
    matching names in win32security/win32process), so this is raw ctypes
    throughout, matching this session's Loader Snaps debugger.

    `command` is already the COMPLETE top-level command
    (_build_appcontainer_command built it, including whatever output-
    capture strategy that language uses) — this function does no further
    wrapping. Two things confirmed live and NOT reproduced here on purpose:
    STARTUPINFO's hStdOutput/hStdError/STARTF_USESTDHANDLES makes the
    process die with STATUS_DLL_INIT_FAILED (0xC0000142) regardless of
    handle type; and having an AppContainer `cmd.exe` spawn node.exe as ITS
    OWN child intermittently fails with a bare "Access is denied." even
    with correct ACLs (cause undiagnosed). Both are why python/node use
    in-script redirection and launch their interpreter directly rather
    than being wrapped in an outer shell here.
    """
    import appcontainer_sandbox

    sid_string = appcontainer_sandbox.appcontainer_sid_string()
    sid_out = ctypes.c_void_p()
    ctypes.windll.advapi32.ConvertStringSidToSidW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    ctypes.windll.advapi32.ConvertStringSidToSidW.restype = ctypes.wintypes.BOOL
    if not ctypes.windll.advapi32.ConvertStringSidToSidW(sid_string, ctypes.byref(sid_out)):
        return {"success": False, "stdout": "", "stderr": "could not resolve the AppContainer SID",
                "return_code": -1, "timed_out": False, "duration_ms": 0.0}

    stdout_path = cwd / _APPCONTAINER_STDOUT_NAME
    stderr_path = cwd / _APPCONTAINER_STDERR_NAME
    wrapped = command

    # Without this, CreateProcessW's lpEnvironment=None makes the child
    # inherit THIS (real, unsandboxed) process's full environment instead —
    # confirmed live: pptxgenjs/docx (installed under the shared runtime
    # node_modules _minimal_env() points NODE_PATH at) were unreachable
    # because NODE_PATH was never actually being set for the AppContainer
    # process at all.
    env_block = _build_environment_block(_minimal_env())

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)]
    k32.InitializeProcThreadAttributeList.restype = ctypes.wintypes.BOOL
    k32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    k32.UpdateProcThreadAttribute.restype = ctypes.wintypes.BOOL
    k32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    k32.CreateProcessW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.wintypes.BOOL, ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.LPCWSTR,
                                    ctypes.POINTER(_StartupInfoExW), ctypes.POINTER(_ProcessInformation)]
    k32.CreateProcessW.restype = ctypes.wintypes.BOOL

    sec_cap = _SecurityCapabilities(AppContainerSid=sid_out, Capabilities=None, CapabilityCount=0, Reserved=0)
    size = ctypes.c_size_t(0)
    k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    attr_list = ctypes.cast(buf, ctypes.c_void_p)
    if not k32.InitializeProcThreadAttributeList(attr_list, 1, 0, ctypes.byref(size)):
        return {"success": False, "stdout": "", "stderr": "InitializeProcThreadAttributeList failed",
                "return_code": -1, "timed_out": False, "duration_ms": 0.0}
    if not k32.UpdateProcThreadAttribute(attr_list, 0, _PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                                          ctypes.byref(sec_cap), ctypes.sizeof(sec_cap), None, None):
        k32.DeleteProcThreadAttributeList(attr_list)
        return {"success": False, "stdout": "", "stderr": "UpdateProcThreadAttribute failed",
                "return_code": -1, "timed_out": False, "duration_ms": 0.0}

    si = _StartupInfoExW()
    si.StartupInfo.cb = ctypes.sizeof(_StartupInfoExW)
    si.lpAttributeList = attr_list
    pi = _ProcessInformation()
    cmdline_buf = ctypes.create_unicode_buffer(wrapped)

    import win32event
    import win32job
    import win32process

    # Same memory/process-count caps as the Windows-account backend — the
    # AppContainer's own SID-based restrictions are about WHAT the process
    # can touch, not HOW MUCH of the machine it can consume, so this is
    # still needed as the fork-bomb/runaway-memory defense.
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

    start = time.time()
    # argtypes declares lpEnvironment as plain c_void_p — explicit cast
    # rather than trusting ctypes to auto-decay a c_wchar_Array into that
    # slot, since (unlike LPWSTR-typed params elsewhere in this call, which
    # do auto-convert) that decay is not guaranteed for a bare void pointer.
    env_ptr = ctypes.cast(env_block, ctypes.c_void_p)
    ok = k32.CreateProcessW(None, cmdline_buf, None, None, False,
                             _EXTENDED_STARTUPINFO_PRESENT | _CREATE_UNICODE_ENVIRONMENT,
                             env_ptr, str(cwd), ctypes.byref(si), ctypes.byref(pi))
    # Capture the real failure reason BEFORE any further ctypes call —
    # DeleteProcThreadAttributeList is itself a use_last_error=True kernel32
    # call, so calling it first clobbers CreateProcessW's actual error code
    # (confirmed live: reported a bogus, unrelated error until reordered).
    create_error = ctypes.get_last_error()
    k32.DeleteProcThreadAttributeList(attr_list)
    if not ok:
        job.Close()
        return {"success": False, "stdout": "", "stderr": f"CreateProcessW failed, error {create_error}",
                "return_code": -1, "timed_out": False, "duration_ms": round((time.time() - start) * 1000, 1)}

    win32job.AssignProcessToJobObject(job, pi.hProcess)

    h_process = pi.hProcess
    try:
        wait_result = win32event.WaitForSingleObject(h_process, int(timeout * 1000))
        timed_out = wait_result != win32event.WAIT_OBJECT_0
        if timed_out:
            win32job.TerminateJobObject(job, 1)
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pi.dwProcessId)], capture_output=True)
            return_code = -1
        else:
            return_code = win32process.GetExitCodeProcess(h_process)
    finally:
        job.Close()
        ctypes.windll.kernel32.CloseHandle(h_process)
        ctypes.windll.kernel32.CloseHandle(pi.hThread)

    stdout_data = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr_data = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""

    return {
        "success": (not timed_out) and return_code == 0,
        "stdout": stdout_data,
        "stderr": stderr_data,
        "return_code": return_code,
        "timed_out": timed_out,
        "duration_ms": round((time.time() - start) * 1000, 1),
    }


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
    backend = _active_backend()
    # _active_backend() only returns "appcontainer" once it has already
    # confirmed that backend is configured — "windows" is a fallback CHOICE,
    # not a guarantee, so that specific case still needs the readiness check
    # the original single-backend gate always did.
    if backend == "windows" and not sandbox_account_configured():
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
        if backend == "appcontainer":
            command_line = _build_appcontainer_command(language, code, session_dir)
        else:
            command_line = _build_command(language, code, session_dir)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    if backend == "appcontainer":
        result = _create_appcontainer_process(command_line, session_dir, timeout)
    else:
        env = _minimal_env()
        try:
            result = _create_sandboxed_process(command_line, session_dir, env, timeout)
        except SandboxPrivilegeError as e:
            return {"success": False, "error": str(e)}

    # script.py/script.js/script.bat is the code we wrote in, and the two
    # AppContainer output-capture files are plumbing, not results — neither
    # is something the code itself produced.
    files_created = _files_created(session_dir, exclude=_SCRIPT_NAMES | _APPCONTAINER_CAPTURE_NAMES, before=before)

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
