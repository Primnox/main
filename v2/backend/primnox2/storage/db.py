"""SQLite access — CRS/1.0 §4.

One database (§4.1). Splitting state across files is prohibited: a state change
and the event describing it must commit together (§4.2), and across two SQLite
files they cannot without ATTACH and a shared journal.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# CRS §4.4 — bump when schema.sql changes, and add a migration below.
#
# v3 adds `execution_sessions`. Pure table additions need no migration entry:
# schema.sql is CREATE TABLE IF NOT EXISTS throughout and runs on every boot,
# so a new table appears on existing databases too. Only CHECK-constraint
# changes require the rebuild dance in _m002.
#
# v6 adds the knowledge graph (V2.2) — eight tables, no constraint changes.
# Its jobs are namespaced `memory.*` rather than a new `graph.*` namespace
# specifically to stay inside the existing jobs.kind CHECK: a new namespace
# would mean rebuilding the jobs table, and the graph IS the memory system.
#
# v7 persists per-conversation graphs into those same tables, which widens
# knowledge_nodes' type CHECK and adds a conversation_id foreign key.
SCHEMA_VERSION = 7

_local = threading.local()
_db_path: Path | None = None
# SQLite permits exactly one writer. Serialising writes here turns what would
# be SQLITE_BUSY retries into an orderly queue, and gives §3.1's gapless
# counter a single place to be incremented.
write_lock = threading.RLock()


def configure(path: str | Path) -> None:
    """Point the runtime at a database file.

    Drops the CALLING thread's cached connection, because `connect()` memoises
    one per thread and would otherwise keep handing back a handle to the
    previous file — reconfiguring would appear to succeed and change nothing.

    It cannot reach connections other threads have already opened; there is no
    portable way to close a sqlite3 handle owned by another thread, and doing so
    mid-query would be worse than the staleness. So this must be called before
    the scheduler starts, which is the one place production calls it.
    """
    global _db_path
    stale = getattr(_local, "conn", None)
    if stale is not None:
        try:
            stale.close()
        except Exception:  # pragma: no cover - a dead handle is already gone
            pass
        _local.conn = None

    _db_path = Path(path)
    _db_path.parent.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    """One connection per thread.

    Every PRAGMA here is per-connection, not per-database — `foreign_keys`
    especially (§4.3.1). Setting it once at startup does nothing for the rest
    of the pool, which is the classic way to end up with unenforced foreign
    keys in production and enforced ones in tests.
    """
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    if _db_path is None:
        raise RuntimeError("storage.configure() must be called before connect()")

    conn = sqlite3.connect(str(_db_path), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    _local.conn = conn
    return conn


class tx:
    """`BEGIN IMMEDIATE` context manager for anything that writes.

    IMMEDIATE, not DEFERRED (§4.2.2): a deferred transaction takes its write
    lock lazily, so it can fail with SQLITE_BUSY *after* the caller has already
    done part of the work and believes it holds the database.
    """

    def __init__(self) -> None:
        self.conn = connect()

    def __enter__(self) -> sqlite3.Connection:
        write_lock.acquire()
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is None:
                self.conn.execute("COMMIT")
            else:
                try:
                    self.conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    # "cannot rollback - no transaction is active" happens when
                    # something inside the block ended the transaction (notably
                    # executescript, which issues an implicit COMMIT). Raising
                    # here would replace the real exception with a misleading
                    # one and hide the actual failure.
                    pass
        finally:
            write_lock.release()
        return False


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def init() -> None:
    conn = connect()

    # Migrations run BEFORE schema.sql, not after.
    #
    # schema.sql is idempotent DDL that describes the CURRENT shape, and
    # CREATE TABLE IF NOT EXISTS silently leaves an out-of-date table alone —
    # so any statement in it that depends on a column a migration adds will
    # fail on exactly the databases the migration exists to fix. A partial
    # index on a new column is the ordinary way to hit this, and it did:
    # `CREATE INDEX … ON knowledge_nodes(conversation_id)` raised "no such
    # column" against a v6 database, before the migration that adds the column
    # ever ran.
    #
    # Migrating first means every migration must be a no-op on an empty
    # database, which is what the _has_table guards below are for.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at INTEGER NOT NULL)"
    )
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    current = row["v"] if row and row["v"] is not None else 0

    if current > SCHEMA_VERSION:
        # CRS §4.4.3 — refuse rather than corrupt.
        raise RuntimeError(
            f"primnox.db is at schema v{current}; this build understands v{SCHEMA_VERSION}. "
            "Upgrade the app instead of downgrading the database."
        )

    for version, name, fn in _MIGRATIONS:
        if current < version:
            fn(conn)
            with tx() as c:
                c.execute(
                    "INSERT OR REPLACE INTO schema_migrations (version, name, applied_at) VALUES (?,?,?)",
                    (version, name, int(time.time() * 1000)),
                )

    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    if current < SCHEMA_VERSION:
        with tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO schema_migrations (version, name, applied_at) VALUES (?,?,?)",
                (SCHEMA_VERSION, "current", int(time.time() * 1000)),
            )


def _m002_split_thinking_and_namespace_jobs(conn: sqlite3.Connection) -> None:
    """v1 -> v2: split `preparing` into `building_context` + `thinking`, and
    namespace job kinds by owning service.

    Both are CHECK-constraint changes, and SQLite cannot alter a CHECK in
    place — the table has to be rebuilt. CREATE TABLE IF NOT EXISTS in
    schema.sql silently leaves an existing table on the OLD constraint, so
    without this an upgraded database would reject every new status value at
    runtime while looking perfectly healthy at startup.
    """
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='turns'").fetchone():
        return  # fresh database: schema.sql already built it correctly

    turns_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='turns'").fetchone()
    jobs_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='jobs'").fetchone()
    # The guard must cover EVERY table this migration touches. Checking only
    # `turns` meant a run that died partway through was treated as complete on
    # the next boot, leaving `jobs` on the old constraint permanently.
    if (turns_ddl and "building_context" in turns_ddl["sql"]
            and jobs_ddl and "GLOB" in jobs_ddl["sql"]):
        return

    # Three pragmas, each load-bearing, all set OUTSIDE the transaction:
    #
    #  foreign_keys=OFF     so the rebuild can drop and recreate tables others
    #                       reference.
    #  legacy_alter_table=ON  because since SQLite 3.25 `ALTER TABLE x RENAME
    #                       TO x_old` also REWRITES every other table's FK
    #                       clause to point at x_old. Dropping x_old then
    #                       leaves all of them dangling — measured here as 104
    #                       foreign_key_check violations before this was added.
    #
    # executescript() is also avoided below: it issues an implicit COMMIT,
    # which ends the transaction mid-rebuild.
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        with tx() as c:
            # ── turns: split `preparing` into building_context/thinking ──
            c.execute("ALTER TABLE turns RENAME TO turns_old")
            c.execute("""
                CREATE TABLE turns (
                    id                  TEXT    PRIMARY KEY,
                    conversation_id     TEXT    NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    seq_in_conversation INTEGER NOT NULL,
                    status              TEXT    NOT NULL,
                    error_code          TEXT,
                    error_message       TEXT,
                    error_retryable     INTEGER,
                    retry_of_turn_id    TEXT    REFERENCES turns(id) ON DELETE SET NULL,
                    created_at          INTEGER NOT NULL,
                    completed_at        INTEGER,
                    CHECK (status IN ('queued','building_context','thinking','streaming','tool_running',
                                      'awaiting_input','completed','failed','cancelled')),
                    CHECK ((status IN ('completed','failed','cancelled')) = (completed_at IS NOT NULL)),
                    UNIQUE (conversation_id, seq_in_conversation)
                )
            """)
            c.execute("""
                INSERT INTO turns SELECT id, conversation_id, seq_in_conversation,
                       CASE status WHEN 'preparing' THEN 'building_context' ELSE status END,
                       error_code, error_message, error_retryable, retry_of_turn_id,
                       created_at, completed_at
                  FROM turns_old
            """)
            c.execute("DROP TABLE turns_old")
            c.execute("CREATE INDEX IF NOT EXISTS idx_turns_conversation"
                      " ON turns(conversation_id, seq_in_conversation)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_turns_live ON turns(status)"
                      " WHERE status NOT IN ('completed','failed','cancelled')")

            # ── jobs: namespace kinds by owning service ──
            # This table carries its own CHECK on `kind`, so simply UPDATEing
            # 'chat' to 'chat.reply' fails against the old constraint. It has
            # to be rebuilt too.
            c.execute("ALTER TABLE jobs RENAME TO jobs_old")
            c.execute("""
                CREATE TABLE jobs (
                    id               TEXT    PRIMARY KEY,
                    turn_id          TEXT    REFERENCES turns(id) ON DELETE CASCADE,
                    kind             TEXT    NOT NULL,
                    status           TEXT    NOT NULL,
                    idempotent       INTEGER NOT NULL DEFAULT 0,
                    cancellable      INTEGER NOT NULL DEFAULT 1,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    priority         INTEGER NOT NULL DEFAULT 0,
                    attempts         INTEGER NOT NULL DEFAULT 0,
                    max_attempts     INTEGER NOT NULL DEFAULT 1,
                    payload          TEXT    NOT NULL,
                    result           TEXT,
                    result_ref       TEXT    REFERENCES assets(id) ON DELETE SET NULL,
                    error            TEXT,
                    created_at       INTEGER NOT NULL,
                    started_at       INTEGER,
                    finished_at      INTEGER,
                    CHECK (kind GLOB 'chat.*' OR kind GLOB 'tool.*' OR kind GLOB 'asset.*'
                        OR kind GLOB 'context.*' OR kind GLOB 'workspace.*'
                        OR kind GLOB 'memory.*' OR kind GLOB 'maintenance.*'),
                    CHECK (status IN ('queued','running','completed','failed','cancelled')),
                    CHECK (max_attempts = 1 OR idempotent = 1)
                )
            """)
            c.execute("""
                INSERT INTO jobs SELECT id, turn_id,
                       CASE kind
                            WHEN 'chat'   THEN 'chat.reply'
                            WHEN 'tool'   THEN 'tool.run'
                            WHEN 'skill'  THEN 'tool.skill'
                            WHEN 'asset'  THEN 'asset.ingest'
                            WHEN 'memory' THEN 'memory.extract'
                            WHEN 'maintenance' THEN 'maintenance.sweep'
                            ELSE kind END,
                       status, idempotent, cancellable, cancel_requested, priority,
                       attempts, max_attempts, payload, result, result_ref, error,
                       created_at, started_at, finished_at
                  FROM jobs_old
            """)
            c.execute("DROP TABLE jobs_old")
            c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_queued ON jobs(priority DESC, created_at)"
                      " WHERE status = 'queued'")
            c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_turn ON jobs(turn_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_running ON jobs(status) WHERE status = 'running'")

        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError(
                f"migration 2 left {len(broken)} dangling reference(s) — refusing to "
                f"mark it applied. First: {tuple(broken[0])}"
            )
    finally:
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute("PRAGMA foreign_keys = ON")


def _m004_record_the_code_that_ran(conn: sqlite3.Connection) -> None:
    """v3 -> v4: keep the source an execution actually ran.

    The session recorded stdout, stderr and the file diff — everything about
    the result and nothing about the cause. When a run produced a nearly empty
    Word document there was no way to tell whether the model had written thin
    code or the parser had mangled good code on its way in. A plain ADD COLUMN;
    no CHECK constraint is involved, so no table rebuild.
    """
    if not _has_table(conn, "execution_sessions"):
        return  # fresh database: schema.sql will build it with the column
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(execution_sessions)")}
    if "code" not in existing:
        conn.execute("ALTER TABLE execution_sessions ADD COLUMN code TEXT")


def _m005_pin_conversations(conn: sqlite3.Connection) -> None:
    """v4 -> v5: a timestamp rather than a flag.

    `pinned INTEGER` would say which conversations are pinned and nothing
    about their order, so a second pin would have to sort by `updated_at` and
    jump around the moment either chat was used. The time it was pinned is a
    stable order that costs the same column.
    """
    if not _has_table(conn, "conversations"):
        return  # fresh database: schema.sql will build it with the column
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(conversations)")}
    if "pinned_at" not in existing:
        conn.execute("ALTER TABLE conversations ADD COLUMN pinned_at INTEGER")


def _m007_persist_conversation_graphs(conn: sqlite3.Connection) -> None:
    """v6 -> v7: widen knowledge_nodes' type CHECK and add conversation_id.

    Rebuilt by DROP rather than the copy-into-a-new-table dance in _m002,
    because every row in these tables is DERIVED — nodes and edges are a cache
    over files and messages that are themselves still on disk. Dropping costs a
    re-index, never a fact. Preserving them would mean writing a data migration
    for a cache, which is work in exchange for nothing.

    Nothing is recreated here: init() runs schema.sql immediately after the
    migrations, and it rebuilds every dropped table in its current shape.
    """
    if not _has_table(conn, "knowledge_nodes"):
        return  # fresh database: schema.sql will build the current shape

    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='knowledge_nodes'").fetchone()
    if ddl and "conversation_id" in (ddl["sql"] or ""):
        return  # already at the new shape

    for table in ("cluster_members", "graph_clusters", "graph_chunk_state",
                  "entity_mentions", "node_aliases", "knowledge_edges",
                  "knowledge_nodes"):
        conn.execute(f"DROP TABLE IF EXISTS {table}")


_MIGRATIONS = [
    (2, "split_thinking_and_namespace_jobs", _m002_split_thinking_and_namespace_jobs),
    (4, "record_the_code_that_ran", _m004_record_the_code_that_ran),
    (5, "pin_conversations", _m005_pin_conversations),
    (7, "persist_conversation_graphs", _m007_persist_conversation_graphs),
]


def sweep_on_boot() -> dict:
    """CRS §10.3 — nothing may stay non-terminal across a restart.

    A crash leaves jobs in `running` and turns mid-flight. Left alone they are
    invisible zombies: the UI shows a spinner forever and the scheduler never
    picks them up again because they are not `queued`.
    """
    # Lazy, because `kernel.events` imports this module. By the time a sweep
    # runs the event system is fully loaded, so the cycle never materialises.
    from ..kernel.events import bus

    now = int(time.time() * 1000)
    pending: list[dict] = []
    with tx() as c:
        requeued = c.execute(
            "UPDATE jobs SET status='queued', started_at=NULL "
            " WHERE status='running' AND idempotent=1"
        ).rowcount
        failed_jobs = c.execute(
            "UPDATE jobs SET status='failed', error='interrupted by shutdown', finished_at=? "
            " WHERE status='running' AND idempotent=0",
            (now,),
        ).rowcount

        # Read the doomed turns before updating them, so each one can be
        # announced. Changing the row without emitting anything leaves a
        # reconnecting client showing "Writing" forever — it never learns the
        # turn died, which is the stuck-spinner defect this whole rewrite is
        # meant to eliminate.
        doomed = c.execute(
            "SELECT id, conversation_id FROM turns"
            " WHERE status NOT IN ('completed','failed','cancelled')"
        ).fetchall()

        # Partial assistant text is preserved — the message row is untouched.
        failed_turns = c.execute(
            "UPDATE turns SET status='failed', error_code='internal', "
            "       error_message='interrupted by shutdown', error_retryable=1, completed_at=? "
            " WHERE status NOT IN ('completed','failed','cancelled')",
            (now,),
        ).rowcount

        for row in doomed:
            pending.append(bus.emit(
                "turn.failed",
                {"code": "internal",
                 "message": "This reply was interrupted when Primnox restarted.",
                 "retryable": True},
                conversation_id=row["conversation_id"], turn_id=row["id"], conn=c,
            ))

    # After COMMIT, never inside it (§4.2.3).
    bus.deferred_fanout(pending)
    return {"jobs_requeued": requeued, "jobs_failed": failed_jobs, "turns_failed": failed_turns}
