"""Runs document-generation (PDF/PPTX) inside the sandboxed Windows account
instead of in Primnox's own process.

Why bother, when the reportlab/python-pptx calls are Primnox's own reviewed
code? Because the *content* fed into them isn't: it's model output derived
from whatever the user pasted, a fetched web page, a meeting transcript. A
malformed-document parser bug or a path that escapes the intended output
directory then executes with Primnox's full privileges — access to
settings.json (API keys), memory.db, and the network. Rendering as
PrimnoxSandbox instead means the worst case is a corrupt file in a scratch
directory that gets quota-evicted.

Falls back to in-process rendering when the sandbox isn't usable (not yet
provisioned, or code_execution_enabled is off). That fallback is the whole
reason this is safe to adopt now: PDF generation keeps working exactly as
before on a machine where the sandbox was never set up, and silently
upgrades to isolated rendering on one where it was.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from logger import get_logger

log = get_logger("skill.sandboxed_render")


def sandbox_available(requires: tuple[str, ...] = ()) -> bool:
    """True only when a sandboxed render would actually run. Checks the same
    two gates code_exec._run() enforces, so this never promises isolation
    the execution layer would then refuse to provide.

    `requires` names the libraries the render actually needs, checked against
    what has been probed to work *inside* the sandbox. Without that, a PDF
    render would spawn a sandboxed process, wait for reportlab to fail on
    Pillow's native extension, and only then fall back — paying the full
    cost of an execution to learn something already known.
    """
    try:
        from settings_manager import load_settings
        if not load_settings().get("code_execution_enabled"):
            return False
        from sandbox_account import sandbox_account_configured
        if not sandbox_account_configured():
            return False
        if requires:
            import runtime_capabilities
            caps = runtime_capabilities.detect()
            missing = [name for name in requires if not caps.has(name)]
            if missing:
                log.info(f"Rendering in-process: {', '.join(missing)} unavailable in the sandbox.")
                return False
        return True
    except Exception as e:
        log.warning(f"Sandbox availability check failed, treating as unavailable: {e}")
        return False


def render_in_sandbox(
    script: str,
    produced_filename: str,
    final_path: Path,
    session_id: str = "",
) -> tuple[bool, Optional[str]]:
    """Runs `script` (which must write `produced_filename` into its own
    working directory) as the sandbox account, then moves the artifact to
    `final_path` in the user-visible Sandbox folder.

    Returns (success, error). A False result is always safe for the caller
    to treat as "fall back to in-process" — nothing has been written to
    final_path in that case.
    """
    import code_exec

    result = code_exec.run_python(script, session_id=session_id)

    if result.get("error"):
        return False, result["error"]
    if not result.get("success"):
        detail = (result.get("stderr") or "").strip() or f"exit code {result.get('return_code')}"
        return False, f"sandboxed render failed: {detail}"

    produced = _locate_artifact(result, produced_filename)
    if produced is None or not produced.exists() or produced.stat().st_size == 0:
        # python-pptx/reportlab don't raise for an empty document, so an
        # existing-but-zero-byte file is still a failure, not a success.
        return False, "sandboxed render produced no output file"

    final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(produced), str(final_path))
    return True, None


def _locate_artifact(result: dict, produced_filename: str) -> Optional[Path]:
    """code_exec returns files_created as paths relative to the per-run
    session directory, so rebuild the absolute path from the sandbox_id it
    reports rather than guessing at the directory layout here."""
    from sandbox_manager import code_exec_dir

    sandbox_id = result.get("sandbox_id")
    if not sandbox_id:
        return None
    candidate = code_exec_dir() / sandbox_id / produced_filename
    return candidate if candidate.exists() else None


def render_document(
    script: str,
    produced_filename: str,
    final_path: Path,
    in_process_fallback: Callable[[], tuple[bool, Optional[str]]],
    session_id: str = "",
    requires: tuple[str, ...] = (),
) -> tuple[bool, Optional[str], bool]:
    """Preferred entry point: sandboxed render when possible, in-process
    otherwise. Returns (success, error, used_sandbox).

    Falls back on sandbox *failure* as well as unavailability, because the
    failures seen in practice are environmental rather than content-related
    — Pillow's native _imaging extension cannot initialize under the
    batch-logon sandbox account ("DLL initialization routine failed"), which
    takes reportlab and python-pptx down with it, while numpy/lxml/sqlite3
    load fine. Refusing to fall back would turn a working PDF feature into a
    broken one on every machine with that limitation. The fallback is logged
    at warning level so a silently-never-sandboxed setup is still visible.
    """
    if not sandbox_available(requires=requires):
        ok, err = in_process_fallback()
        return ok, err, False

    ok, err = render_in_sandbox(script, produced_filename, final_path, session_id=session_id)
    if ok:
        return True, None, True

    log.warning(f"Sandboxed render failed, falling back to in-process: {err}")
    ok, fallback_err = in_process_fallback()
    return ok, fallback_err, False
