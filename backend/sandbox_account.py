"""One-time provisioning of a dedicated, low-privileged Windows account used
to run sandboxed code (see code_exec.py). This is the actual security
boundary: a process running as a different Windows account genuinely
cannot read this account's Credential Manager vault or profile folder —
env-var scrubbing and a scratch cwd alone can't deliver that, since they
don't change *which account* the code runs as.

This module deliberately does NOT create the account automatically. Account
creation requires administrator privilege and is a real system-security
change — it only happens via `request_elevated_provisioning()`, which asks
Windows to show the user a UAC prompt they approve themselves. Primnox's
own (non-elevated) process never gains elevated privileges; it launches a
short-lived, separate elevated process that does just the provisioning and
exits, then reports success/failure back.
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

from logger import get_logger

log = get_logger("sandbox_account")

SANDBOX_USERNAME = "PrimnoxSandbox"
KEYRING_SERVICE = "primnox_sandbox"
FIREWALL_RULE_NAME = "PrimnoxSandboxBlockOutbound"

# Windows logon-right constants used by LsaAddAccountRights — the sandbox
# account should only ever be usable via the programmatic logon type
# code_exec.py uses (LOGON32_LOGON_BATCH), never as a real interactive
# login, RDP session, or network logon.
_DENIED_LOGON_RIGHTS = ["SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight"]
# Ordinary user accounts do NOT have this right by default — without it,
# code_exec.py's LogonUser(..., LOGON32_LOGON_BATCH, ...) fails outright with
# "Logon failure: the user has not been granted the requested logon type at
# this computer." (confirmed via a live run_python smoke test). This is the
# one logon type the account needs to actually be usable.
_GRANTED_LOGON_RIGHTS = ["SeBatchLogonRight"]

# code_exec.py's CreateProcessAsUser call needs these on the CALLING
# process's OWN token (i.e. the real, logged-in user running Primnox — NOT
# the sandbox account above). Confirmed live: even a fully UAC-elevated
# admin token lacks SeAssignPrimaryTokenPrivilege ("Replace a process level
# token") by default — Windows reserves it for LOCAL SERVICE/NETWORK
# SERVICE, not interactive Administrators. Must match
# code_exec._REQUIRED_PRIVILEGES (kept as a separate literal here rather
# than importing code_exec, to avoid a sandbox_account <-> code_exec import
# cycle — code_exec already imports SANDBOX_USERNAME etc. from here).
_CALLER_PROCESS_CREATION_RIGHTS = ["SeAssignPrimaryTokenPrivilege", "SeIncreaseQuotaPrivilege"]


def _is_elevated() -> bool:
    import ctypes
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def account_exists(username: str = SANDBOX_USERNAME) -> bool:
    import win32net
    try:
        win32net.NetUserGetInfo(None, username, 0)
        return True
    except Exception:
        return False


def sandbox_account_configured() -> bool:
    """Cheap, read-only check — safe to call from the normal (non-elevated)
    Primnox process on every settings load / before every code execution.
    Both the account and its stored password must exist; either alone is
    an incomplete/broken setup."""
    if not account_exists():
        return False
    try:
        import keyring
        return bool(keyring.get_password(KEYRING_SERVICE, SANDBOX_USERNAME))
    except Exception as e:
        log.warning(f"Could not check sandbox keyring entry: {e}")
        return False


def request_elevated_provisioning(timeout_seconds: int = 180) -> dict:
    """Called from Primnox's normal (non-elevated) process — e.g. when the
    user clicks "Set up sandbox" in Settings. Launches this same module as
    a separate elevated process (triggering a UAC prompt the user must
    approve) with `--provision`, waits for it to finish, and reports the
    result. Returns {"success": bool, "error": str | None}."""
    from win32comext.shell.shell import ShellExecuteEx
    from win32comext.shell import shellcon
    import win32event
    import win32process

    script = str(Path(__file__).resolve())
    try:
        result = ShellExecuteEx(
            fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
            lpVerb="runas",
            lpFile=sys.executable,
            lpParameters=f'"{script}" --provision',
            nShow=1,
        )
    except Exception as e:
        # Commonly pywintypes.error 1223 (ERROR_CANCELLED) — the user
        # declined the UAC prompt. Not a bug, just a "no" — report plainly.
        log.info(f"Elevated provisioning request did not start: {e}")
        return {"success": False, "error": "elevation was declined or failed to start"}

    hProcess = result["hProcess"]
    try:
        wait_result = win32event.WaitForSingleObject(hProcess, timeout_seconds * 1000)
        if wait_result != win32event.WAIT_OBJECT_0:
            return {"success": False, "error": "provisioning timed out"}
        exit_code = win32process.GetExitCodeProcess(hProcess)
        if exit_code != 0:
            return {"success": False, "error": f"provisioning process exited with code {exit_code}"}
        return {"success": True, "error": None}
    finally:
        hProcess.Close()


def provision_sandbox_account() -> dict:
    """The actual provisioning logic — MUST only run inside an elevated
    process (refuses otherwise, as a defense-in-depth check even though the
    only real caller is the elevated subprocess launched above). Creates
    the account if it doesn't already exist, denies interactive/remote
    logon rights, stores a freshly generated password in the real user's
    keyring, grants the sandbox account access to the code-execution
    directory, adds a firewall rule blocking its outbound network access by
    default, and grants the REAL user's own account the two process-creation
    privileges CreateProcessAsUser needs from its caller. Idempotent — safe
    to call again if a later step failed partway (e.g. re-running after a
    firewall rule add failed)."""
    if not _is_elevated():
        return {"success": False, "error": "provisioning must run elevated"}

    import win32net
    import win32netcon
    import win32security
    import keyring

    try:
        password = secrets.token_urlsafe(32)

        if not account_exists():
            log.info(f"Creating sandbox account '{SANDBOX_USERNAME}'")
            win32net.NetUserAdd(None, 1, {
                "name": SANDBOX_USERNAME,
                "password": password,
                "priv": win32netcon.USER_PRIV_USER,
                "flags": win32netcon.UF_DONT_EXPIRE_PASSWD | win32netcon.UF_NORMAL_ACCOUNT,
                "comment": "Primnox sandboxed code-execution account — not for interactive login.",
            })
        else:
            # Account already exists (e.g. re-running after a partial
            # failure) — reset its password so we have a known-good value
            # to store, rather than assuming a prior stored one is still valid.
            win32net.NetUserSetInfo(None, SANDBOX_USERNAME, 1003, {"password": password})

        keyring.set_password(KEYRING_SERVICE, SANDBOX_USERNAME, password)

        sid, _domain, _type = win32security.LookupAccountName(None, SANDBOX_USERNAME)
        policy_handle = win32security.LsaOpenPolicy(
            None, win32security.POLICY_CREATE_ACCOUNT | win32security.POLICY_LOOKUP_NAMES
        )
        win32security.LsaAddAccountRights(policy_handle, sid, _DENIED_LOGON_RIGHTS)
        win32security.LsaAddAccountRights(policy_handle, sid, _GRANTED_LOGON_RIGHTS)

        _grant_folder_access(_code_exec_dir(), sid)
        _grant_python_interpreter_access(sid)
        _grant_node_access(sid)
        _add_firewall_block_rule(sid)
        _grant_caller_process_creation_rights()

        log.info("Sandbox account provisioning complete.")
        return {"success": True, "error": None}
    except Exception as e:
        log.error(f"Sandbox account provisioning failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _grant_caller_process_creation_rights() -> None:
    """Grants SeAssignPrimaryTokenPrivilege + SeIncreaseQuotaPrivilege to the
    REAL logged-in user's account (whoever this elevated process is running
    as — UAC elevation changes the token type, not the account identity).
    code_exec.py's _enable_own_privileges() only enables privileges the
    account already holds; this is what makes them holdable in the first
    place.

    Takes effect only after the next logon — Windows computes a token's
    privilege set at logon time, so the session that ran the provisioning
    keeps its stale token (elevated or not) until the user signs out or
    reboots. Verified after a real reboot: a normal, NON-elevated Primnox
    process can then enable both privileges, so running Primnox as admin
    is not required."""
    import win32api
    import win32security

    username = win32api.GetUserName()
    sid, _domain, _type = win32security.LookupAccountName(None, username)
    policy_handle = win32security.LsaOpenPolicy(
        None, win32security.POLICY_CREATE_ACCOUNT | win32security.POLICY_LOOKUP_NAMES
    )
    win32security.LsaAddAccountRights(policy_handle, sid, _CALLER_PROCESS_CREATION_RIGHTS)
    log.info(f"Granted process-creation rights to '{username}' (needed to launch sandboxed processes).")


def _code_exec_dir() -> Path:
    from sandbox_manager import code_exec_dir
    return code_exec_dir()


def _grant_folder_access(path: Path, sid, read_only: bool = False) -> None:
    """Grants the sandbox account access to `path` AND everything created
    under it later.

    Uses icacls rather than the pywin32 DACL APIs because inheritance alone
    provably isn't enough here, for two separate reasons found live:

    1. An ACE without OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE covers only
       the directory object itself, so the per-execution session
       subdirectories code_exec.py creates inside CodeExecution/ inherited
       only the real user's ACL and the sandbox account hit "Access is
       denied." on its first write.
    2. Even *with* inheritance flags, children that already exist and have a
       protected (inheritance-blocked) DACL never receive the ACE. Every
       file in a per-user Python install is exactly that — `icacls
       python.exe` showed only SYSTEM/Administrators/<user>, so the
       sandboxed process died with STATUS_ACCESS_DENIED (0xC0000022) trying
       to execute it, even though the parent directory grant had succeeded.

    This takes TWO icacls passes, and both are required — a single
    `(OI)(CI)` + /T call looks like it works but doesn't. Inheritance flags
    are only valid on directories, so with /T icacls applies the ACE to
    every subdirectory and silently skips every *file* (with /C suppressing
    the errors and still exiting 0). Verified after such a run: the Lib\\
    directory had the ACE while python311.dll next to it did not, and the
    sandboxed interpreter still died with STATUS_ACCESS_DENIED.

      pass 1 — (OI)(CI), no /T : inheritable ACE on the directory, so
                                 anything created here LATER is covered.
      pass 2 — no flags, /T    : plain ACE applied to the directory and to
                                 every file/subdirectory that already
                                 exists, including ones whose own DACL
                                 blocks inheritance (every file in a
                                 per-user Python install is like this).

    /C keeps pass 2 going instead of aborting on the first locked file.
    Shelling out matches this module's existing approach for the firewall
    rule.
    """
    import subprocess

    path.mkdir(parents=True, exist_ok=True)
    path_str = str(path)
    sid_string = _sid_to_string(sid)
    # RX = read + execute; M = modify (read/write/delete). Applied by SID
    # rather than name so a renamed account can't silently break it.
    rights = "(RX)" if read_only else "(M)"

    passes = [
        (["icacls", path_str, "/grant", f"*{sid_string}:(OI)(CI){rights}", "/Q"], "inheritable"),
        (["icacls", path_str, "/grant", f"*{sid_string}:{rights}", "/T", "/C", "/Q"], "existing-children"),
    ]
    for cmd, label in passes:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"icacls {label} grant on {path_str} failed: {result.stderr or result.stdout}"
            )
    log.info(f"Granted sandbox account {'read' if read_only else 'full'} access to {path_str}")


def _sid_to_string(sid) -> str:
    import win32security
    return win32security.ConvertSidToStringSid(sid)


def _grant_python_interpreter_access(sid) -> None:
    """The sandbox runs the same interpreter Primnox itself uses
    (code_exec._build_command uses sys.executable), so the sandbox account
    needs read+execute on the Python installation. When Python is installed
    per-user it lives under C:\\Users\\<you>\\AppData\\Local\\Programs\\...,
    which is ACL'd to that user alone — the sandboxed process died with
    STATUS_ACCESS_DENIED (0xC0000022) before running a single line
    (confirmed live). Read-only: the sandbox may execute the interpreter and
    import stdlib/site-packages, never modify them.

    Deliberately NOT granted: APPDATA/Roaming (settings.json lives there)
    and the Windows Credential Manager vault — the sandbox account still
    cannot reach any Primnox secret. A system-wide Python install
    (C:\\Program Files\\...) is already readable by all users, making this a
    harmless no-op there.
    """
    python_dir = Path(sys.executable).parent
    try:
        _grant_folder_access(python_dir, sid, read_only=True)
    except Exception as e:
        # Non-fatal: run_shell still works without it, and a system-wide
        # install needs no grant at all. Log loudly rather than failing the
        # whole provisioning run over it.
        log.warning(f"Could not grant sandbox read access to the Python install at {python_dir}: {e}")


def _grant_node_access(sid) -> None:
    """Same problem as the Python interpreter, for Node.

    The official pptx and docx skills build their output with pptxgenjs and
    docx-js, so code_exec.run_node has to launch node.exe as the sandbox
    account. The account is created with no group memberships at all — not
    even Users — so it gets only the ACEs granted to it explicitly, and the
    default Program Files ACL (which grants Users, not everyone) doesn't
    reach it. node.exe then died with STATUS_DLL_INIT_FAILED (0xC0000142)
    before running a line, while python.exe in the already-granted install
    directory ran fine (confirmed live, same sandbox account, same run).

    Read+execute only, and a no-op when node isn't installed — Node is
    optional, and every Python-based skill works without it.
    """
    import shutil

    node_exe = shutil.which("node")
    if not node_exe:
        log.info("Node not installed — skipping sandbox grant (JS-based skills will be unavailable).")
        return
    node_dir = Path(node_exe).parent
    try:
        _grant_folder_access(node_dir, sid, read_only=True)
        log.info(f"Granted sandbox account read access to the Node install at {node_dir}")
    except Exception as e:
        log.warning(f"Could not grant sandbox read access to the Node install at {node_dir}: {e}")


def _add_firewall_block_rule(sid) -> None:
    import subprocess
    import win32security

    sid_string = win32security.ConvertSidToStringSid(sid)
    # "CC" is the SDDL access mask netsh/NetSecurity expect for a
    # local-user-scoped ACE in a firewall rule (not a real file/object
    # permission — it's just the token this API reads to know which SID to
    # match against).
    sddl = f"D:(A;;CC;;;{sid_string})"

    # netsh's advfirewall CLI does NOT support localuser= on this Windows
    # build — `netsh advfirewall firewall add rule ?` omits it entirely from
    # the supported parameter list, and passing it fails outright with
    # "'localuser' is not a valid argument for this command." (confirmed via
    # a live provisioning attempt). New-NetFirewallRule's -LocalUser
    # (NetSecurity PowerShell module, Windows 8 / Server 2012+) is the
    # actually-supported way to scope a rule to one local account via SDDL.
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"Remove-NetFirewallRule -DisplayName '{FIREWALL_RULE_NAME}' -ErrorAction SilentlyContinue"],
        capture_output=True,
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"New-NetFirewallRule -DisplayName '{FIREWALL_RULE_NAME}' -Direction Outbound "
         f"-Action Block -LocalUser '{sddl}' -Enabled True"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"firewall rule creation failed: {result.stderr or result.stdout}")
    log.info(f"Added outbound-block firewall rule for sandbox account (SID {sid_string})")


if __name__ == "__main__":
    if "--provision" in sys.argv:
        outcome = provision_sandbox_account()
        sys.exit(0 if outcome.get("success") else 1)
