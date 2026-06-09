import sqlite3
import os
import uuid
import datetime
from pathlib import Path

def _get_appdata_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "primnox_extension" if appdata else Path.home() / ".primnox_extension"
    base.mkdir(parents=True, exist_ok=True)
    return base

DB_FILE = str(_get_appdata_dir() / "chat.db")

def get_current_time():
    return datetime.datetime.now().isoformat()

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_chat_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS folders (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            folder_id TEXT,
            is_pinned INTEGER DEFAULT 0,
            FOREIGN KEY(folder_id) REFERENCES folders(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            text TEXT NOT NULL,
            speaker TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
    ''')
    
    # Check if folders exist, if not create default
    c.execute('SELECT COUNT(*) FROM folders')
    c.execute("INSERT OR IGNORE INTO folders (id, title) VALUES ('f_research', 'Research')")
    c.execute("INSERT OR IGNORE INTO folders (id, title) VALUES ('f_projects', 'Projects')")
    c.execute("INSERT OR IGNORE INTO folders (id, title) VALUES ('f_archive', 'Archive')")
        
    conn.commit()
    conn.close()

def get_all_sessions():
    init_chat_db()
    conn = get_db()
    c = conn.cursor()
    
    # Get all sessions
    c.execute('SELECT * FROM sessions ORDER BY date DESC')
    sessions = []
    for row in c.fetchall():
        sessions.append({
            "id": row["id"],
            "title": row["title"],
            "date": row["date"],
            "folderId": row["folder_id"],
            "isPinned": bool(row["is_pinned"])
        })
        
    # Get folder counts
    c.execute('''
        SELECT f.id, f.title, COUNT(s.id) as count
        FROM folders f
        LEFT JOIN sessions s ON f.id = s.folder_id
        GROUP BY f.id, f.title
    ''')
    folders = []
    for row in c.fetchall():
        folders.append({
            "id": row["id"],
            "title": row["title"],
            "count": row["count"]
        })
        
    conn.close()
    return {
        "sessions": sessions,
        "folders": folders
    }

def create_session(title="New Chat"):
    init_chat_db()
    conn = get_db()
    c = conn.cursor()
    
    new_id = str(uuid.uuid4())
    date = get_current_time()
    
    c.execute('''
        INSERT INTO sessions (id, title, date, folder_id, is_pinned)
        VALUES (?, ?, ?, ?, ?)
    ''', (new_id, title, date, None, 0))
    
    conn.commit()
    conn.close()
    
    return {
        "id": new_id,
        "title": title,
        "date": date,
        "folderId": None,
        "isPinned": False
    }

def get_session_messages(session_id):
    init_chat_db()
    
    if session_id == "current":
        # Get most recent session, or create one
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id FROM sessions ORDER BY date DESC LIMIT 1')
        row = c.fetchone()
        if row:
            session_id = row["id"]
        else:
            session = create_session()
            session_id = session["id"]
        conn.close()
            
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC', (session_id,))
    messages = []
    for row in c.fetchall():
        messages.append({
            "text": row["text"],
            "speaker": row["speaker"],
            "timestamp": row["timestamp"]
        })
    conn.close()
    return messages

def append_message_to_session(session_id, text, speaker):
    init_chat_db()
    
    if session_id == "current":
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id FROM sessions ORDER BY date DESC LIMIT 1')
        row = c.fetchone()
        if row:
            session_id = row["id"]
        else:
            session = create_session()
            session_id = session["id"]
        conn.close()
        
    msg_id = str(uuid.uuid4())
    timestamp = get_current_time()
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages (id, session_id, text, speaker, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (msg_id, session_id, text, speaker, timestamp))
    
    # Check if this is the first user message to update title
    c.execute('SELECT COUNT(*) FROM messages WHERE session_id = ?', (session_id,))
    if c.fetchone()[0] == 1 and speaker == "User":
        title = text[:30] + "..." if len(text) > 30 else text
        c.execute('UPDATE sessions SET title = ? WHERE id = ?', (title, session_id))
        
    conn.commit()
    conn.close()
    
    return {
        "text": text,
        "speaker": speaker,
        "timestamp": timestamp
    }

def get_session(session_id: str) -> dict | None:
    """Return session metadata dict or None if not found."""
    init_chat_db()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, title, date, folder_id, is_pinned FROM sessions WHERE id = ?', (session_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row["id"], "title": row["title"], "date": row["date"],
            "folder_id": row["folder_id"], "is_pinned": bool(row["is_pinned"])}

def update_session(session_id, title=None, is_pinned=None, folder_id=None):
    init_chat_db()
    conn = get_db()
    c = conn.cursor()
    
    if title is not None:
        c.execute('UPDATE sessions SET title = ? WHERE id = ?', (title, session_id))
    if is_pinned is not None:
        c.execute('UPDATE sessions SET is_pinned = ? WHERE id = ?', (1 if is_pinned else 0, session_id))
    if folder_id is not None:
        folder_val = folder_id if folder_id != "none" else None
        c.execute('UPDATE sessions SET folder_id = ? WHERE id = ?', (folder_val, session_id))
        
    conn.commit()
    conn.close()
    return True

def create_folder(title: str) -> dict:
    """Create a new chat folder and return it."""
    init_chat_db()
    folder_id = f"f_{str(uuid.uuid4())[:8]}"
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO folders (id, title) VALUES (?, ?)", (folder_id, title))
    conn.commit()
    conn.close()
    return {"id": folder_id, "title": title, "count": 0}


def delete_folder(folder_id: str) -> bool:
    """Delete a folder and unassign any chats in it."""
    init_chat_db()
    conn = get_db()
    c = conn.cursor()
    # Move chats out of the deleted folder first
    c.execute("UPDATE sessions SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
    c.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def delete_session(session_id):
    init_chat_db()
    conn = get_db()
    c = conn.cursor()
    # Delete session (messages will cascade delete due to ON DELETE CASCADE)
    c.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
    c.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()
    
    try:
        from memory import delete_memories_by_session
        delete_memories_by_session(session_id)
    except Exception as e:
        print(f"Failed to delete memories for session {session_id}: {e}")
        
    return True

