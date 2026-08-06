import sqlite3
import json
import hashlib
import os
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

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
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
    conn.close()

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
    conn.close()
    return [{"key": r[0], "text": r[1], "category": r[2], "timestamp": r[3], "stale": bool(r[4])} for r in rows]

def delete_memory(key_or_text):
    log.info(f"Deleting memory matching: {key_or_text}")
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE key = ? OR text = ?", (key_or_text, key_or_text))
    rows_deleted = c.rowcount
    conn.commit()
    conn.close()
    
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
    conn.close()
    if rows_deleted > 0:
        log.info(f"Deleted {rows_deleted} memories for session {session_id}.")

def list_memories(category=None, include_stale=False):
    log.debug(f"Listing memories (category={category}, include_stale={include_stale})...")
    conn = get_db()
    c = conn.cursor()
    
    query = "SELECT key, text, category, timestamp, stale FROM memories WHERE 1=1"
    params = []
    
    if category:
        query += " AND category = ?"
        params.append(category)
        
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    
    now = datetime.now()
    result = []
    for r in rows:
        stale = bool(r[4])
        ts = datetime.fromisoformat(r[3])
        if not include_stale and (now - ts).days > 30:
            continue
        result.append({"key": r[0], "text": r[1], "category": r[2], "timestamp": r[3], "stale": stale})
    return result

def extract_memories_from_text(text):
    return [s.strip() for s in text.split(".") if len(s.strip()) > 10]

def is_duplicate(new, existing_memories, threshold=0.85):
    from difflib import SequenceMatcher
    for m in existing_memories:
        if SequenceMatcher(None, new, m.get("text", "")).ratio() > threshold:
            log.debug(f"Duplicate memory detected (ratio > {threshold})")
            return True
    return False

def add_memory(text, category="session", session_id=None):
    log.info(f"Adding new memory: {text[:50]}...")
    conn = get_db()
    c = conn.cursor()
    
    # Simple deduplication check via exact match or FTS to save time
    # For now, we fetch recent memories to check difflib
    c.execute("SELECT text FROM memories ORDER BY timestamp DESC LIMIT 50")
    recent = [{"text": r[0]} for r in c.fetchall()]
    
    if is_duplicate(text, recent):
        log.info("Memory is a duplicate, skipping.")
        conn.close()
        return False
        
    key = hashlib.sha256((text+str(datetime.now())).encode()).hexdigest()
    ts = datetime.now().isoformat()
    cat = category if category in CATEGORIES else "session"
    
    c.execute("INSERT INTO memories (key, text, category, timestamp, stale, session_id) VALUES (?, ?, ?, ?, 0, ?)", (key, text, cat, ts, session_id))
    conn.commit()
    conn.close()
    
    log.info("Memory added successfully.")
    return True

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
        SELECT m.key, m.text, m.category, m.timestamp, m.stale
        FROM memories_fts f
        JOIN memories m ON f.rowid = m.rowid
        WHERE memories_fts MATCH ?
        ORDER BY bm25(memories_fts)
        LIMIT ?
    '''
    
    try:
        c.execute(sql, (fts_query, limit))
        rows = c.fetchall()
        result = [{"key": r[0], "text": r[1], "category": r[2], "timestamp": r[3], "stale": bool(r[4])} for r in rows]
    except sqlite3.OperationalError as e:
        log.error(f"FTS search error: {e}")
        # Fallback to simple LIKE search if FTS syntax breaks
        like_query = f"%{clean_query}%"
        c.execute("SELECT key, text, category, timestamp, stale FROM memories WHERE text LIKE ? LIMIT ?", (like_query, limit))
        rows = c.fetchall()
        result = [{"key": r[0], "text": r[1], "category": r[2], "timestamp": r[3], "stale": bool(r[4])} for r in rows]
        
    conn.close()
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
    conn.close()

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
        finally:
            conn.close()

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
