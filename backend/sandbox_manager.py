"""Bounded scratch space for AI-generated files (PDFs, PPTs, screenshots).

Skills that produce output files (screenshot_skill.py, and the pdf/pptx/
docx/xlsx Claude Skills) previously wrote directly and indefinitely into the
user's real Documents folder — disk usage grew forever with zero
size-based ceiling (cleanup_manager.py only handles time-based retention
for meetings/memories, nothing size-based for generated files). This gives
every generating skill one shared, quota-enforced directory instead: write
the file, then call enforce_quota() — oldest files (by mtime) get deleted
first until total usage is back under the quota.

Not a true execution sandbox (no process/filesystem isolation) — Primnox
has no arbitrary-code-execution tool today, so there's nothing to actually
isolate yet. This solves the concrete problem that exists right now:
unbounded disk growth from repeated file generation.
"""
from __future__ import annotations

import threading
from pathlib import Path

from logger import get_logger

log = get_logger("sandbox")

DEFAULT_QUOTA_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB

_lock = threading.Lock()


def sandbox_dir() -> Path:
    d = Path.home() / "Documents" / "Primnox" / "Sandbox"
    d.mkdir(parents=True, exist_ok=True)
    return d


def code_exec_dir() -> Path:
    """Separate top-level directory from sandbox_dir() (generated PDFs/PPTs/
    screenshots) — a user browsing their generated documents shouldn't
    stumble into arbitrary executed scripts, and vice versa. Quota-managed
    independently via enforce_quota(base=code_exec_dir(), ...)."""
    d = Path.home() / "Documents" / "Primnox" / "CodeExecution"
    d.mkdir(parents=True, exist_ok=True)
    return d


def runtime_dir() -> Path:
    """Shared, long-lived dependencies for SKILL.md-backed skills — chiefly
    the node_modules holding pptxgenjs and docx-js, which the official pptx
    and docx skills build their output with.

    Lives under code_exec_dir() so it inherits the ACL already granted to
    the sandbox account (it can't read this user's global npm root, which
    is under AppData by design). It is deliberately exempt from quota
    eviction — see enforce_quota's `protect`.
    """
    d = code_exec_dir() / "_runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


def runtime_node_modules() -> Path:
    return runtime_dir() / "node_modules"


def prune_stale_workspaces(max_age_hours: float = 24.0) -> int:
    """Deletes named workspaces (ws_*) untouched for `max_age_hours`.

    Workspaces persist across executions on purpose, so they can't be
    reclaimed by the size-based sweeper the way throwaway session dirs are:
    a workspace in the middle of a multi-step skill is full of files older
    than everything around it, and oldest-first eviction would delete a
    half-finished document between two steps. Age since last write is the
    safe signal instead. Returns the number of workspaces removed.
    """
    import shutil
    import time

    base = code_exec_dir()
    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    for d in base.glob("ws_*"):
        if not d.is_dir():
            continue
        try:
            newest = max((f.stat().st_mtime for f in d.rglob("*") if f.is_file()), default=d.stat().st_mtime)
            if newest >= cutoff:
                continue
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
            log.info(f"Pruned stale skill workspace: {d.name}")
        except OSError as e:
            log.warning(f"Could not prune workspace {d}: {e}")
    return removed


def get_usage_bytes(base: Path | None = None) -> int:
    base = base or sandbox_dir()
    total = 0
    for f in base.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def _is_protected(f: Path, protect: tuple[Path, ...]) -> bool:
    for root in protect:
        try:
            f.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def enforce_quota(
    quota_bytes: int = DEFAULT_QUOTA_BYTES,
    base: Path | None = None,
    protect: tuple[Path, ...] = (),
) -> int:
    """Deletes the oldest files (by mtime) under `base` (default sandbox_dir())
    until total usage is at or under `quota_bytes`. Call this after writing a
    new file. Returns the number of files evicted.

    Anything under a `protect` root is never evicted. Without that, the
    installed node_modules under runtime_dir() would be prime eviction
    targets — thousands of files, all with install-time mtimes older than
    any real output — and the pptx/docx skills would break with a
    module-not-found error long after the install appeared to succeed.
    """
    base = base or sandbox_dir()
    with _lock:
        usage = get_usage_bytes(base)
        if usage <= quota_bytes:
            return 0

        files = sorted(
            (f for f in base.rglob("*") if f.is_file() and not _is_protected(f, protect)),
            key=lambda f: f.stat().st_mtime,
        )
        evicted = 0
        for f in files:
            if usage <= quota_bytes:
                break
            try:
                size = f.stat().st_size
                f.unlink()
                usage -= size
                evicted += 1
                log.info(f"Sandbox quota eviction: deleted {f.name} ({size} bytes)")
            except OSError as e:
                log.warning(f"Could not evict {f}: {e}")
        return evicted
