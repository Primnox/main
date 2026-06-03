import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime
from logger import get_logger

log = get_logger("memory")

DB_PATH = Path(__file__).parent / "memory.db"
OLD_MEMORY_PATH = Path(__file__).parent / "memory.json"
OLD_KEY_PATH = Path(__file__).parent / "memory.key"

CATEGORIES = ["work", "personal", "project", "session"]

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
            stale INTEGER DEFAULT 0
        )
    ''')
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
    if not OLD_MEMORY_PATH.exists() or not OLD_KEY_PATH.exists():
        return
        
    log.info("Found legacy memory.json, migrating to SQLite...")
    try:
        from cryptography.fernet import Fernet
        key = OLD_KEY_PATH.read_bytes()
        f = Fernet(key)
        enc = OLD_MEMORY_PATH.read_bytes()
        data = f.decrypt(enc)
        old_memories = json.loads(data)
        
        conn = get_db()
        c = conn.cursor()
        count = 0
        for m in old_memories:
            try:
                c.execute(
                    "INSERT INTO memories (key, text, category, timestamp, stale) VALUES (?, ?, ?, ?, ?)",
                    (m.get("key"), m.get("text"), m.get("category", "session"), m.get("timestamp", datetime.now().isoformat()), int(m.get("stale", False)))
                )
                count += 1
            except sqlite3.IntegrityError:
                pass # Duplicate key
        conn.commit()
        conn.close()
        
        # Rename old files to prevent re-migration
        OLD_MEMORY_PATH.rename(OLD_MEMORY_PATH.with_suffix('.json.bak'))
        OLD_KEY_PATH.rename(OLD_KEY_PATH.with_suffix('.key.bak'))
        
        log.info(f"Successfully migrated {count} memories to SQLite.")
    except Exception as e:
        log.error(f"Migration failed: {e}")

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

def add_memory(text, category="session"):
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
        
    key = hashlib.sha1((text+str(datetime.now())).encode()).hexdigest()
    ts = datetime.now().isoformat()
    cat = category if category in CATEGORIES else "session"
    
    c.execute("INSERT INTO memories (key, text, category, timestamp, stale) VALUES (?, ?, ?, ?, 0)", (key, text, cat, ts))
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

if __name__ == "__main__":
    print("Current memories:", get_memory())
    add_memory("This is a test memory for SQLite.", "work")
    add_memory("Aniketh prefers to use FTS5 for fast searches.", "personal")
    print("After add:", list_memories())
    
    print("\n--- Search Results ---")
    results = search_memories("Aniketh FTS5")
    for r in results:
        print(f"Match: {r['text']}")
        
    # delete_memory(results[0]["key"])
    # print("After delete:", get_memory())
