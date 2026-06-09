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

    conn.commit()
    conn.close()

init_db()

def add_note(text, title=None, key_points=None, action_items=None, timestamp=None, project=None, parent_id=None):
    log.info(f"Adding note: {title or 'Untitled'}")
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
    log.info("Note saved.")
    return {"id": note_id, "title": title, "text": text, "timestamp": ts, "project": project, "parent_id": parent_id}

def update_note(index, title, text, project=None, parent_id=None):
    # index is now the direct database ID
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE notes SET title=?, text=?, timestamp=?, project=?, parent_id=? WHERE id=?", (title, text, datetime.now().isoformat(), project, parent_id, index))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success

def delete_note(index):
    # index is now the direct database ID
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM notes WHERE id=?", (index,))
    success = c.rowcount > 0
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

def search_notes(query: str, limit: int = 20) -> list:
    """Case-insensitive substring search across note titles and bodies."""
    conn = get_db()
    c = conn.cursor()
    q = f"%{query}%"
    c.execute(
        "SELECT id, title, text, project, timestamp, pinned FROM notes "
        "WHERE title LIKE ? OR text LIKE ? "
        "ORDER BY pinned DESC, timestamp DESC LIMIT ?",
        (q, q, limit)
    )
    results = []
    for row in c.fetchall():
        results.append({
            "id": row["id"],
            "title": row["title"],
            "text": (row["text"] or "")[:300],   # preview only
            "project": row["project"],
            "timestamp": row["timestamp"],
            "pinned": bool(row["pinned"]),
        })
    conn.close()
    return results


def add_task(text, priority="normal", due_date=None):
    log.info(f"Adding task: {text[:50]} (priority={priority})")
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

def extract_action_items(text):
    items = []
    for line in text.split(".\n"):
        if any(word in line.lower() for word in ["action", "do", "complete", "finish"]):
            items.append(line.strip())
    return items
