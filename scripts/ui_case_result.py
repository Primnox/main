"""Wait for the newest conversation's turn to settle, then say what it produced.

Companion to driving the real UI by hand: the browser tool caps a script at 30
seconds, which is shorter than a turn, so the sending happens in the page and
the waiting happens here. Reads the same two tables the app writes — a
workspace is a Canvas, an asset is a file — because "did it work" spans both
and scoring only one is what produced a wrong answer earlier.

Usage:  python scripts/ui_case_result.py [timeout_s]
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

TERMINAL = ("completed", "failed", "cancelled", "awaiting_input")


def main() -> int:
    timeout = float(sys.argv[1]) if len(sys.argv) > 1 else 240.0
    from primnox2 import paths
    from primnox2.storage import db
    home = pathlib.Path(os.getenv("PRIMNOX2_HOME",
                                  pathlib.Path.home() / "Documents" / "Primnox2"))
    paths.configure(home)
    db.configure(home / "primnox.db")
    con = db.connect()

    row = con.execute(
        "SELECT id, title FROM conversations ORDER BY created_at DESC LIMIT 1").fetchone()
    if row is None:
        print("no conversation")
        return 1

    deadline = time.time() + timeout
    status = "?"
    while time.time() < deadline:
        turn = con.execute(
            "SELECT id, status FROM turns WHERE conversation_id=?"
            " ORDER BY created_at DESC LIMIT 1", (row["id"],)).fetchone()
        if turn is not None:
            status = turn["status"]
            if status in TERMINAL:
                break
        time.sleep(2)

    workspaces = [w["title"] for w in con.execute(
        "SELECT w.title FROM workspaces w JOIN turns t ON t.id=w.origin_turn_id"
        " WHERE t.conversation_id=?", (row["id"],))]
    assets = con.execute(
        "SELECT COUNT(*) n FROM assets a JOIN turn_assets ta ON ta.asset_id=a.id"
        " JOIN turns t ON t.id=ta.turn_id WHERE t.conversation_id=?",
        (row["id"],)).fetchone()["n"]

    delivered = "CANVAS" if workspaces else ("FILE" if assets else "NOTHING")
    print("%-9s %-15s canvas=%d file=%d  %s"
          % (delivered, status, len(workspaces), assets, str(row["title"])[:44]))
    if workspaces:
        print("    workspace: %s" % workspaces[0][:60])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
