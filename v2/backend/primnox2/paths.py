"""Filesystem layout.

One configured root, resolved once at startup. Content-addressed asset storage
and workspace checkouts hang off it.

Everything here returns a path that exists — callers should never have to
mkdir defensively, because a half-created tree is how ingestion ends up
reporting success for a file it never actually wrote.
"""
from __future__ import annotations

from pathlib import Path

_root: Path | None = None


def configure(root: str | Path) -> None:
    global _root
    _root = Path(root)
    _root.mkdir(parents=True, exist_ok=True)


def root() -> Path:
    if _root is None:
        raise RuntimeError("paths.configure() must be called before use")
    return _root


def _sub(name: str) -> Path:
    p = root() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def assets_dir() -> Path:
    return _sub("assets")


def workspaces_dir() -> Path:
    return _sub("workspaces")


def traces_dir() -> Path:
    return _sub("traces")


def asset_path(sha256: str) -> Path:
    """Content-addressed: assets/<first two hex chars>/<full digest>.

    The two-character fan-out keeps any single directory from collecting every
    asset on the machine, which is what makes directory listing degrade on
    NTFS once a tree gets large.
    """
    shard = assets_dir() / sha256[:2]
    shard.mkdir(parents=True, exist_ok=True)
    return shard / sha256
