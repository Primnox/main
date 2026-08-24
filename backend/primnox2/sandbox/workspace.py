"""Ephemeral execution directories.

Every execution gets its own directory, and the container is granted access
to THAT DIRECTORY ONLY — see `_grant()` below and `appcontainer.provision()`.
The isolation is an ACL the OS enforces, not a naming convention:

    sandbox/exec_<id>/
        main.py | main.js | main.cmd
        output/
        temp/
        logs/

Two lifetimes, from the architecture spec:

    ephemeral  one execution, destroyed or snapshotted afterwards
    project    reusable, so a later conversation continues in the same tree
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .. import paths

SCRIPT_NAMES = {"python": "main.py", "node": "main.js", "shell": "main.cmd"}

# Subdirectories every execution gets, so generated code has somewhere
# conventional to put things and the snapshot diff stays readable.
_SUBDIRS = ("output", "temp", "logs")


def sandbox_root() -> Path:
    root = paths.root() / "sandbox"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _grant(d: Path) -> Path:
    """Give the container access to this directory alone.

    The shared roots carry traverse-only, non-inheritable ACEs, so a new
    directory under them starts with NO access for the container and has to
    be granted explicitly. That is what keeps one execution out of another's
    directory even though both run under the same AppContainer SID: a
    sibling simply has no ACE for it.

    Import is local because `appcontainer` imports `paths` and is
    Windows-specific; keeping it out of module scope leaves this module
    importable (and testable) anywhere.
    """
    try:
        from . import appcontainer
        appcontainer.grant_session_dir(d)
    except Exception:
        # A failed grant surfaces as the execution being unable to write its
        # own workspace, which supervisor reports honestly. It must never
        # take down directory creation itself.
        pass
    return d


def ephemeral(execution_id: str) -> Path:
    """A fresh directory for one execution."""
    d = sandbox_root() / execution_id
    for sub in _SUBDIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
    return _grant(d)


def project(workspace_id: str) -> Path:
    """A persistent directory that survives across executions and chats."""
    d = paths.workspaces_dir() / workspace_id
    for sub in _SUBDIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
    return _grant(d)


def resolve(execution_id: str, workspace_id: str | None) -> tuple[Path, bool]:
    """Return (directory, ephemeral?) for this execution."""
    if workspace_id:
        return project(workspace_id), False
    return ephemeral(execution_id), True


# Copied into every Python execution so generated code can import it with no
# install and no network. Named for what it is to the code that imports it,
# not for the file it comes from.
HELPER_NAME = "primnox_docs.py"
_HELPER_SOURCE = Path(__file__).with_name("doc_themes.py")


def install_helpers(directory: Path, runtime: str) -> None:
    """Put the themed document builders where generated code can reach them.

    The sandbox has no network, so a helper has to arrive as a file. The
    working directory is on `sys.path`, which makes `import primnox_docs` work
    without touching site-packages — and keeps the helper as ephemeral as the
    execution that used it.
    """
    if runtime != "python":
        return
    try:
        shutil.copyfile(_HELPER_SOURCE, directory / HELPER_NAME)
    except OSError:
        # A missing helper costs styling, never the execution.
        pass


def write_script(directory: Path, runtime: str, code: str) -> Path:
    name = SCRIPT_NAMES.get(runtime)
    if name is None:
        raise ValueError(f"no script name for runtime {runtime!r}")
    path = directory / name
    # newline="" keeps Python source byte-exact; letting the platform rewrite
    # line endings inside a string literal would change the program.
    path.write_text(code, encoding="utf-8", newline="")
    return path


def destroy(directory: Path) -> bool:
    """Remove an ephemeral directory. Never raises — cleanup failing must not
    fail the execution that already produced a result."""
    try:
        shutil.rmtree(directory, ignore_errors=True)
        return not directory.exists()
    except OSError:
        return False


def disk_usage_bytes(directory: Path) -> int:
    total = 0
    for p in directory.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total
