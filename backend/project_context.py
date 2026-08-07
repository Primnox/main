# backend/project_context.py
"""
Project Context — cheap, local, zero-token awareness of the codebase the user
is actively working in.

Primnox's error detection used to know nothing about the project on screen:
no file path, no git repo, no branch, no idea whether "failed" in a UI label
was a real build error or a Slack notification. This module answers "what
project, what file, what branch, what's dirty" from local disk/subprocess
calls only — no LLM, no network — so the (comparatively expensive) triage
model gets real signal instead of a bare window title.

Entry point: get_project_context(title, process, pid). Everything else is
cached and safe to call every feed tick; it never raises — every public
function degrades to {} / None on failure so a project-context hiccup can
never break the feed loop.
"""

from __future__ import annotations

import json
import os as _os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import psutil

from logger import get_logger
from settings_manager import get_appdata_dir

log = get_logger("project_context")

PLATFORM = sys.platform

# Editors whose window title reliably ends with their own display name.
# Returning None for anything else is deliberate: it doubles as the "is this
# even an IDE" check that replaces the old, over-broad
# `process.lower() in ["code.exe", "code", "electron"]` match, which also
# matched Slack/Discord/Postman (all Electron apps).
_HYPHEN_EDITORS = {
    "Visual Studio Code": "vscode",
    "Cursor": "cursor",
    "Windsurf": "windsurf",
    "Sublime Text": "sublime",
}
# JetBrains IDEs separate segments with an en dash ("file – Project – PyCharm"),
# not a hyphen, and put the project before the editor name like VS Code does.
_ENDASH_EDITORS = {
    "PyCharm": "pycharm",
    "IntelliJ IDEA": "intellij",
    "WebStorm": "webstorm",
    "CLion": "clion",
    "Rider": "rider",
    "GoLand": "goland",
}

_SKIP_DIR_NAMES = {
    "node_modules", ".git", "venv", ".venv", "__pycache__", "dist", "build",
    "target", ".next", ".cache", "site-packages", ".idea", ".vs",
}

_HOME = Path.home()
_SEARCH_ROOTS = [
    _HOME, _HOME / "Projects", _HOME / "projects", _HOME / "source" / "repos",
    _HOME / "dev", _HOME / "Documents", _HOME / "code", _HOME / "src",
]

_LANG_BY_EXT = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".jsx": "javascript", ".rs": "rust", ".go": "go", ".java": "java", ".kt": "kotlin",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp", ".rb": "ruby",
    ".php": "php", ".swift": "swift", ".m": "objc",
}

_STACK_FILES = (
    "package.json", "requirements.txt", "pyproject.toml", "Cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "Gemfile", "composer.json",
)

_POPEN_KWARGS = {}
if PLATFORM == "win32":
    _POPEN_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW  # no console flash


# ── Title parsing ────────────────────────────────────────────────────────────

def parse_editor_title(title: str, process: str) -> Optional[dict]:
    """Return {"file_name","project_name","dirty","editor"} for a recognised
    IDE window title, or None if this isn't an IDE we know how to parse."""
    if not title:
        return None
    raw = title.strip()

    for sep, table, file_idx, proj_idx in ((" - ", _HYPHEN_EDITORS, 0, -2),
                                            (" – ", _ENDASH_EDITORS, 0, -2)):
        if sep not in raw:
            continue
        parts = [p.strip() for p in raw.split(sep)]
        editor_name = parts[-1]
        if editor_name not in table:
            continue
        if len(parts) < 2:
            return None
        file_part = parts[file_idx]
        dirty = file_part.startswith(("●", "•", "*"))
        file_name = file_part.lstrip("●•* ").strip()
        project_name = parts[proj_idx] if len(parts) > 2 else ""
        # Strip JetBrains' trailing " (Workspace)"/"[project]" decoration.
        project_name = re.sub(r"\s*[\[(].*?[\])]\s*$", "", project_name).strip()
        if not file_name or file_name == editor_name:
            return None  # IDE with no file open — nothing to resolve
        return {
            "file_name": file_name,
            "project_name": project_name,
            "dirty": dirty,
            "editor": table[editor_name],
        }
    return None


# ── Project root resolution ──────────────────────────────────────────────────

def _cwd_candidates(pid: Optional[int]) -> list[Path]:
    if not pid:
        return []
    try:
        proc = psutil.Process(pid)
        cwd = Path(proc.cwd())
    except Exception:
        return []
    candidates = [cwd]
    candidates.extend(cwd.parents)
    return candidates[:8]


def _find_file_under(root: Path, file_name: str, max_visited: int = 3000) -> bool:
    """Bounded existence check — root.rglob(file_name) was capped on MATCHES
    found, not entries VISITED, so a wrong candidate directory with zero
    matches (the common case: most candidates tried are wrong) walked its
    entire subtree unbounded. Root resolution tries several candidates per
    call, on a background thread, every ~10s — an unbounded miss against a
    large, wrong directory (e.g. an editor's own install dir) stalled the
    whole feed loop for the scan interval. os.walk lets us count every
    directory/file visited and bail deterministically regardless of whether
    anything matches."""
    visited = 0
    try:
        for dirpath, dirnames, filenames in _os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")]
            visited += len(dirnames) + len(filenames)
            if file_name in filenames:
                return True
            if visited >= max_visited:
                break
    except Exception:
        pass
    return False


def resolve_project(file_name: str, project_name: str, pid: Optional[int]) -> Optional[Path]:
    """Best-effort local resolution of the project root — no LLM, pure I/O."""
    candidates: list[Path] = []

    for c in _cwd_candidates(pid):
        if project_name and c.name == project_name:
            candidates.append(c)
    candidates.extend(_cwd_candidates(pid))  # fall back to cwd itself even if name mismatches

    if project_name:
        for search_root in _SEARCH_ROOTS:
            try:
                if not search_root.is_dir():
                    continue
                hit = search_root / project_name
                if hit.is_dir():
                    candidates.append(hit)
            except Exception:
                continue

    seen: set[str] = set()
    for c in candidates:
        key = str(c)
        if key in seen:
            continue
        seen.add(key)
        try:
            if not c.is_dir():
                continue
            if _find_file_under(c, file_name):
                return c
        except Exception:
            continue

    # Nothing confirmed the file under any candidate — admit it rather than
    # guess. This used to fall back to "the first candidate that's a real
    # directory", which for an editor opened on a single file with no
    # workspace folder (title has no project-name segment, so nothing here
    # is name-matched) meant returning psutil's reported cwd for the editor
    # process — for VS Code/Electron that's the app's own install directory,
    # not the user's project. Feeding the triage LLM "your project is
    # C:\...\Microsoft VS Code" is worse than feeding it nothing.
    return None


# ── Git (subprocess, no GitPython dependency) ────────────────────────────────

def _git(root: Path, *args: str, timeout: float = 2.0) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=timeout, **_POPEN_KWARGS,
        )
        if result.returncode != 0:
            return None
        # rstrip only — `status --porcelain` is fixed-width (2 status chars +
        # space) per line, and its first line often starts with a literal
        # leading space. A full .strip() ate that space off the whole blob,
        # shifting every downstream `line[3:]` slice by one character for
        # just the first entry (silently truncating one filename per scan).
        return result.stdout.rstrip()
    except Exception:
        return None


def _git_info(root: Path) -> dict:
    toplevel = _git(root, "rev-parse", "--show-toplevel")
    if not toplevel:
        return {"is_repo": False, "branch": None, "dirty_files": [], "last_commit": None}
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or None
    status = _git(root, "status", "--porcelain") or ""
    dirty_files = [line[3:].strip() for line in status.splitlines()[:15] if line.strip()]
    last_commit = _git(root, "log", "-1", "--format=%s") or None
    return {"is_repo": True, "branch": branch, "dirty_files": dirty_files, "last_commit": last_commit}


# ── Project tree scan (expensive — cached separately from git/active file) ──

def _scan_tree(root: Path) -> dict:
    languages: dict[str, int] = {}
    key_files: list[str] = []
    stack: list[str] = []
    recent: list[tuple[float, str]] = []

    # Root-level plus one directory deep — a plain root scan misses monorepo
    # layouts like this one (backend/requirements.txt, frontend/package.json,
    # nothing stack-identifying at the actual root).
    try:
        for entry in root.iterdir():
            if entry.name in _STACK_FILES:
                stack.append(entry.name)
            elif entry.is_dir() and entry.name not in _SKIP_DIR_NAMES and not entry.name.startswith("."):
                try:
                    for sub in entry.iterdir():
                        if sub.name in _STACK_FILES:
                            stack.append(f"{entry.name}/{sub.name}")
                except Exception:
                    continue
    except Exception:
        pass

    scanned = 0
    try:
        for p in root.rglob("*"):
            if any(part in _SKIP_DIR_NAMES for part in p.parts):
                continue
            scanned += 1
            if scanned > 5000:
                break
            if p.is_dir():
                continue
            ext = p.suffix.lower()
            if ext in _LANG_BY_EXT:
                languages[ext] = languages.get(ext, 0) + 1
            rel = str(p.relative_to(root))
            if len(rel.split("\\" if PLATFORM == "win32" else "/")) <= 2 and len(key_files) < 40:
                key_files.append(rel)
            try:
                recent.append((p.stat().st_mtime, rel))
            except Exception:
                pass
    except Exception:
        pass

    recent.sort(key=lambda t: t[0], reverse=True)
    recent_files = [r for _, r in recent[:10]]

    return {
        "stack": stack,
        "languages": languages,
        "key_files": key_files,
        "recent_files": recent_files,
    }


# ── Caching ───────────────────────────────────────────────────────────────────

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, dict] = {}          # root -> full context
_CHEAP_TTL = 30            # active file / branch / dirty — refresh often, it's cheap
_TREE_TTL = 30 * 60        # file tree / languages / stack — expensive, refresh rarely
_DISK_CACHE_PATH = get_appdata_dir() / "project_cache.json"
_DISK_CACHE_MAX_ENTRIES = 20
_SCHEMA = 1


def _load_disk_cache() -> dict:
    try:
        if _DISK_CACHE_PATH.exists():
            data = json.loads(_DISK_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if isinstance(v, dict) and v.get("schema") == _SCHEMA}
    except Exception as e:
        log.debug(f"project cache load failed: {e}")
    return {}


def _save_disk_cache() -> None:
    try:
        trimmed = dict(list(_CACHE.items())[-_DISK_CACHE_MAX_ENTRIES:])
        _DISK_CACHE_PATH.write_text(json.dumps(trimmed), encoding="utf-8")
    except Exception as e:
        log.debug(f"project cache save failed: {e}")


with _CACHE_LOCK:
    _CACHE.update(_load_disk_cache())


def invalidate() -> None:
    """Test hook — clears the in-memory cache (does not touch disk)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def get_project_context(title: str, process: str, pid: Optional[int] = None) -> dict:
    """The one entry point the feed loop should call. Never raises."""
    try:
        parsed = parse_editor_title(title, process)
        if not parsed:
            return {}

        root = resolve_project(parsed["file_name"], parsed["project_name"], pid)
        if not root:
            return {}
        root_key = str(root)
        now = time.time()

        with _CACHE_LOCK:
            cached = _CACHE.get(root_key)

        need_tree = not cached or (now - cached.get("scanned_at", 0)) > _TREE_TTL
        need_cheap = not cached or (now - cached.get("cheap_scanned_at", 0)) > _CHEAP_TTL

        if not need_tree and not need_cheap:
            ctx = dict(cached)
        else:
            tree = _scan_tree(root) if need_tree else {
                "stack": cached.get("stack", []),
                "languages": cached.get("languages", {}),
                "key_files": cached.get("key_files", []),
                "recent_files": cached.get("recent_files", []),
            }
            git = _git_info(root)
            ctx = {
                "schema": _SCHEMA,
                "project_name": parsed["project_name"] or root.name,
                "root": root_key,
                "language": _LANG_BY_EXT.get(Path(parsed["file_name"]).suffix.lower()),
                **tree,
                "git": git,
                "scanned_at": now if need_tree else cached.get("scanned_at", now),
                "cheap_scanned_at": now,
            }
            with _CACHE_LOCK:
                _CACHE[root_key] = ctx
            if need_tree:
                _save_disk_cache()

        ctx = dict(ctx)
        ctx["active_file"] = parsed["file_name"]
        try:
            ctx["active_file_rel"] = str((root / parsed["file_name"]).relative_to(root))
        except Exception:
            ctx["active_file_rel"] = parsed["file_name"]
        ctx["editor"] = parsed["editor"]
        ctx["dirty_active_file"] = parsed["dirty"]
        return ctx
    except Exception as e:
        log.debug(f"project context resolution failed: {e}")
        return {}


if __name__ == "__main__":
    # Manual check: prints context for whatever IDE window is currently
    # foreground. `python project_context.py "<window title>" <process> [pid]`
    # for a quick offline check, or with no args on Windows it reads the
    # live foreground window.
    import sys as _sys

    if len(_sys.argv) >= 3:
        _title, _process = _sys.argv[1], _sys.argv[2]
        _pid = int(_sys.argv[3]) if len(_sys.argv) > 3 else None
    else:
        import win32gui, win32process
        _hwnd = win32gui.GetForegroundWindow()
        _title = win32gui.GetWindowText(_hwnd)
        _, _pid = win32process.GetWindowThreadProcessId(_hwnd)
        _process = psutil.Process(_pid).name()

    print(f"title={_title!r} process={_process!r} pid={_pid}")
    print(json.dumps(get_project_context(_title, _process, _pid), indent=2))
