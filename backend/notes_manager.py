import re
import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime
from logger import get_logger

log = get_logger("notes")

def _get_appdata_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "primnox_extension" if appdata else Path.home() / ".primnox_extension"
    base.mkdir(parents=True, exist_ok=True)
    return base

DB_PATH = _get_appdata_dir() / "memory.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        text TEXT,
        key_points TEXT,
        action_items TEXT,
        timestamp TEXT,
        project TEXT,
        parent_id INTEGER,
        pinned INTEGER DEFAULT 0
    )''')
    try:
        c.execute("ALTER TABLE notes ADD COLUMN pinned INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
        
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT,
        priority TEXT,
        due_date TEXT,
        completed INTEGER DEFAULT 0,
        timestamp TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT,
        speaker TEXT,
        key_points TEXT,
        action_items TEXT,
        timestamp TEXT
    )''')

    # search_notes() used to do LIKE '%query%', which can't use an index —
    # every search was a full table scan (same class of bug memory.py had).
    # FTS5 mirrors memory.py's pattern: content='notes' keeps the index in
    # sync via triggers instead of duplicating the text.
    c.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            title, text,
            content='notes',
            content_rowid='id'
        )
    ''')
    c.execute('''
        CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
            INSERT INTO notes_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
        END;
    ''')
    c.execute('''
        CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, text) VALUES('delete', old.id, old.title, old.text);
        END;
    ''')
    c.execute('''
        CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, text) VALUES('delete', old.id, old.title, old.text);
            INSERT INTO notes_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
        END;
    ''')
    # Triggers only fire on writes going forward — notes created before this
    # migration existed would otherwise be permanently invisible to search.
    # 'rebuild' resyncs the FTS index from the content table; cheap at
    # personal-notes scale, safe to run on every startup.
    c.execute("INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")

    # Wiki-style [[Note Title]] links — many-to-many, distinct from parent_id
    # (which is a single-value hierarchy pointer for sub-pages). UNIQUE stops
    # re-saving a note with the same [[link]] twice from duplicating rows.
    c.execute('''
        CREATE TABLE IF NOT EXISTS note_links (
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            UNIQUE(source_id, target_id)
        )
    ''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_note_links_source ON note_links(source_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_note_links_target ON note_links(target_id)")

    conn.commit()
    conn.close()

init_db()

# Wiki-style note-to-note references, e.g. "see [[Project Roadmap]] for details".
WIKILINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]')


def _resolve_and_set_links(note_id, text: str) -> None:
    """Parse [[Title]] references out of a note's text and replace its
    outbound note_links rows to match. Title match is case-insensitive exact
    match — good enough for a first slice; ambiguous/unresolved titles are
    silently skipped rather than guessed at."""
    titles = {m.strip().lower() for m in WIKILINK_PATTERN.findall(text or "") if m.strip()}
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM note_links WHERE source_id=?", (note_id,))
        if titles:
            placeholders = ",".join("?" * len(titles))
            c.execute(
                f"SELECT id FROM notes WHERE lower(title) IN ({placeholders}) AND id != ?",
                (*titles, note_id),
            )
            target_ids = {r["id"] for r in c.fetchall()}
            c.executemany(
                "INSERT OR IGNORE INTO note_links (source_id, target_id) VALUES (?, ?)",
                [(note_id, tid) for tid in target_ids],
            )
        conn.commit()
    finally:
        conn.close()


def get_note_links(note_id) -> list:
    """Notes this note links out to via [[wiki-links]]."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT n.id, n.title FROM note_links l JOIN notes n ON n.id = l.target_id WHERE l.source_id = ?",
        (note_id,),
    )
    rows = [{"id": r["id"], "title": r["title"]} for r in c.fetchall()]
    conn.close()
    return rows


def get_backlinks(note_id) -> list:
    """Notes that link to this note (the reverse direction of get_note_links)."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT n.id, n.title FROM note_links l JOIN notes n ON n.id = l.source_id WHERE l.target_id = ?",
        (note_id,),
    )
    rows = [{"id": r["id"], "title": r["title"]} for r in c.fetchall()]
    conn.close()
    return rows


def search_note_titles(query: str, limit: int = 10) -> list:
    """Thin title-only lookup backing the [[ ]] autocomplete menu — cheap
    prefix/substring match, not a full FTS query (the editor calls this on
    every keystroke)."""
    conn = get_db()
    c = conn.cursor()
    if query and query.strip():
        q = f"%{query.strip()}%"
        c.execute("SELECT id, title FROM notes WHERE title LIKE ? ORDER BY title LIMIT ?", (q, limit))
    else:
        c.execute("SELECT id, title FROM notes ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = [{"id": r["id"], "title": r["title"]} for r in c.fetchall()]
    conn.close()
    return rows


def parse_note_json_response(content: str) -> dict:
    """Parse an LLM response that's supposed to be raw JSON
    {"title": ..., "body": ...} (the AI note builder's expected shape),
    tolerating a wrapping ```json fence some models add despite being told
    not to. Raises ValueError with a clear message on anything unusable, so
    callers don't have to separately handle JSONDecodeError, missing keys,
    and an empty body."""
    text = (content or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI response was not valid JSON: {e}")
    body = (data.get("body") or "").strip()
    if not body:
        raise ValueError("AI response had no note body")
    return {"title": (data.get("title") or "").strip() or "Untitled", "body": body}


def add_note(text, title=None, key_points=None, action_items=None, timestamp=None, project=None, parent_id=None):
    log.debug(f"Adding note: {title or 'Untitled'}")
    title = title or "Untitled Note"
    kp = json.dumps(key_points or extract_key_points(text))
    ai = json.dumps(action_items or extract_action_items(text))
    ts = timestamp or datetime.now().isoformat()

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO notes (title, text, key_points, action_items, timestamp, project, parent_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (title, text, kp, ai, ts, project, parent_id))
    conn.commit()
    note_id = c.lastrowid
    conn.close()
    _resolve_and_set_links(note_id, text)
    log.debug("Note saved.")
    return {"id": note_id, "title": title, "text": text, "timestamp": ts, "project": project, "parent_id": parent_id}

def update_note(index, title, text, project=None, parent_id=None):
    # index is now the direct database ID
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE notes SET title=?, text=?, timestamp=?, project=?, parent_id=? WHERE id=?", (title, text, datetime.now().isoformat(), project, parent_id, index))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    if success:
        _resolve_and_set_links(index, text)
    return success

def delete_note(index):
    # index is now the direct database ID
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM notes WHERE id=?", (index,))
    success = c.rowcount > 0
    if success:
        c.execute("DELETE FROM note_links WHERE source_id=? OR target_id=?", (index, index))
    conn.commit()
    conn.close()
    return success

def toggle_pin_note(index, pinned_status):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE notes SET pinned=? WHERE id=?", (1 if pinned_status else 0, index))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success

def get_notes():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM notes ORDER BY id ASC")
    rows = c.fetchall()
    notes = []
    for r in rows:
        notes.append({
            "id": r["id"],
            "title": r["title"],
            "text": r["text"],
            "key_points": json.loads(r["key_points"]) if r["key_points"] else [],
            "action_items": json.loads(r["action_items"]) if r["action_items"] else [],
            "timestamp": r["timestamp"],
            "project": r["project"],
            "parent_id": r["parent_id"],
            "pinned": bool(r["pinned"]) if "pinned" in r.keys() else False
        })
    conn.close()
    return notes


def get_note_by_id(note_id) -> dict | None:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
    r = c.fetchone()
    conn.close()
    if not r:
        return None
    return {
        "id": r["id"],
        "title": r["title"],
        "text": r["text"],
        "project": r["project"],
        "parent_id": r["parent_id"],
    }


def note_title_exists(title: str) -> bool:
    """Cheap existence check — used by meeting_recorder to avoid re-saving a
    duplicate summary without paying to fetch and JSON-decode every note."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT 1 FROM notes WHERE title = ? LIMIT 1", (title,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def search_notes(query: str, limit: int = 20) -> list:
    """Full-text search across note titles and bodies via FTS5."""
    if not query or not query.strip():
        return []

    import re
    clean_query = re.sub(r'[^a-zA-Z0-9\s]', '', query).strip()
    if not clean_query:
        return []
    fts_query = " OR ".join(clean_query.split())

    conn = get_db()
    c = conn.cursor()

    def _row_to_result(row):
        return {
            "id": row["id"],
            "title": row["title"],
            "text": (row["text"] or "")[:300],   # preview only
            "project": row["project"],
            "timestamp": row["timestamp"],
            "pinned": bool(row["pinned"]),
        }

    try:
        c.execute(
            '''
            SELECT n.id, n.title, n.text, n.project, n.timestamp, n.pinned
            FROM notes_fts f
            JOIN notes n ON f.rowid = n.id
            WHERE notes_fts MATCH ?
            ORDER BY n.pinned DESC, bm25(notes_fts)
            LIMIT ?
            ''',
            (fts_query, limit),
        )
        results = [_row_to_result(r) for r in c.fetchall()]
    except sqlite3.OperationalError as e:
        log.error(f"Notes FTS search error: {e}")
        q = f"%{query}%"
        c.execute(
            "SELECT id, title, text, project, timestamp, pinned FROM notes "
            "WHERE title LIKE ? OR text LIKE ? "
            "ORDER BY pinned DESC, timestamp DESC LIMIT ?",
            (q, q, limit),
        )
        results = [_row_to_result(r) for r in c.fetchall()]

    conn.close()
    return results


def add_task(text, priority="normal", due_date=None):
    log.debug(f"Adding task: {text[:50]} (priority={priority})")
    ts = datetime.now().isoformat()
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO tasks (text, priority, due_date, completed, timestamp) VALUES (?, ?, ?, ?, ?)",
              (text, priority, due_date, 0, ts))
    conn.commit()
    conn.close()
    return {"text": text, "priority": priority, "due_date": due_date, "completed": False, "timestamp": ts}

def get_tasks(priority=None):
    conn = get_db()
    c = conn.cursor()
    if priority:
        c.execute("SELECT * FROM tasks WHERE priority=? ORDER BY id ASC", (priority,))
    else:
        c.execute("SELECT * FROM tasks ORDER BY id ASC")
    rows = c.fetchall()
    tasks = []
    for r in rows:
        tasks.append({
            "id": r["id"],
            "text": r["text"],
            "priority": r["priority"],
            "due_date": r["due_date"],
            "completed": bool(r["completed"]),
            "timestamp": r["timestamp"]
        })
    conn.close()
    return tasks

def complete_task(task_id: int) -> bool:
    """Mark a task complete by its database id (not index)."""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE tasks SET completed=1 WHERE id=?", (task_id,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def delete_task(task_id: int) -> bool:
    """Permanently delete a task by its database id."""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def add_conversation(text, speaker=None, timestamp=None):
    kp = json.dumps(extract_key_points(text))
    ai = json.dumps(extract_action_items(text))
    ts = timestamp or datetime.now().isoformat()
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO conversations (text, speaker, key_points, action_items, timestamp) VALUES (?, ?, ?, ?, ?)",
              (text, speaker, kp, ai, ts))
    conn.commit()
    conn.close()
    return {"text": text, "speaker": speaker, "timestamp": ts}

def get_conversations():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM conversations ORDER BY id ASC")
    rows = c.fetchall()
    convs = []
    for r in rows:
        convs.append({
            "text": r["text"],
            "speaker": r["speaker"],
            "key_points": json.loads(r["key_points"]) if r["key_points"] else [],
            "action_items": json.loads(r["action_items"]) if r["action_items"] else [],
            "timestamp": r["timestamp"]
        })
    conn.close()
    return convs

def extract_key_points(text):
    return [s.strip() for s in text.split(".") if len(s.strip()) > 10]

# Word-boundary match so e.g. "document" or "adopt" don't false-positive on
# a bare "do"/"complete" substring check.
_ACTION_KEYWORDS = re.compile(
    r'\b(action item|to-?do|follow[- ]?up|need(?:s)? to|will do|assign(?:ed)?|complete|finish)\b',
    re.IGNORECASE,
)


def extract_action_items(text):
    if not text:
        return []
    items = []
    # Split on lines first (checklist/bullet-style notes), then sentences —
    # splitting on the literal ".\n" required a period immediately followed
    # by a newline with no space, which real note text essentially never
    # produces, so this used to come back empty almost every time.
    for line in text.split("\n"):
        for sentence in re.split(r'(?<=[.!?])\s+', line):
            sentence = sentence.strip(" -*•\t")
            if sentence and _ACTION_KEYWORDS.search(sentence):
                items.append(sentence)
    return items
