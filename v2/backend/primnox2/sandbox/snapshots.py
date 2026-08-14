"""Before/after snapshots — execution becomes reversible.

Take a snapshot before the process runs and after it exits, diff the two, and
the user gets a git-style view of what actually changed, with accept and revert
as real options.

Content hashing rather than mtime: a script that rewrites a file with identical
bytes has not changed anything the user cares about, and filesystem timestamp
granularity is coarse enough that a fast execution can modify a file without
its mtime moving at all.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# Files bigger than this are identified by (size, mtime) rather than content.
# Hashing a 500MB artifact on both sides of every execution would cost more
# than the execution itself.
_HASH_LIMIT_BYTES = 8 * 1024 * 1024

# Never diff the machinery. The script we wrote in is not a result, and the
# wrapper and capture files are plumbing the user never asked for.
from .appcontainer import PLUMBING as _AC_PLUMBING

# `primnox_docs.py` is copied in for the script to import. It is ours, not the
# user's — surfacing it as a produced file would attach a library to every
# document as though the model had written one.
_IGNORED = {"main.py", "main.js", "main.cmd", "primnox_docs.py"} | set(_AC_PLUMBING)


def _fingerprint(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return "unreadable"
    if stat.st_size > _HASH_LIMIT_BYTES:
        return f"big:{stat.st_size}:{int(stat.st_mtime)}"
    try:
        return "sha1:" + hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return "unreadable"


def snapshot(root: Path) -> dict[str, str]:
    """Map every file under `root` to a content fingerprint."""
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if not p.is_file() or p.name in _IGNORED:
            continue
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            continue
        out[rel] = _fingerprint(p)
    return out


def diff(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    """Git-style change summary between two snapshots."""
    b, a = set(before), set(after)
    return {
        "created": sorted(a - b),
        "modified": sorted(p for p in (a & b) if before[p] != after[p]),
        "deleted": sorted(b - a),
    }


def is_empty(d: dict[str, list[str]]) -> bool:
    return not (d["created"] or d["modified"] or d["deleted"])


def summarize(d: dict[str, list[str]]) -> str:
    if is_empty(d):
        return "no file changes"
    bits = []
    for label in ("created", "modified", "deleted"):
        if d[label]:
            bits.append(f"{len(d[label])} {label}")
    return ", ".join(bits)
