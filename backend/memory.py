import sqlite3
import json
import hashlib
import os
import random
import threading
from pathlib import Path
from datetime import datetime, timedelta
from logger import get_logger

log = get_logger("memory")

def _get_appdata_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "primnox_extension" if appdata else Path.home() / ".primnox_extension"
    base.mkdir(parents=True, exist_ok=True)
    return base

DB_PATH = _get_appdata_dir() / "memory.db"
OLD_MEMORY_PATH = Path(__file__).parent / "memory.json"
OLD_KEY_PATH = Path(__file__).parent / "memory.key"

CATEGORIES = ["work", "personal", "project", "session"]

def _auto_unlock_vault():
    """If a local vault exists for memory.db, try to unlock it using the
    OS-keychain-cached key. If locked and no key is cached, leave the
    plaintext db absent — init_db() will then create a fresh empty db
    and the user can restore from their mnemonic via /api/vault/unlock."""
    try:
        import local_vault
        if local_vault.is_locked(DB_PATH):
            try:
                local_vault.unlock_vault(DB_PATH)
                log.info("Local vault auto-unlocked from keychain key.")
            except PermissionError:
                log.warning("Local vault is locked and no keychain key found. "
                             "Memory will be empty until unlocked via /api/vault/unlock.")
    except Exception as e:
        log.error(f"Vault auto-unlock check failed: {e}")

_auto_unlock_vault()

# A fresh sqlite3.connect() (plus a PRAGMA journal_mode=WAL re-execution) on
# every single call added up — benchmarked as a real, if secondary, cost
# behind add_memory/search_memories at scale. One connection per thread,
# kept open and reused, removes that overhead; threading.local() keeps it
# from being shared across threads without needing a lock, since SQLite
# connections aren't safe to share that way by default.
_thread_local = threading.local()


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        # sqlite3.connect() succeeds even against a malformed file — it's the
        # first real read (the PRAGMA) that raises. On Windows, an open
        # sqlite3.Connection holds an OS-level file lock, so recovery code
        # that tries to move/delete the corrupted file right after this
        # fails with WinError 32 unless this handle is explicitly released
        # first (found live via this fix's own test suite).
        conn.close()
        raise
    return conn


def _recover_corrupted_db(exc: Exception) -> sqlite3.Connection:
    """A forceful process kill mid-write (crash, kill -9, OS shutdown) can
    leave memory.db as a malformed SQLite file — this happened for real in
    production (root-caused to local_vault's _secure_delete overwrite being
    interrupted). Previously this was a hard crash on every subsequent
    startup. Recovery order: (1) if a local vault exists, decrypt it back
    over the corrupted file — the vault is the last known-good copy;
    (2) otherwise, move the corrupted file aside (never delete — it may
    still hold forensic/recoverable data) and start fresh, exactly like the
    manual recovery already performed once this session."""
    import shutil
    from datetime import datetime as _dt

    log.error(f"memory.db failed to open ({exc}) — attempting recovery")

    try:
        import local_vault
        vault_file = local_vault.vault_path(DB_PATH)
        if vault_file.exists():
            local_vault.unlock_vault(DB_PATH)
            conn = _connect(DB_PATH)
            log.info("memory.db recovered from local vault backup.")
            return conn
    except Exception as recovery_exc:
        log.error(f"Vault-based recovery failed ({recovery_exc}) — falling back to a fresh database")

    corrupted_path = DB_PATH.with_name(f"{DB_PATH.name}.corrupted-{_dt.now().strftime('%Y%m%d_%H%M%S')}")
    try:
        shutil.move(str(DB_PATH), str(corrupted_path))
        log.warning(f"Corrupted memory.db moved to {corrupted_path.name} — starting with a fresh database.")
    except Exception as move_exc:
        log.error(f"Could not move aside corrupted memory.db ({move_exc}) — deleting it instead")
        DB_PATH.unlink(missing_ok=True)

    return _connect(DB_PATH)


def get_db():
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        try:
            conn = _connect(DB_PATH)
        except sqlite3.DatabaseError as e:
            conn = _recover_corrupted_db(e)
        _thread_local.conn = conn
    return conn


def _reset_db_connection():
    """Drop this thread's cached connection so the next get_db() call opens a
    fresh one against the current DB_PATH. Needed whenever the file on disk
    changes out from under an already-open connection: init_db() calls this
    (so tests that monkeypatch DB_PATH actually take effect instead of
    silently reusing a connection to the old path), and local_vault.py calls
    it after unlock_vault()/lock_vault() rewrite the file in place."""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _thread_local.conn = None


def init_db():
    _reset_db_connection()
    conn = get_db()
    c = conn.cursor()
    # Create main table
    c.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            key TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            category TEXT,
            timestamp TEXT,
            stale INTEGER DEFAULT 0,
            session_id TEXT
        )
    ''')
    try:
        c.execute("ALTER TABLE memories ADD COLUMN session_id TEXT")
    except sqlite3.OperationalError:
        pass
    # compressed: 0 = raw original, 1 = compressed summary (from multiple originals)
    try:
        c.execute("ALTER TABLE memories ADD COLUMN compressed INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    # topic: structural grouping key (e.g. "project:primnox"), independent of
    # the coarser `category`. Falls back to category when nothing more
    # specific was resolved (see memory_mirror.py).
    try:
        c.execute("ALTER TABLE memories ADD COLUMN topic TEXT")
    except sqlite3.OperationalError:
        pass
    # provenance: how this memory was learned. "explicit" = the user stated it
    # or typed it directly; anything else was inferred (from a chat exchange or
    # ambient screen-watching) and should decay faster / be surfaced as a
    # guess rather than settled fact until confirmed.
    try:
        c.execute("ALTER TABLE memories ADD COLUMN provenance TEXT DEFAULT 'explicit'")
    except sqlite3.OperationalError:
        pass
    # access_count: bumped every time search_memories() actually returns this
    # row. Used as a cheap, zero-token signal of how load-bearing a memory is
    # — no model call needed to score importance.
    try:
        c.execute("ALTER TABLE memories ADD COLUMN access_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    # add_memory()'s dedup check does WHERE category = ? ORDER BY timestamp
    # DESC LIMIT 200 — without this, SQLite has to scan and sort the entire
    # category before it can return the top 200, so the "cap" only bounded
    # how much text got compared, not how much got scanned. That made every
    # add_memory() call scale with total memory count instead of being flat
    # (measured: ~11ms at 100 memories vs ~41ms at 20k in bench_memory.py).
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_category_timestamp ON memories(category, timestamp DESC)")

    # Create FTS5 virtual table for full-text search
    c.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            text,
            content='memories',
            content_rowid='rowid'
        )
    ''')
    
    # Triggers to keep FTS table in sync with memories table
    c.execute('''
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, text) VALUES (new.rowid, new.text);
        END;
    ''')
    c.execute('''
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, text) VALUES('delete', old.rowid, old.text);
        END;
    ''')
    c.execute('''
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, text) VALUES('delete', old.rowid, old.text);
            INSERT INTO memories_fts(rowid, text) VALUES (new.rowid, new.text);
        END;
    ''')
    conn.commit()

def _migrate_old_memory():
    """Legacy migration path removed. The old Fernet key/JSON scheme is
    deprecated; memory.key(.bak) and memory.json(.bak) should be deleted
    from disk and history (the key was previously exposed)."""
    return

# Initialize DB on import
init_db()
_migrate_old_memory()


def get_memory():
    # Helper to return all memories in dict format (used by some old logic)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT key, text, category, timestamp, stale FROM memories")
    rows = c.fetchall()
    return [{"key": r[0], "text": r[1], "category": r[2], "timestamp": r[3], "stale": bool(r[4])} for r in rows]


def memory_score(timestamp: str, access_count: int) -> float:
    """Cheap, zero-token importance score: recency decays linearly over 30
    days, each recall (via search_memories) is worth two extra days of
    "freshness". No LLM call — just arithmetic on data already being tracked.
    """
    try:
        age_days = (datetime.now() - datetime.fromisoformat(timestamp)).total_seconds() / 86400
    except Exception:
        age_days = 30.0
    recency = max(0.0, 30.0 - age_days) / 30.0
    return recency + (access_count or 0) * 0.1

def delete_memory(key_or_text):
    log.info(f"Deleting memory matching: {key_or_text}")
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE key = ? OR text = ?", (key_or_text, key_or_text))
    rows_deleted = c.rowcount
    conn.commit()

    if rows_deleted > 0:
        log.info(f"Memory deleted successfully. ({rows_deleted} rows)")
    else:
        log.warning(f"No memory found matching: {key_or_text}")

def delete_memories_by_session(session_id):
    if not session_id:
        return
    log.info(f"Deleting memories for session: {session_id}")
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE session_id = ?", (session_id,))
    rows_deleted = c.rowcount
    conn.commit()
    if rows_deleted > 0:
        log.info(f"Deleted {rows_deleted} memories for session {session_id}.")

STALE_AFTER_DAYS = 30
# Inferred memories (a guess from a chat exchange or ambient screen-watching)
# haven't been confirmed by the user, so they earn less benefit of the doubt
# than something explicitly stated — they go stale in a third of the time.
INFERRED_STALE_AFTER_DAYS = 10
# A memory that keeps getting pulled back up by search_memories() is clearly
# still load-bearing even if old, so each recall buys it extra days before
# the staleness cutoff applies (capped so a runaway access_count can't make a
# memory immortal).
_ACCESS_GRACE_DAYS_PER_HIT = 2
_ACCESS_GRACE_CAP_DAYS = 60


def mark_stale_memories(stale_after_days: int = STALE_AFTER_DAYS) -> int:
    """Flag memories past their age cutoff as stale. Returns rows newly flagged.

    list_memories() used to drop old rows by recomputing age on every read while
    the `stale` column it selected was never written by anything — so a memory
    could vanish from the UI while its own flag still said it was fresh. The
    cutoff is applied here, once, by the cleanup scheduler; every reader now
    just trusts the column.

    The cutoff itself isn't flat: explicit (user-stated) memories get the full
    window, inferred ones decay faster, and frequently-recalled memories of
    either kind earn extra time — see INFERRED_STALE_AFTER_DAYS and
    _ACCESS_GRACE_DAYS_PER_HIT.
    """
    now = datetime.now()
    conn = get_db()
    c = conn.cursor()
    # Grace only ever adds days, never subtracts, so nothing younger than the
    # smaller of the two base windows can possibly be stale yet. Filtering
    # that in SQL (rather than fetching every non-stale row and rejecting
    # most of them in the Python loop below) keeps this pass cheap even once
    # the table holds thousands of mostly-recent rows.
    min_base_days = min(stale_after_days, INFERRED_STALE_AFTER_DAYS)
    candidate_cutoff = (now - timedelta(days=min_base_days)).isoformat()
    c.execute(
        "SELECT key, timestamp, provenance, access_count FROM memories WHERE stale = 0 AND timestamp < ?",
        (candidate_cutoff,),
    )
    rows = c.fetchall()

    stale_keys = []
    for key, ts, provenance, access_count in rows:
        try:
            age_days = (now - datetime.fromisoformat(ts)).total_seconds() / 86400
        except Exception:
            continue
        base = stale_after_days if (provenance or "explicit") == "explicit" else INFERRED_STALE_AFTER_DAYS
        grace = min((access_count or 0) * _ACCESS_GRACE_DAYS_PER_HIT, _ACCESS_GRACE_CAP_DAYS)
        if age_days > base + grace:
            stale_keys.append(key)

    if stale_keys:
        c.executemany("UPDATE memories SET stale = 1 WHERE key = ?", [(k,) for k in stale_keys])
        conn.commit()

    if stale_keys:
        log.info(f"Marked {len(stale_keys)} memories stale")
    return len(stale_keys)


def list_memories(category=None, include_stale=False):
    log.debug(f"Listing memories (category={category}, include_stale={include_stale})...")
    conn = get_db()
    c = conn.cursor()

    query = "SELECT key, text, category, timestamp, stale, topic, provenance, access_count FROM memories WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)
    if not include_stale:
        query += " AND stale = 0"

    c.execute(query, params)
    rows = c.fetchall()

    return [
        {
            "key": r[0], "text": r[1], "category": r[2], "timestamp": r[3], "stale": bool(r[4]),
            "topic": r[5], "provenance": r[6] or "explicit", "access_count": r[7] or 0,
        }
        for r in rows
    ]

def is_duplicate(new, existing_memories, threshold=0.85):
    from difflib import SequenceMatcher
    # quick_ratio() is a cheap upper bound on ratio() (no real alignment work,
    # just character-count math) — benchmarked at ~10x faster than calling
    # ratio() outright on 200 candidates (42ms -> 4ms for the common case of
    # no match). Only pay for the expensive exact ratio() when quick_ratio()
    # says a match is even possible.
    sm = SequenceMatcher(None, new)
    for m in existing_memories:
        sm.set_seq2(m.get("text", ""))
        if sm.quick_ratio() > threshold and sm.ratio() > threshold:
            log.debug(f"Duplicate memory detected (ratio > {threshold})")
            return True
    return False

# How many prior memories a new one is compared against before being stored.
# Scoped per-category, so a busy "session" stream can't push older "work" or
# "personal" facts out of comparison range and let duplicates back in.
_DEDUP_CANDIDATES = 200


# Valid provenance values. "explicit" means the user stated or typed it
# directly (manual add, a save_memory tool call the user asked for). Anything
# else is a guess Primnox made on its own and hasn't been confirmed.
PROVENANCE_VALUES = {"explicit", "inferred_chat", "inferred_screen"}


def add_memory(text, category="session", session_id=None, topic=None, provenance="explicit"):
    # This runs on every single memory write — screen-watching alone can fire
    # it constantly — so it's DEBUG, not INFO; INFO here drowned out anything
    # else in the log the moment memory activity picked up.
    log.debug(f"Adding new memory: {text[:50]}...")
    conn = get_db()
    c = conn.cursor()

    cat = category if category in CATEGORIES else "session"
    prov = provenance if provenance in PROVENANCE_VALUES else "explicit"

    c.execute(
        "SELECT text FROM memories WHERE category = ? ORDER BY timestamp DESC LIMIT ?",
        (cat, _DEDUP_CANDIDATES),
    )
    recent = [{"text": r[0]} for r in c.fetchall()]

    if is_duplicate(text, recent):
        log.debug("Memory is a duplicate, skipping.")
        return False

    ts = datetime.now().isoformat()

    # datetime.now() alone isn't unique enough: found via concurrency stress
    # testing that multiple threads writing near-identical text at the same
    # moment (e.g. several ambient-capture threads firing together) could
    # land on the same microsecond timestamp and produce the same sha256 key,
    # raising UNIQUE constraint failed. random.random() makes a real collision
    # astronomically unlikely; the retry loop is a second line of defense so
    # a freak collision still can't crash the caller or, worse, leave this
    # thread's now-long-lived cached connection (see get_db()) sitting mid
    # transaction — the observed "database is locked" secondary failure.
    for _attempt in range(3):
        key = hashlib.sha256(f"{text}{ts}{random.random()}".encode()).hexdigest()
        try:
            c.execute(
                "INSERT INTO memories (key, text, category, timestamp, stale, session_id, topic, provenance, access_count) "
                "VALUES (?, ?, ?, ?, 0, ?, ?, ?, 0)",
                (key, text, cat, ts, session_id, topic, prov),
            )
            conn.commit()
            break
        except sqlite3.IntegrityError:
            conn.rollback()
    else:
        log.error("add_memory: could not generate a unique key after 3 attempts")
        return False

    if prov != "explicit":
        _last_inferred["key"] = key
        _last_inferred["text"] = text
    else:
        # An explicit statement means new context — "no, that's wrong" from
        # here on shouldn't reach back past it to correct an older guess.
        _last_inferred["key"] = None
        _last_inferred["text"] = None

    log.debug("Memory added successfully.")
    return True


# Last inferred (non-explicit) memory stored, so a "no, that's wrong" right
# after Primnox acts on a guess has something concrete to correct — see
# correct_last_inferred_memory(). Best-effort/in-memory only: a guess made in
# a previous run isn't something "that's wrong" should reach back for.
_last_inferred = {"key": None, "text": None}


def correct_last_inferred_memory() -> str | None:
    """Delete the most recent inferred memory and return its text, or None if
    there's nothing to correct (either nothing's been inferred yet, or it was
    already corrected/deleted since)."""
    key, text = _last_inferred["key"], _last_inferred["text"]
    if not key:
        return None
    _last_inferred["key"] = None
    _last_inferred["text"] = None
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE key = ?", (key,))
    deleted = c.rowcount > 0
    conn.commit()
    if deleted:
        log.info(f"Corrected (deleted) inferred memory: {text[:60]}")
    return text if deleted else None

def search_memories(query, limit=5):
    """
    Search memories using SQLite FTS5 MATCH algorithm.
    Extremely fast and scales to millions of records.
    """
    if not query:
        return []
        
    # Clean query for FTS MATCH (remove special chars)
    import re
    clean_query = re.sub(r'[^a-zA-Z0-9\s]', '', query).strip()
    if not clean_query:
        return []
        
    # FTS5 syntax: match all words using OR for broader semantic coverage
    words = clean_query.split()
    fts_query = " OR ".join(words)
    
    conn = get_db()
    c = conn.cursor()
    
    # Perform full-text search joining with original table to get metadata
    # FTS5 bm25 ranking function provides relevance scoring
    sql = '''
        SELECT m.key, m.text, m.category, m.timestamp, m.stale, m.topic, m.provenance, m.access_count
        FROM memories_fts f
        JOIN memories m ON f.rowid = m.rowid
        WHERE memories_fts MATCH ?
        ORDER BY bm25(memories_fts)
        LIMIT ?
    '''

    try:
        c.execute(sql, (fts_query, limit))
        rows = c.fetchall()
        result = [
            {
                "key": r[0], "text": r[1], "category": r[2], "timestamp": r[3], "stale": bool(r[4]),
                "topic": r[5], "provenance": r[6] or "explicit", "access_count": r[7] or 0,
            }
            for r in rows
        ]
    except sqlite3.OperationalError as e:
        log.error(f"FTS search error: {e}")
        # Fallback to simple LIKE search if FTS syntax breaks
        like_query = f"%{clean_query}%"
        c.execute(
            "SELECT key, text, category, timestamp, stale, topic, provenance, access_count "
            "FROM memories WHERE text LIKE ? LIMIT ?",
            (like_query, limit),
        )
        rows = c.fetchall()
        result = [
            {
                "key": r[0], "text": r[1], "category": r[2], "timestamp": r[3], "stale": bool(r[4]),
                "topic": r[5], "provenance": r[6] or "explicit", "access_count": r[7] or 0,
            }
            for r in rows
        ]

    # A memory that keeps getting recalled is clearly load-bearing — bump its
    # access_count so mark_stale_memories() gives it extra grace. Pure
    # arithmetic, no model call.
    if result:
        c.executemany(
            "UPDATE memories SET access_count = access_count + 1 WHERE key = ?",
            [(r["key"],) for r in result],
        )
        conn.commit()

    return result

def compress_old_memories(compress_after_days: int = 7) -> int:
    """
    Compress memories older than compress_after_days into weekly summaries.

    Algorithm:
      1. Fetch all un-compressed memories older than the threshold.
      2. Group by (category, ISO-week) — e.g. ("work", "2025-W22").
      3. For each group with ≥ 2 memories, ask the LLM to synthesise them
         into one condensed paragraph that preserves the key facts.
      4. Insert the summary as a new compressed memory.
      5. Delete the originals.

    Returns the number of original memories replaced.
    """
    if compress_after_days <= 0:
        return 0

    cutoff = datetime.now() - timedelta(days=compress_after_days)
    cutoff_iso = cutoff.isoformat()

    conn = get_db()
    c    = conn.cursor()

    c.execute(
        "SELECT key, text, category, timestamp FROM memories "
        "WHERE timestamp < ? AND (compressed IS NULL OR compressed = 0) AND stale = 0",
        (cutoff_iso,)
    )
    rows = c.fetchall()

    if not rows:
        return 0

    # Group by (category, ISO year-week)
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for key, text, category, ts in rows:
        try:
            dt = datetime.fromisoformat(ts)
        except Exception:
            continue
        week_bucket = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
        groups[(category or "session", week_bucket)].append((key, text, ts))

    total_replaced = 0

    for (category, week), items in groups.items():
        if len(items) < 2:
            continue   # nothing to compress for a single memory

        # Ask LLM to summarise
        bullet_list = "\n".join(f"- {text}" for _, text, _ in items)
        try:
            from brain import think
            resp = think(
                f"Compress these {len(items)} memories from week {week} into one concise "
                f"paragraph (2-4 sentences) that preserves every important fact, preference, "
                f"or decision. Be specific — include names, dates, numbers.\n\n{bullet_list}",
                system_override=(
                    "You are a memory archivist. Write a dense, factual summary. "
                    "No preamble. Preserve all concrete details."
                )
            )
            choices = resp.get("choices") or []
            summary = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
        except Exception as e:
            log.warning(f"Compression LLM call failed for {category}/{week}: {e}")
            continue

        if not summary:
            continue

        # Insert compressed memory
        new_key = hashlib.sha256(f"compressed:{category}:{week}".encode()).hexdigest()
        new_ts  = datetime.now().isoformat()
        conn = get_db()
        c    = conn.cursor()
        try:
            c.execute(
                "INSERT OR REPLACE INTO memories "
                "(key, text, category, timestamp, stale, session_id, compressed) "
                "VALUES (?, ?, ?, ?, 0, NULL, 1)",
                (new_key, summary, category, new_ts)
            )
            # Delete originals
            for key, _, _ in items:
                c.execute("DELETE FROM memories WHERE key = ?", (key,))
            conn.commit()
            total_replaced += len(items)
            log.info(
                f"Compressed {len(items)} memories → 1 summary "
                f"[{category} / {week}]"
            )
        except Exception as e:
            log.warning(f"DB error during compression: {e}")

    return total_replaced


if __name__ == "__main__":
    print("Current memories:", get_memory())
    add_memory("This is a test memory for SQLite.", "work")
    add_memory("The user prefers FTS5 for fast searches.", "personal")
    print("After add:", list_memories())
    
    print("\n--- Search Results ---")
    results = search_memories("FTS5 searches")
    for r in results:
        print(f"Match: {r['text']}")
        
    # delete_memory(results[0]["key"])
    # print("After delete:", get_memory())
