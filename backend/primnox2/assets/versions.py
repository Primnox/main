"""Asset lineage — version history and revert for generated files.

A workspace has had both since it shipped: `workspaces.update()` writes a new
immutable version and `revert()` restores an old one by appending, never by
deleting. An asset had neither, so "regenerate that deck" replaced the old one
with nothing pointing back at it. That asymmetry was the real gap behind the
Canvas-versus-AssetViewer split, and it is what this closes.

Nothing here stores bytes. Assets are content-addressed and deduplicated on
sha256, so a regenerated deck is already its own row at its own path — the old
file did not go anywhere, it just stopped being referenced. Recording lineage
is therefore bookkeeping over rows that already exist, which is why this is a
table of ordering rather than a second copy of every artifact.

Retention is the user's call, not this module's. See `retention()`.
"""
from __future__ import annotations

from ..ids import new_id
from ..storage import db
from ..settings import service as settings_service


def _now() -> int:
    import time
    return int(time.time() * 1000)


def retention() -> str:
    """"keep" or "history".

    Defaults to "keep", so a user who has never opened Settings can still undo
    a regeneration. The alternative loses data on a silent default, and the
    asymmetry this module exists to fix was itself a silent data loss.
    """
    value = settings_service.get("assets.version_retention", "keep")
    return value if value in {"keep", "history"} else "keep"


def lineage_of(asset_id: str, conn=None) -> str | None:
    """The lineage this asset belongs to, or None if it has never been versioned.

    An unversioned asset is the common case — most files are uploaded once and
    never regenerated — and it is not an error. Callers treat None as "one
    version, this one".
    """
    c = conn if conn is not None else db.connect()
    row = c.execute(
        "SELECT lineage_id FROM asset_versions WHERE asset_id=?"
        " ORDER BY version DESC LIMIT 1", (asset_id,),
    ).fetchone()
    return row["lineage_id"] if row else None


def supersede(previous_asset_id: str, new_asset_id: str, *,
              summary: str | None = None, turn_id: str | None = None) -> dict:
    """Record that `new_asset_id` replaces `previous_asset_id`.

    Starts a lineage if the previous asset was not in one, which is what makes
    this callable at the moment of regeneration without anyone having declared
    a lineage up front.
    """
    if previous_asset_id == new_asset_id:
        # Regenerating to byte-identical output deduplicates to the same asset.
        # Appending a version here would claim a change that did not happen.
        return {"lineage_id": lineage_of(previous_asset_id) or "",
                "version": version_of(previous_asset_id) or 1, "unchanged": True}

    ts = _now()
    with db.tx() as c:
        for aid in (previous_asset_id, new_asset_id):
            if c.execute("SELECT 1 FROM assets WHERE id=?", (aid,)).fetchone() is None:
                raise KeyError(f"unknown asset {aid}")

        lineage = lineage_of(previous_asset_id, c)
        if lineage is None:
            lineage = new_id("lineage")
            c.execute(
                "INSERT INTO asset_versions"
                " (lineage_id,version,asset_id,summary,created_by_turn_id,created_at)"
                " VALUES (?,1,?,?,?,?)",
                (lineage, previous_asset_id, "created", None, ts),
            )
            nxt = 2
        else:
            row = c.execute(
                "SELECT MAX(version) AS v FROM asset_versions WHERE lineage_id=?",
                (lineage,),
            ).fetchone()
            nxt = int(row["v"]) + 1

        c.execute(
            "INSERT INTO asset_versions"
            " (lineage_id,version,asset_id,summary,created_by_turn_id,created_at)"
            " VALUES (?,?,?,?,?,?)",
            (lineage, nxt, new_asset_id, summary or "regenerated", turn_id, ts),
        )

    return {"lineage_id": lineage, "version": nxt, "unchanged": False}


def version_of(asset_id: str) -> int | None:
    row = db.connect().execute(
        "SELECT version FROM asset_versions WHERE asset_id=?"
        " ORDER BY version DESC LIMIT 1", (asset_id,),
    ).fetchone()
    return int(row["version"]) if row else None


def versions(asset_id: str) -> list[dict]:
    """Every version in this asset's lineage, oldest first.

    An asset that has never been superseded returns [] rather than a synthetic
    single entry: the UI decides whether "one version" is worth drawing, and
    inventing a history here would make every uploaded file look versioned.
    """
    lineage = lineage_of(asset_id)
    if lineage is None:
        return []
    rows = db.connect().execute(
        "SELECT v.version, v.asset_id, v.summary, v.created_by_turn_id, v.created_at,"
        "       a.original_name, a.bytes, a.sha256, a.status"
        "  FROM asset_versions v JOIN assets a ON a.id = v.asset_id"
        " WHERE v.lineage_id=? ORDER BY v.version ASC", (lineage,),
    ).fetchall()
    return [dict(r) for r in rows]


def head(asset_id: str) -> str:
    """The current asset in this lineage — the newest version.

    Returns the input unchanged when there is no lineage, so callers can use
    this without first asking whether the asset was ever versioned.
    """
    lineage = lineage_of(asset_id)
    if lineage is None:
        return asset_id
    row = db.connect().execute(
        "SELECT asset_id FROM asset_versions WHERE lineage_id=?"
        " ORDER BY version DESC LIMIT 1", (lineage,),
    ).fetchone()
    return row["asset_id"] if row else asset_id


def revert(asset_id: str, to_version: int, *, turn_id: str | None = None) -> dict:
    """Restore an earlier version by appending it as a new one.

    The same rule workspaces.revert() follows: reverting does not delete the
    versions after the one being restored, so undoing an undo is just another
    revert. Deleting them would destroy the record of what was reverted away
    from, which is the evidence the user is acting on.
    """
    lineage = lineage_of(asset_id)
    if lineage is None:
        raise KeyError(f"asset {asset_id} has no version history")

    conn = db.connect()
    target = conn.execute(
        "SELECT asset_id FROM asset_versions WHERE lineage_id=? AND version=?",
        (lineage, to_version),
    ).fetchone()
    if target is None:
        raise KeyError(f"lineage {lineage} has no version {to_version}")

    restored = target["asset_id"]
    status = conn.execute(
        "SELECT status FROM assets WHERE id=?", (restored,)
    ).fetchone()
    if status is None:
        # ON DELETE CASCADE should make this unreachable, but a pruned file
        # under retention="history" is a real state and must not 500.
        raise KeyError(f"version {to_version} is no longer available")

    ts = _now()
    with db.tx() as c:
        row = c.execute(
            "SELECT MAX(version) AS v FROM asset_versions WHERE lineage_id=?",
            (lineage,),
        ).fetchone()
        nxt = int(row["v"]) + 1
        c.execute(
            "INSERT INTO asset_versions"
            " (lineage_id,version,asset_id,summary,created_by_turn_id,created_at)"
            " VALUES (?,?,?,?,?,?)",
            (lineage, nxt, restored, f"reverted to v{to_version}", turn_id, ts),
        )

    return {"lineage_id": lineage, "version": nxt, "asset_id": restored,
            "reverted_to": to_version}


def superseded_assets(lineage_id: str) -> list[str]:
    """Assets in a lineage that are no longer the head.

    This is what retention="history" would prune. It is reported rather than
    acted on: deleting the bytes is only safe once nothing else references that
    sha256, and dedup means another asset row legitimately can. The pruning
    itself is left unbuilt rather than built wrong.
    """
    rows = db.connect().execute(
        "SELECT DISTINCT asset_id FROM asset_versions WHERE lineage_id=?", (lineage_id,),
    ).fetchall()
    current = db.connect().execute(
        "SELECT asset_id FROM asset_versions WHERE lineage_id=?"
        " ORDER BY version DESC LIMIT 1", (lineage_id,),
    ).fetchone()
    head_id = current["asset_id"] if current else None
    return [r["asset_id"] for r in rows if r["asset_id"] != head_id]
