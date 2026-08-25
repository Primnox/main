"""Shared SQLite storage for the V2 substrate.

Every V2 subsystem that persists anything lands in one database file
(`primnox_v2.db`, alongside V1's `memory.db` and `chat.db` in the app data
directory). One file rather than one per subsystem, because the whole point
of the world model is that a memory, an event, a tool result and a task can
reference each other — cross-database joins and cross-database transactions
are not worth the isolation.

Three things this module is responsible for:

1. **Connections.** One connection per thread per database, kept open and
   reused. `memory.py` learned this the hard way: reconnecting (plus
   re-running `PRAGMA journal_mode=WAL`) on every call was a measurable cost
   at scale. SQLite connections are not safe to share across threads by
   default, so `threading.local()` gives each thread its own without a lock.

2. **Schema.** Subsystems declare their own DDL and call
   :func:`ensure_schema` before first use. The registry keeps one module's
   tables out of another module's import path while still guaranteeing the
   DDL has run exactly once per process per database.

3. **Redirection.** :func:`configure` points storage at a different file.
   Tests use it to get a hermetic per-test database; without it every V2
   test would share the developer's real app-data database.

Import is deliberately side-effect free: no directory is created and no
database opened until something actually asks for a connection.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_NAME = "primnox_v2.db"

# Set by configure(); None means "resolve from the environment on demand".
_configured_path: Path | None = None

_thread_local = threading.local()

# Which (db path, schema name) pairs have had their DDL applied in this
# process. DDL is all IF NOT EXISTS, so re-running it would be harmless but
# not free — this keeps first-use cost off the hot path.
_applied_schemas: set[tuple[str, str]] = set()
_schema_lock = threading.Lock()


def _app_data_dir() -> Path:
    """App data directory, matching V1's `memory.py` resolution exactly.

    Deliberately duplicated rather than imported from `memory`: importing
    that module executes a vault auto-unlock at import time, which is a
    surprising side effect for anything that only wanted a directory path.
    """
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "primnox_extension" if appdata else Path.home() / ".primnox_extension"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    """Resolve the active database path.

    Precedence: explicit :func:`configure` call, then the `PRIMNOX_V2_DB`
    environment variable, then the app data directory. The env var exists so
    a packaged build or a debugging session can redirect storage without a
    code change.
    """
    if _configured_path is not None:
        return _configured_path
    env = os.environ.get("PRIMNOX_V2_DB")
    if env:
        return Path(env)
    return _app_data_dir() / DEFAULT_DB_NAME


def configure(path: str | Path | None) -> None:
    """Point V2 storage at `path` (or back at the default when None).

    Closes any open connections first: leaving a connection open against the
    previous file would keep an OS-level lock on it, which on Windows blocks
    the caller from moving or deleting that file afterwards.
    """
    global _configured_path
    close_all()
    _configured_path = Path(path) if path is not None else None


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.row_factory = sqlite3.Row
        # WAL keeps a reader (the retrieval path) from blocking on a writer
        # (an observation being recorded), which for V2 is the common case:
        # events and tool results are written while a query is in flight.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    except sqlite3.DatabaseError:
        # sqlite3.connect() succeeds even against a malformed file — the
        # first real read is what raises. An open connection holds an
        # OS-level lock, so recovery code that wants to move the bad file
        # aside needs this handle released first.
        conn.close()
        raise
    return conn


def connect() -> sqlite3.Connection:
    """Thread-local connection to the active database."""
    path = db_path()
    key = str(path)
    conns: dict[str, sqlite3.Connection] = getattr(_thread_local, "conns", None)
    if conns is None:
        conns = {}
        _thread_local.conns = conns
    conn = conns.get(key)
    if conn is None:
        conn = _open(path)
        conns[key] = conn
    return conn


def close_all() -> None:
    """Close this thread's connections.

    Only this thread's: a connection belonging to another thread cannot be
    closed safely from here. Other threads' connections are released when
    those threads end or call this themselves.
    """
    conns: dict[str, sqlite3.Connection] = getattr(_thread_local, "conns", None)
    if not conns:
        return
    for conn in conns.values():
        with contextlib.suppress(Exception):
            conn.close()
    conns.clear()


def ensure_schema(name: str, statements: list[str]) -> None:
    """Apply a subsystem's DDL once per process per database.

    `name` identifies the subsystem ("world_model", "episodes", ...).
    `statements` must all be idempotent (`IF NOT EXISTS`) so that a second
    process, or a database that already has the tables, is a no-op.
    """
    key = (str(db_path()), name)
    if key in _applied_schemas:
        return
    with _schema_lock:
        if key in _applied_schemas:
            return
        conn = connect()
        with conn:
            for statement in statements:
                conn.execute(statement)
        _applied_schemas.add(key)


@contextlib.contextmanager
def transaction():
    """Run a block in a single transaction, committing or rolling back.

    `sqlite3.Connection` as a context manager already does commit/rollback;
    this wrapper exists so call sites read as `with store.transaction() as
    conn:` and never have to think about which connection they are on.
    """
    conn = connect()
    with conn:
        yield conn


def reset_for_tests(path: str | Path | None = None) -> None:
    """Drop cached connections and schema state, optionally repointing.

    Without clearing `_applied_schemas`, a test that points storage at a
    fresh temp file would find the DDL "already applied" for a database that
    has no tables in it.
    """
    close_all()
    _applied_schemas.clear()
    configure(path)


def utc_now() -> str:
    """Current UTC time as a timezone-aware ISO-8601 string.

    Every timestamp written by V2 goes through here. V1 used naive
    `datetime.now().isoformat()`, which makes "what was I doing yesterday?"
    ambiguous the moment a machine changes timezone or crosses DST — the
    exact query V2 has to answer correctly. Fixed-offset UTC strings also
    sort lexicographically, so `ORDER BY timestamp` is chronological order
    without parsing.
    """
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str | None) -> datetime | None:
    """Parse a stored timestamp back to an aware datetime.

    Tolerates the naive timestamps V1 wrote (and the `Z` suffix other tools
    produce) by assuming UTC, so V2 can read pre-existing V1 rows without a
    migration pass.
    """
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
