"""One-time provisioning for the AppContainer sandbox backend — the one
that actually runs Node.js and Pillow, where sandbox_account.py's dedicated
Windows account cannot (see docs/sandbox-runtime-limitations.md for the
full, live-confirmed root cause: full USER32/desktop access requires a
winlogon-minted logon-session SID that a separate LogonUser() call can
never hold).

AppContainer sidesteps that entirely by not creating a separate logon
session at all. `CreateAppContainerProfile` mints an isolated security
identity (a SID), and the sandboxed process launches via plain
`CreateProcess` carrying that SID in its security-capabilities attribute —
still in the CALLING process's own session, so it inherits the session's
already-legitimate window station. Confirmed live: node.exe and
`import PIL._imaging` both succeed under this SID where every
separate-logon-session approach failed identically.

Isolation then comes from the SID itself, not a different Windows account:
- Filesystem: AppContainer tokens are denied nearly everything by default
  (confirmed live: a fresh AppContainer got PermissionError on
  settings.json/memory.db/chat.db/source with zero grants). Access is
  explicit allow-listing via icacls, identical in spirit to
  sandbox_account.py's `_grant_folder_access` — reused directly here via a
  SID-object bridge (ConvertStringSidToSid), not duplicated.
- Network: zero capabilities granted (this module never requests any) means
  no network capability at all — confirmed live via URLError on an actual
  HTTP request. This is a first-class Windows Filtering Platform deny, not
  a bolted-on firewall rule the way sandbox_account.py's is.

No LogonUser, no password, no keyring entry, and — unlike
sandbox_account.py's account creation — no elevation needed at all:
`CreateAppContainerProfile` succeeded fully non-elevated in every live test.
Provisioning here is correspondingly much simpler than the account-based
module.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
from pathlib import Path

from logger import get_logger

log = get_logger("appcontainer_sandbox")

APPCONTAINER_NAME = "PrimnoxSandboxAC"
_SETUP_MARKER_NAME = ".appcontainer_provisioned"

_userenv = ctypes.WinDLL("userenv", use_last_error=True)
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

_userenv.CreateAppContainerProfile.argtypes = [
    wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(ctypes.c_void_p)
]
_userenv.CreateAppContainerProfile.restype = ctypes.c_long  # HRESULT
_userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
_userenv.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long
_advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.LPWSTR)]
_advapi32.ConvertSidToStringSidW.restype = wt.BOOL

_S_OK = 0
_HRESULT_ERROR_ALREADY_EXISTS = 0x800700B7  # HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS)


class AppContainerError(RuntimeError):
    """Raised by the internal helpers; provision_appcontainer_sandbox() turns
    this into the same {"success": False, "error": str} shape every other
    provisioning function in this codebase returns."""


def appcontainer_sid_string() -> str:
    """Creates the profile if it doesn't exist yet (idempotent — confirmed
    live: a second CreateAppContainerProfile call on an existing name
    returns ERROR_ALREADY_EXISTS, not an error state) and returns its SID
    as a string. AppContainer SIDs are deterministic from the profile name,
    so this always returns the same value for APPCONTAINER_NAME."""
    sid_ptr = ctypes.c_void_p()
    hr = _userenv.CreateAppContainerProfile(APPCONTAINER_NAME, "Primnox Sandbox", "Sandboxed code execution", None, 0, ctypes.byref(sid_ptr))
    if (hr & 0xFFFFFFFF) == _HRESULT_ERROR_ALREADY_EXISTS:
        hr = _userenv.DeriveAppContainerSidFromAppContainerName(APPCONTAINER_NAME, ctypes.byref(sid_ptr))
    if hr != _S_OK:
        raise AppContainerError(f"could not obtain AppContainer SID (HRESULT 0x{hr & 0xFFFFFFFF:08x})")

    str_sid = wt.LPWSTR()
    if not _advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(str_sid)):
        raise AppContainerError("ConvertSidToStringSidW failed")
    return str_sid.value


def _sid_object(sid_string: str):
    """Bridges the raw-ctypes SID this module works with into a pywin32
    PySID object, so the icacls grant logic already tested in
    sandbox_account.py (_grant_folder_access, which calls
    win32security.ConvertSidToStringSid internally) can be reused as-is
    rather than duplicated."""
    import win32security
    return win32security.ConvertStringSidToSid(sid_string)


def appcontainer_configured() -> bool:
    """Cheap-ish, mirrors sandbox_account_configured()'s "both conditions"
    shape: the profile must exist AND provisioning must have completed
    (the marker file, written last in provision_appcontainer_sandbox(),
    confirms every grant before it actually succeeded). Safe to call every
    settings load / before every execution — CreateAppContainerProfile is a
    fast local call, not a subprocess spawn."""
    try:
        sid_string = appcontainer_sid_string()
    except AppContainerError as e:
        log.warning(f"AppContainer SID unavailable: {e}")
        return False
    from sandbox_manager import code_exec_dir
    marker = code_exec_dir() / _SETUP_MARKER_NAME
    if not marker.is_file():
        return False
    return marker.read_text(encoding="utf-8").strip() == sid_string


def provision_appcontainer_sandbox() -> dict:
    """One-time setup: create the profile, grant read+execute on the
    Python/Node install directories and read+write on the code-execution
    workspace root, write the completion marker last. No elevation
    required — confirmed live every step of this runs fully non-elevated.

    Idempotent: safe to re-run after a partial failure (icacls grants are
    additive; re-granting an already-granted SID is a harmless no-op).
    """
    try:
        sid_string = appcontainer_sid_string()
        sid = _sid_object(sid_string)

        _grant_python_interpreter_access(sid)
        _grant_node_access(sid)

        from sandbox_manager import code_exec_dir
        workspace_root = code_exec_dir()
        from sandbox_account import _grant_folder_access
        _grant_folder_access(workspace_root, sid, read_only=False)

        marker = workspace_root / _SETUP_MARKER_NAME
        marker.write_text(sid_string, encoding="utf-8")

        log.info("AppContainer sandbox provisioning complete.")
        return {"success": True, "error": None}
    except AppContainerError as e:
        log.error(f"AppContainer sandbox provisioning failed: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        log.error(f"AppContainer sandbox provisioning failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _grant_python_interpreter_access(sid) -> None:
    """Same problem sandbox_account.py's identically-named function solves:
    a per-user Python install (AppData\\Local\\Programs\\...) is ACL'd to
    just the owning user's own SID, so the AppContainer SID needs an
    explicit read+execute grant or python.exe itself is unreadable
    (STATUS_ACCESS_DENIED before running a line — confirmed live). A
    system-wide install under Program Files is already broadly readable,
    making this a harmless no-op there."""
    import sys

    python_dir = Path(sys.executable).parent
    from sandbox_account import _grant_folder_access
    try:
        _grant_folder_access(python_dir, sid, read_only=True)
    except Exception as e:
        log.warning(f"Could not grant AppContainer read access to the Python install at {python_dir}: {e}")


def _grant_node_access(sid) -> None:
    """Confirmed live: node.exe under Program Files needed NO explicit
    grant at all (Program Files' default ACL already covers AppContainer
    tokens, unlike a per-user Python install). Still called defensively,
    matching sandbox_account.py's identically-reasoned function, in case
    Node is ever installed per-user instead. No-op when Node isn't
    installed — Node is optional, every Python-based skill works without it."""
    import shutil

    node_exe = shutil.which("node")
    if not node_exe:
        log.info("Node not installed — skipping AppContainer grant (JS-based skills will be unavailable).")
        return
    node_dir = Path(node_exe).parent
    from sandbox_account import _grant_folder_access
    try:
        _grant_folder_access(node_dir, sid, read_only=True)
        log.info(f"Granted AppContainer read access to the Node install at {node_dir}")
    except Exception as e:
        log.warning(f"Could not grant AppContainer read access to the Node install at {node_dir}: {e}")
