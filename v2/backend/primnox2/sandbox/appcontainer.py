"""AppContainer isolation — V2's own implementation.

Modelled on V1's, which earned every detail in here the hard way. The
investigation lives in `docs/sandbox-runtime-limitations.md`; this module is
the conclusion, rewritten so the V2 sandbox owns its execution primitive
outright rather than reaching into V1.

Why AppContainer and not a separate Windows account: a separate `LogonUser()`
session lacks the winlogon-minted logon-session SID that `USER32.dll`'s own
initialiser requires, so a large fraction of Windows — Node, Pillow,
PowerShell, even `notepad.exe` — simply refuses to start inside one.
AppContainer creates no separate logon session at all. It mints an isolated
SID and launches via plain `CreateProcess` inside Primnox's own session, so
the process inherits the session's already-legitimate window station.

Four things are load-bearing and must not be "simplified":

1. **Never STARTF_USESTDHANDLES.** Attaching std handles kills the
   AppContainer process with STATUS_DLL_INIT_FAILED regardless of handle
   type. Output is captured by having the child redirect its *own* streams to
   files from inside the process.
2. **`LOCALAPPDATA` must be in the environment block.** AppContainer's
   per-container storage redirection needs it; without it `CreateProcessW`
   fails outright with ERROR_ENVVAR_NOT_FOUND.
3. **Node needs `--preserve-symlinks --preserve-symlinks-main`.** Node
   realpath-resolves its entry script by walking up to the drive root, which
   the container was never granted — correct isolation, but it kills Node
   before any user code runs. Both flags are needed: the first covers
   `require()`, the second the entry module.
4. **Read `GetLastError` before `DeleteProcThreadAttributeList`.** That
   cleanup call is itself a kernel32 call and clobbers the real failure code.

The ACL grant takes two icacls passes. One `(OI)(CI) /T` call looks correct
and is not: inheritance flags are only valid on directories, so with `/T`
icacls silently skips every *file*.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time
from pathlib import Path

from .. import paths

APPCONTAINER_NAME = "PrimnoxSandboxV2"
DISPLAY_NAME = "Primnox V2 Sandbox"
MARKER_NAME = ".appcontainer_provisioned_v2"

STDOUT_NAME = "__ac_stdout.txt"
STDERR_NAME = "__ac_stderr.txt"
WRAPPER_PY = "__ac_wrapper.py"
WRAPPER_JS = "__ac_wrapper.js"

# Plumbing the snapshot diff must ignore — none of it is a result.
PLUMBING = {STDOUT_NAME, STDERR_NAME, WRAPPER_PY, WRAPPER_JS, "package.json"}

_IS_WINDOWS = os.name == "nt"

if _IS_WINDOWS:
    _userenv = ctypes.WinDLL("userenv", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _userenv.CreateAppContainerProfile.argtypes = [
        wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _userenv.CreateAppContainerProfile.restype = ctypes.c_long
    _userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [
        wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    _userenv.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long
    _advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.LPWSTR)]
    _advapi32.ConvertSidToStringSidW.restype = wt.BOOL
    _advapi32.ConvertStringSidToSidW.argtypes = [wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.ConvertStringSidToSidW.restype = wt.BOOL

_S_OK = 0
_ERROR_ALREADY_EXISTS = 0x800700B7

_PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_CREATE_NO_WINDOW = 0x08000000

_JobObjectExtendedLimitInformation = 9
_JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
_JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_WAIT_OBJECT_0 = 0x00000000

MAX_ACTIVE_PROCESSES = 64


class SandboxUnavailable(RuntimeError):
    """Isolation could not be established. Never a reason to run unisolated."""


# ── Win32 structures ─────────────────────────────────────────────────────────
class _SecurityCapabilities(ctypes.Structure):
    _fields_ = [("AppContainerSid", ctypes.c_void_p), ("Capabilities", ctypes.c_void_p),
                ("CapabilityCount", wt.DWORD), ("Reserved", wt.DWORD)]


class _StartupInfoW(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR),
        ("lpTitle", wt.LPWSTR), ("dwX", wt.DWORD), ("dwY", wt.DWORD),
        ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD), ("dwXCountChars", wt.DWORD),
        ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD), ("dwFlags", wt.DWORD),
        ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD), ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", ctypes.c_void_p), ("hStdOutput", ctypes.c_void_p),
        ("hStdError", ctypes.c_void_p),
    ]


class _StartupInfoExW(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfoW), ("lpAttributeList", ctypes.c_void_p)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
                ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _JobBasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wt.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wt.DWORD),
        ("Affinity", ctypes.POINTER(ctypes.c_ulong)), ("PriorityClass", wt.DWORD),
        ("SchedulingClass", wt.DWORD),
    ]


class _JobExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobBasicLimits), ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


# ── Profile and SID ──────────────────────────────────────────────────────────
_sid_cache: str | None = None


def sid_string() -> str:
    """Create the profile if absent and return its SID.

    Idempotent: a second create on an existing name returns
    ERROR_ALREADY_EXISTS, which is a success path, not a failure. AppContainer
    SIDs are deterministic from the name, so this is stable across runs.
    """
    global _sid_cache
    if _sid_cache:
        return _sid_cache
    if not _IS_WINDOWS:
        raise SandboxUnavailable("AppContainer is Windows-only")

    sid_ptr = ctypes.c_void_p()
    hr = _userenv.CreateAppContainerProfile(
        APPCONTAINER_NAME, DISPLAY_NAME, "Sandboxed code execution",
        None, 0, ctypes.byref(sid_ptr),
    )
    if (hr & 0xFFFFFFFF) == _ERROR_ALREADY_EXISTS:
        hr = _userenv.DeriveAppContainerSidFromAppContainerName(
            APPCONTAINER_NAME, ctypes.byref(sid_ptr))
    if hr != _S_OK:
        raise SandboxUnavailable(f"could not obtain AppContainer SID (HRESULT 0x{hr & 0xFFFFFFFF:08x})")

    out = wt.LPWSTR()
    if not _advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(out)):
        raise SandboxUnavailable("ConvertSidToStringSidW failed")
    _sid_cache = out.value
    return _sid_cache


def _marker_path() -> Path:
    return paths.root() / "sandbox" / MARKER_NAME


def _interpreter_marker() -> Path:
    """Marker for the interpreter grants, which are machine-global.

    Kept OUT of the per-root tree on purpose. Granting the AppContainer SID
    read access to the interpreter walks the whole install with icacls /T and
    costs ~80 seconds; the resulting ACEs live on the interpreter itself, not
    on any Primnox directory, so repeating that walk for every new data root
    (which is what every test run is) buys nothing at all.
    """
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base) / "Primnox2"
    d.mkdir(parents=True, exist_ok=True)
    return d / ".appcontainer_interpreter_grants"


def _interpreter_fingerprint(sid: str) -> str:
    return sid + "|" + "|".join(sorted(str(p) for p in _interpreter_dirs()))


def configured() -> bool:
    """Profile exists AND provisioning finished.

    The marker is written last, after every grant succeeded, so its presence
    means the whole sequence completed — not merely that it was attempted.
    """
    if not _IS_WINDOWS:
        return False
    try:
        sid = sid_string()
    except SandboxUnavailable:
        return False
    marker = _marker_path()
    if not marker.is_file():
        return False
    try:
        return marker.read_text(encoding="utf-8").strip() == sid
    except OSError:
        return False


def _icacls_grant(path: Path, sid: str, *, read_only: bool) -> None:
    """Two passes, both required.

    pass 1  (OI)(CI) without /T — an inheritable ACE, so anything created here
            later is covered.
    pass 2  no flags, with /T    — a plain ACE on every file and subdirectory
            that already exists, including ones whose own DACL blocks
            inheritance. Every file in a per-user Python install is like that.
    """
    rights = "(RX)" if read_only else "(F)"
    subprocess.run(["icacls", str(path), "/grant", f"*{sid}:(OI)(CI){rights}"],
                   capture_output=True, timeout=120)
    subprocess.run(["icacls", str(path), "/grant", f"*{sid}:{rights}", "/T", "/C"],
                   capture_output=True, timeout=300)


def _interpreter_dirs() -> list[Path]:
    """Directories the container must be able to read to start an interpreter.

    The venv ROOT is included, not just `Scripts/`. `pyvenv.cfg` lives in the
    root, and without it the interpreter starts and immediately dies with
    "No pyvenv.cfg file" — a failure that looks like a broken sandbox rather
    than a missing grant.
    """
    exe = Path(sys.executable)
    dirs = [exe.parent]
    if exe.parent.name.lower() in ("scripts", "bin"):
        dirs.append(exe.parent.parent)
    base = Path(getattr(sys, "base_prefix", sys.prefix))
    if base.exists() and base not in dirs:
        dirs.append(base)
    return dirs


def provision() -> dict:
    """One-time setup. Non-elevated, idempotent, safe to re-run."""
    if not _IS_WINDOWS:
        return {"ok": False, "error": "AppContainer is Windows-only"}
    try:
        sid = sid_string()
    except SandboxUnavailable as exc:
        return {"ok": False, "error": str(exc)}

    # The expensive, machine-global half — skipped when it has already been
    # done for this SID and this interpreter.
    granted: list[str] = []
    fingerprint = _interpreter_fingerprint(sid)
    marker = _interpreter_marker()
    already = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
    if already != fingerprint:
        for directory in _interpreter_dirs():
            try:
                _icacls_grant(directory, sid, read_only=True)
                granted.append(str(directory))
            except (OSError, subprocess.SubprocessError):
                continue
        try:
            marker.write_text(fingerprint, encoding="utf-8")
        except OSError:
            pass

    sandbox_root = paths.root() / "sandbox"
    sandbox_root.mkdir(parents=True, exist_ok=True)
    try:
        _icacls_grant(sandbox_root, sid, read_only=False)
        _icacls_grant(paths.workspaces_dir(), sid, read_only=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": f"could not grant workspace access: {exc}"}

    _marker_path().write_text(sid, encoding="utf-8")
    return {"ok": True, "sid": sid, "granted": granted}


def ensure_provisioned() -> bool:
    return True if configured() else bool(provision().get("ok"))


# ── Command construction ─────────────────────────────────────────────────────
def _node_executable() -> str:
    from shutil import which
    return which("node") or "node.exe"


def build_command(runtime: str, code: str, session_dir: Path) -> str:
    """Write the wrapper and return the complete command line.

    The wrapper exists so the child redirects its own stdout/stderr from
    inside the process. Attaching std handles from out here is what makes an
    AppContainer process die before running a line.
    """
    stdout_path = session_dir / STDOUT_NAME
    stderr_path = session_dir / STDERR_NAME

    if runtime == "python":
        script = session_dir / "main.py"
        script.write_text(code, encoding="utf-8", newline="")
        wrapper = session_dir / WRAPPER_PY
        wrapper.write_text(
            "import sys\n"
            f"sys.stdout = open(r'{stdout_path}', 'w', encoding='utf-8')\n"
            f"sys.stderr = open(r'{stderr_path}', 'w', encoding='utf-8')\n"
            "try:\n"
            f"    _src = open(r'{script}', encoding='utf-8').read()\n"
            f"    exec(compile(_src, r'{script}', 'exec'), {{'__name__': '__main__'}})\n"
            "except SystemExit:\n"
            "    raise\n"
            "except BaseException:\n"
            "    import traceback; traceback.print_exc()\n"
            "    sys.exit(1)\n"
            "finally:\n"
            "    sys.stdout.flush(); sys.stderr.flush()\n",
            encoding="utf-8",
        )
        return f'"{sys.executable}" "{wrapper}"'

    if runtime == "node":
        script = session_dir / "main.js"
        script.write_text(code, encoding="utf-8", newline="")
        # Stops a package-scope lookup walking up past the workspace. On its
        # own it does not fix the realpath EPERM — the flags below do that.
        (session_dir / "package.json").write_text("{}", encoding="utf-8")
        wrapper = session_dir / WRAPPER_JS
        wrapper.write_text(
            "const fs = require('fs');\n"
            f"const __out = fs.openSync(String.raw`{stdout_path}`, 'w');\n"
            f"const __err = fs.openSync(String.raw`{stderr_path}`, 'w');\n"
            "process.stdout.write = (c, e, cb) => { fs.writeSync(__out, c); "
            "if (typeof e === 'function') e(); else if (typeof cb === 'function') cb(); return true; };\n"
            "process.stderr.write = (c, e, cb) => { fs.writeSync(__err, c); "
            "if (typeof e === 'function') e(); else if (typeof cb === 'function') cb(); return true; };\n"
            "try {\n"
            f"  require(String.raw`{script}`);\n"
            "} catch (e) {\n"
            "  process.stderr.write(String((e && e.stack) || e) + '\\n');\n"
            "  process.exitCode = 1;\n"
            "}\n",
            encoding="utf-8",
        )
        return (f'"{_node_executable()}" --preserve-symlinks --preserve-symlinks-main '
                f'"{wrapper}"')

    if runtime == "shell":
        script = session_dir / "main.cmd"
        script.write_text(code, encoding="utf-8", newline="")
        comspec = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        return f'"{comspec}" /c "{code} > "{stdout_path}" 2> "{stderr_path}""'

    raise ValueError(f"unknown runtime {runtime!r}")


def _environment(session_dir: Path) -> dict:
    """A minimal environment.

    `LOCALAPPDATA` is mandatory — AppContainer's storage redirection needs it
    and `CreateProcessW` fails with ERROR_ENVVAR_NOT_FOUND without it. It is
    distinct from `APPDATA`/Roaming, where secrets live, so including it
    exposes nothing new.
    """
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    env = {
        "SystemRoot": system_root,
        "windir": system_root,
        "COMSPEC": os.environ.get("COMSPEC", rf"{system_root}\System32\cmd.exe"),
        "PATH": os.pathsep.join([
            rf"{system_root}\System32", system_root, rf"{system_root}\System32\Wbem",
            str(Path(sys.executable).parent),
        ]),
        "PATHEXT": ".COM;.EXE;.BAT;.CMD;.JS",
        "TEMP": str(session_dir / "temp"),
        "TMP": str(session_dir / "temp"),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", str(session_dir / "temp")),
        "NUMBER_OF_PROCESSORS": os.environ.get("NUMBER_OF_PROCESSORS", "1"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return env


def _environment_block(env: dict) -> ctypes.Array:
    """`KEY=VALUE\\0` per entry, with a trailing `\\0`.

    Requires CREATE_UNICODE_ENVIRONMENT in the creation flags — without it
    Windows reads this block as ANSI and corrupts every entry.
    """
    return ctypes.create_unicode_buffer("".join(f"{k}={v}\0" for k, v in env.items()) + "\0")


# ── Launch ───────────────────────────────────────────────────────────────────
def run(session_dir: Path, runtime: str, code: str, *, timeout_s: float,
        memory_mb: int = 1024) -> dict:
    """Launch inside the AppContainer and wait. Returns a plain result dict."""
    if not _IS_WINDOWS:
        raise SandboxUnavailable("AppContainer is Windows-only")
    if not configured() and not ensure_provisioned():
        raise SandboxUnavailable("AppContainer profile is not provisioned")

    command = build_command(runtime, code, session_dir)

    sid_ptr = ctypes.c_void_p()
    if not _advapi32.ConvertStringSidToSidW(sid_string(), ctypes.byref(sid_ptr)):
        raise SandboxUnavailable("could not resolve the AppContainer SID")

    _k32.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.c_size_t)]
    _k32.InitializeProcThreadAttributeList.restype = wt.BOOL
    _k32.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p, wt.DWORD, ctypes.c_size_t, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    _k32.UpdateProcThreadAttribute.restype = wt.BOOL
    _k32.CreateProcessW.argtypes = [
        wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL, wt.DWORD,
        ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(_StartupInfoExW),
        ctypes.POINTER(_ProcessInformation)]
    _k32.CreateProcessW.restype = wt.BOOL

    caps = _SecurityCapabilities(AppContainerSid=sid_ptr, Capabilities=None,
                                 CapabilityCount=0, Reserved=0)
    size = ctypes.c_size_t(0)
    _k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    attr_list = ctypes.cast(buf, ctypes.c_void_p)
    if not _k32.InitializeProcThreadAttributeList(attr_list, 1, 0, ctypes.byref(size)):
        raise SandboxUnavailable("InitializeProcThreadAttributeList failed")
    if not _k32.UpdateProcThreadAttribute(
            attr_list, 0, _PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            ctypes.byref(caps), ctypes.sizeof(caps), None, None):
        _k32.DeleteProcThreadAttributeList(attr_list)
        raise SandboxUnavailable("UpdateProcThreadAttribute failed")

    si = _StartupInfoExW()
    si.StartupInfo.cb = ctypes.sizeof(_StartupInfoExW)
    si.lpAttributeList = attr_list
    pi = _ProcessInformation()

    # The AppContainer SID restricts WHAT the process may touch, not HOW MUCH
    # of the machine it may consume. The Job Object is the runaway-memory and
    # fork-bomb defence, and is still required.
    job = _k32.CreateJobObjectW(None, None)
    if job:
        limits = _JobExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_JOB_MEMORY | _JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
        limits.JobMemoryLimit = memory_mb * 1024 * 1024
        limits.BasicLimitInformation.ActiveProcessLimit = MAX_ACTIVE_PROCESSES
        _k32.SetInformationJobObject(job, _JobObjectExtendedLimitInformation,
                                     ctypes.byref(limits), ctypes.sizeof(limits))

    env_block = _environment_block(_environment(session_dir))
    cmd_buf = ctypes.create_unicode_buffer(command)
    started = time.time()

    ok = _k32.CreateProcessW(
        None, cmd_buf, None, None, False,
        _EXTENDED_STARTUPINFO_PRESENT | _CREATE_UNICODE_ENVIRONMENT | _CREATE_NO_WINDOW,
        ctypes.cast(env_block, ctypes.c_void_p), str(session_dir),
        ctypes.byref(si), ctypes.byref(pi),
    )
    # Read the error BEFORE the cleanup call below — DeleteProcThreadAttributeList
    # is itself a kernel32 call and overwrites it.
    create_error = ctypes.get_last_error()
    _k32.DeleteProcThreadAttributeList(attr_list)

    if not ok:
        if job:
            _k32.CloseHandle(job)
        raise SandboxUnavailable(f"CreateProcessW failed (error {create_error})")

    if job:
        _k32.AssignProcessToJobObject(job, pi.hProcess)

    timed_out = False
    exit_code = None
    try:
        wait = _k32.WaitForSingleObject(pi.hProcess, int(timeout_s * 1000))
        if wait != _WAIT_OBJECT_0:
            timed_out = True
            if job:
                _k32.TerminateJobObject(job, 1)
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pi.dwProcessId)],
                           capture_output=True)
        else:
            code_out = wt.DWORD()
            _k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code_out))
            exit_code = code_out.value
    finally:
        if job:
            _k32.CloseHandle(job)
        _k32.CloseHandle(pi.hProcess)
        _k32.CloseHandle(pi.hThread)

    def _read(name: str) -> str:
        p = session_dir / name
        try:
            return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        except OSError:
            return ""

    return {
        "exit_code": exit_code,
        "stdout": _read(STDOUT_NAME),
        "stderr": _read(STDERR_NAME),
        "timed_out": timed_out,
        "duration_ms": int((time.time() - started) * 1000),
    }
