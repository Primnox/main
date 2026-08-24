"""Workspace Service — CRS §2.5.

A workspace is the editable object a conversation *references*. The chat
becomes history; the workspace stays live.

Two rules do the work:

  Every mutation creates a new immutable version. Nothing is edited in place,
  so "undo that" is a pointer move rather than a regeneration.

  Unchanged files carry forward. An edit sends only the files it touches,
  which is what makes "only modify line 742" cost one file instead of a whole
  re-emission of the project — the operation that breaks V1 today.

A workspace outlives its origin turn and its conversation (§2.5). Deleting the
chat you generated a document in must not delete the document.
"""
from __future__ import annotations

import time

from ..ids import WS, new_id
from ..kernel.events import bus
from ..storage import db

now_ms = lambda: int(time.time() * 1000)

KINDS = ("react", "python", "markdown", "html", "notebook", "doc", "shell")


def create(
    kind: str,
    title: str,
    files: dict[str, str],
    *,
    origin_turn_id: str | None = None,
    conversation_id: str | None = None,
    summary: str | None = None,
) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown workspace kind {kind!r} (expected one of {', '.join(KINDS)})")
    if not files:
        raise ValueError("a workspace needs at least one file")

    wid, ts = new_id(WS), now_ms()
    pending = []
    with db.tx() as c:
        c.execute(
            "INSERT INTO workspaces (id,kind,title,origin_turn_id,current_version,created_at,updated_at)"
            " VALUES (?,?,?,?,1,?,?)",
            (wid, kind, title, origin_turn_id, ts, ts),
        )
        c.execute(
            "INSERT INTO workspace_versions (workspace_id,version,created_by_turn_id,summary,created_at)"
            " VALUES (?,1,?,?,?)",
            (wid, origin_turn_id, summary or "created", ts),
        )
        for path, content in files.items():
            c.execute(
                "INSERT INTO workspace_files (workspace_id,version,path,content) VALUES (?,1,?,?)",
                (wid, path, content),
            )
        if origin_turn_id:
            c.execute("INSERT OR IGNORE INTO turn_workspaces (turn_id,workspace_id) VALUES (?,?)",
                      (origin_turn_id, wid))
        if conversation_id:
            pending.append(bus.emit(
                "workspace.created",
                {"workspace_id": wid, "kind": kind, "title": title,
                 "version": 1, "paths": sorted(files)},
                conversation_id=conversation_id, turn_id=origin_turn_id, conn=c,
            ))
    bus.deferred_fanout(pending)
    return {"workspace_id": wid, "kind": kind, "title": title, "version": 1,
            "paths": sorted(files)}


def update(
    workspace_id: str,
    files: dict[str, str],
    *,
    turn_id: str | None = None,
    conversation_id: str | None = None,
    summary: str | None = None,
    delete: tuple[str, ...] = (),
) -> dict:
    """Write a new version containing `files` merged over the current one."""
    pending = []
    with db.tx() as c:
        row = c.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown workspace {workspace_id}")

        current = row["current_version"]
        new_version = current + 1
        ts = now_ms()

        existing = {
            r["path"]: r["content"]
            for r in c.execute(
                "SELECT path, content FROM workspace_files WHERE workspace_id=? AND version=?",
                (workspace_id, current),
            )
        }
        merged = {p: v for p, v in existing.items() if p not in delete}
        changed = [p for p, v in files.items() if merged.get(p) != v]
        merged.update(files)

        if not changed and not delete:
            # Nothing actually differs. Creating a version anyway would make
            # the history lie about what happened.
            return {"workspace_id": workspace_id, "version": current,
                    "changed_paths": [], "unchanged": True}

        c.execute(
            "INSERT INTO workspace_versions (workspace_id,version,created_by_turn_id,summary,created_at)"
            " VALUES (?,?,?,?,?)",
            (workspace_id, new_version, turn_id, summary or "edited", ts),
        )
        for path, content in merged.items():
            c.execute(
                "INSERT INTO workspace_files (workspace_id,version,path,content) VALUES (?,?,?,?)",
                (workspace_id, new_version, path, content),
            )
        c.execute("UPDATE workspaces SET current_version=?, updated_at=? WHERE id=?",
                  (new_version, ts, workspace_id))
        if turn_id:
            c.execute("INSERT OR IGNORE INTO turn_workspaces (turn_id,workspace_id) VALUES (?,?)",
                      (turn_id, workspace_id))
        if conversation_id:
            pending.append(bus.emit(
                "workspace.updated",
                {"workspace_id": workspace_id, "version": new_version,
                 "changed_paths": sorted(set(changed) | set(delete))},
                conversation_id=conversation_id, turn_id=turn_id, conn=c,
            ))
    bus.deferred_fanout(pending)
    return {"workspace_id": workspace_id, "version": new_version,
            "changed_paths": sorted(set(changed) | set(delete)), "unchanged": False}


def revert(workspace_id: str, to_version: int, *, turn_id: str | None = None,
           conversation_id: str | None = None) -> dict:
    """Undo, as a forward move.

    Reverting writes the old content as a NEW version rather than deleting the
    versions after it. History is append-only, so "undo that" is itself
    undoable — and a revert can never destroy the work it reverted.
    """
    files = read_files(workspace_id, to_version)
    if not files:
        raise KeyError(f"workspace {workspace_id} has no version {to_version}")
    current = read_files(workspace_id)
    return update(
        workspace_id, files, turn_id=turn_id, conversation_id=conversation_id,
        summary=f"reverted to v{to_version}",
        delete=tuple(p for p in current if p not in files),
    )


# ── Reads ────────────────────────────────────────────────────────────────────
def read_files(workspace_id: str, version: int | None = None) -> dict[str, str]:
    conn = db.connect()
    if version is None:
        row = conn.execute("SELECT current_version FROM workspaces WHERE id=?",
                           (workspace_id,)).fetchone()
        if row is None:
            return {}
        version = row["current_version"]
    return {
        r["path"]: r["content"]
        for r in conn.execute(
            "SELECT path, content FROM workspace_files WHERE workspace_id=? AND version=?",
            (workspace_id, version),
        )
    }


def get(workspace_id: str, version: int | None = None) -> dict | None:
    row = db.connect().execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["files"] = read_files(workspace_id, version)
    d["version"] = version or d["current_version"]
    d["versions"] = versions(workspace_id)
    return d


def versions(workspace_id: str) -> list[dict]:
    rows = db.connect().execute(
        "SELECT version, created_by_turn_id, summary, created_at FROM workspace_versions"
        " WHERE workspace_id=? ORDER BY version",
        (workspace_id,),
    )
    return [dict(r) for r in rows]


def diff(workspace_id: str, a: int, b: int) -> dict[str, list[str]]:
    fa, fb = read_files(workspace_id, a), read_files(workspace_id, b)
    ka, kb = set(fa), set(fb)
    return {
        "created": sorted(kb - ka),
        "modified": sorted(p for p in (ka & kb) if fa[p] != fb[p]),
        "deleted": sorted(ka - kb),
    }


def list_workspaces(limit: int = 100) -> list[dict]:
    rows = db.connect().execute(
        "SELECT id,kind,title,current_version,created_at,updated_at FROM workspaces"
        " ORDER BY updated_at DESC LIMIT ?", (limit,),
    )
    return [dict(r) for r in rows]


def for_turn(turn_id: str) -> list[dict]:
    rows = db.connect().execute(
        "SELECT w.id,w.kind,w.title,w.current_version FROM workspaces w"
        "  JOIN turn_workspaces tw ON tw.workspace_id = w.id WHERE tw.turn_id=?",
        (turn_id,),
    )
    return [dict(r) for r in rows]
