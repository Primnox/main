"""Schema migrations (CRS §4.4).

These build databases at older shapes on disk and run the real `db.init()`
against them. They deliberately do not use the session runtime fixture: the
whole point is the transition, which a database already at the current version
cannot exercise.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from primnox2.storage import db

# A v6 database: knowledge tables at the pre-conversation-graph shape. The
# columns here are only those v6 actually had — adding one would make the test
# assert against a database that never existed.
V6 = """
CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL,
                                applied_at INTEGER NOT NULL);
CREATE TABLE knowledge_nodes (
    id TEXT PRIMARY KEY, label TEXT NOT NULL, key TEXT NOT NULL, type TEXT NOT NULL,
    scope TEXT NOT NULL, salience REAL NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
    CHECK (type IN ('file','module','section','class','function','rationale',
                    'entity','concept')),
    UNIQUE (scope, key));
CREATE TABLE knowledge_edges (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
    relation TEXT NOT NULL, context TEXT NOT NULL DEFAULT '',
    confidence TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1.0,
    created_at INTEGER NOT NULL);
INSERT INTO schema_migrations VALUES (6, 'current', 1);
INSERT INTO knowledge_nodes VALUES ('n1','stale()','stale','function','repo',0,1,1);
"""


@pytest.fixture
def at_version(tmp_path, monkeypatch):
    """Build a database at an older shape and point the module at it.

    The connection cache is thread-local and keyed to the configured path, so
    the previous path's connection is dropped explicitly — otherwise this test
    would read the session database and pass without touching the migration.
    """
    def _build(ddl: str | None) -> Path:
        path = tmp_path / "primnox.db"
        if ddl:
            conn = sqlite3.connect(path)
            conn.executescript(ddl)
            conn.commit()
            conn.close()
        db.configure(path)
        return path

    original = getattr(db, "_db_path", None)
    yield _build
    if original is not None:
        db.configure(original)


def test_a_fresh_database_lands_on_the_current_version(at_version):
    at_version(None)
    db.init()
    row = db.connect().execute("SELECT MAX(version) v FROM schema_migrations").fetchone()
    assert row["v"] == db.SCHEMA_VERSION


def test_init_is_idempotent(at_version):
    at_version(None)
    db.init()
    db.init()   # must not raise
    row = db.connect().execute("SELECT MAX(version) v FROM schema_migrations").fetchone()
    assert row["v"] == db.SCHEMA_VERSION


def test_v6_upgrades_without_raising_on_a_new_column(at_version):
    """Regression: schema.sql used to run BEFORE migrations.

    `CREATE INDEX … ON knowledge_nodes(conversation_id)` then executed against a
    v6 table that had no such column, so init() raised "no such column" on
    exactly the databases the migration existed to repair. Fresh databases were
    fine, which is what made it invisible until an upgrade was tried.
    """
    at_version(V6)
    db.init()   # the bug was an exception here

    ddl = db.connect().execute(
        "SELECT sql FROM sqlite_master WHERE name='knowledge_nodes'").fetchone()["sql"]
    assert "conversation_id" in ddl
    assert "'decision'" in ddl, "the widened type CHECK did not survive"


def test_v6_upgrade_discards_the_derived_graph(at_version):
    """The knowledge tables are a cache over files and messages still on disk,
    so a shape change drops them rather than migrating them."""
    at_version(V6)
    db.init()
    assert db.connect().execute(
        "SELECT COUNT(*) c FROM knowledge_nodes").fetchone()["c"] == 0


def test_a_conversation_graph_cascades_with_its_conversation(at_version):
    at_version(V6)
    db.init()
    conn = db.connect()
    conn.execute("INSERT INTO conversations (id,title,created_at,updated_at)"
                 " VALUES ('c1','t',1,1)")
    conn.execute("INSERT INTO knowledge_nodes"
                 " (id,label,key,type,scope,conversation_id,salience,created_at,updated_at)"
                 " VALUES ('n2','we chose X','d1','decision','conv:c1','c1',1,1,1)")
    conn.commit()

    conn.execute("DELETE FROM conversations WHERE id='c1'")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) c FROM knowledge_nodes").fetchone()["c"] == 0, \
        "a conversation's graph outlived the conversation"


def test_a_newer_database_is_refused_rather_than_corrupted(at_version):
    """CRS §4.4.3 — refuse rather than corrupt."""
    at_version(V6)
    with db.tx() as c:
        c.execute("INSERT OR REPLACE INTO schema_migrations VALUES (?,?,?)",
                  (db.SCHEMA_VERSION + 5, "from the future", 1))

    with pytest.raises(RuntimeError, match="Upgrade the app"):
        db.init()
