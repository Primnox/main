import sqlite3
import os
import json
import threading
from contextlib import closing
from pathlib import Path
from logger import get_logger

log = get_logger("database")

def get_appdata_dir():
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / "primnox_extension"
    else:
        base = Path.home() / ".primnox_extension"
    base.mkdir(parents=True, exist_ok=True)
    return base

DB_PATH = get_appdata_dir() / "primnox.db"
_db_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with _db_lock:
        with closing(get_db()) as conn, closing(conn.cursor()) as c:
            # ---------------- Chat Tables ----------------
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

            c.execute('SELECT COUNT(*) FROM folders')
            if c.fetchone()[0] == 0:
                c.execute("INSERT OR IGNORE INTO folders (id, title) VALUES ('f_research', 'Research')")
                c.execute("INSERT OR IGNORE INTO folders (id, title) VALUES ('f_projects', 'Projects')")
                c.execute("INSERT OR IGNORE INTO folders (id, title) VALUES ('f_archive', 'Archive')")

            # ---------------- Settings Table ----------------
            c.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')

            conn.commit()

def run_migrations():
    with _db_lock:
        # Migrate old chat.db if it exists in backend
        old_chat = Path(__file__).parent / "chat.db"
        if old_chat.exists() and not old_chat.name.endswith('.bak'):
            try:
                with closing(get_db()) as conn, closing(conn.cursor()) as c:
                    c.execute("ATTACH DATABASE ? AS old_db", (str(old_chat),))
                    c.execute("INSERT OR IGNORE INTO folders SELECT * FROM old_db.folders")
                    c.execute("INSERT OR IGNORE INTO sessions SELECT * FROM old_db.sessions")
                    c.execute("INSERT OR IGNORE INTO messages SELECT * FROM old_db.messages")
                    conn.commit()
                    c.execute("DETACH DATABASE old_db")
                
                # Move to backup
                old_chat.rename(old_chat.with_suffix('.db.bak'))
                log.info("Migrated old chat.db to primnox.db")
            except Exception as e:
                log.error(f"Failed to migrate old chat.db: {e}")

        # Migrate old settings.json if it exists in AppData
        settings_json = get_appdata_dir() / "settings.json"
        if settings_json.exists() and not settings_json.name.endswith('.bak'):
            try:
                with open(settings_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                with closing(get_db()) as conn, closing(conn.cursor()) as c:
                    c.execute('''
                        INSERT INTO settings (key, value) VALUES (?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    ''', ('app_settings', json.dumps(data)))
                    conn.commit()
                
                settings_json.rename(settings_json.with_suffix('.json.bak'))
                log.info("Migrated settings.json to primnox.db")
            except Exception as e:
                log.error(f"Failed to migrate settings.json: {e}")

# Initialize and migrate immediately upon importing
init_db()
run_migrations()

# ==========================================
# Chat Interface
# ==========================================
def db_get_all_sessions():
    with _db_lock:
        with closing(get_db()) as conn, closing(conn.cursor()) as c:
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
            return {"sessions": sessions, "folders": folders}

def db_create_session(new_id, title, date):
    with _db_lock:
        with closing(get_db()) as conn, closing(conn.cursor()) as c:
            c.execute('''
                INSERT INTO sessions (id, title, date, folder_id, is_pinned)
                VALUES (?, ?, ?, ?, ?)
            ''', (new_id, title, date, None, 0))
            conn.commit()

def db_get_latest_session_id():
    with _db_lock:
        with closing(get_db()) as conn, closing(conn.cursor()) as c:
            c.execute('SELECT id FROM sessions ORDER BY date DESC LIMIT 1')
            row = c.fetchone()
            return row["id"] if row else None

def db_get_session_messages(session_id):
    with _db_lock:
        with closing(get_db()) as conn, closing(conn.cursor()) as c:
            c.execute('SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC', (session_id,))
            messages = []
            for row in c.fetchall():
                messages.append({
                    "text": row["text"],
                    "speaker": row["speaker"],
                    "timestamp": row["timestamp"]
                })
            return messages

def db_append_message(msg_id, session_id, text, speaker, timestamp):
    with _db_lock:
        with closing(get_db()) as conn, closing(conn.cursor()) as c:
            c.execute('''
                INSERT INTO messages (id, session_id, text, speaker, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (msg_id, session_id, text, speaker, timestamp))

            c.execute('SELECT COUNT(*) FROM messages WHERE session_id = ?', (session_id,))
            if c.fetchone()[0] == 1 and speaker == "User":
                title = text[:30] + "..." if len(text) > 30 else text
                c.execute('UPDATE sessions SET title = ? WHERE id = ?', (title, session_id))

            conn.commit()

def db_update_session(session_id, title=None, is_pinned=None, folder_id=None):
    with _db_lock:
        with closing(get_db()) as conn, closing(conn.cursor()) as c:
            if title is not None:
                c.execute('UPDATE sessions SET title = ? WHERE id = ?', (title, session_id))
            if is_pinned is not None:
                c.execute('UPDATE sessions SET is_pinned = ? WHERE id = ?', (1 if is_pinned else 0, session_id))
            if folder_id is not None:
                folder_val = folder_id if folder_id != "none" else None
                c.execute('UPDATE sessions SET folder_id = ? WHERE id = ?', (folder_val, session_id))
            conn.commit()

def db_delete_session(session_id):
    with _db_lock:
        with closing(get_db()) as conn, closing(conn.cursor()) as c:
            c.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
            c.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
            conn.commit()

# ==========================================
# Settings Interface
# ==========================================
def db_load_settings():
    with _db_lock:
        with closing(get_db()) as conn, closing(conn.cursor()) as c:
            c.execute('SELECT value FROM settings WHERE key = ?', ('app_settings',))
            row = c.fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return {}
            return {}

def db_save_settings(settings_dict):
    with _db_lock:
        with closing(get_db()) as conn, closing(conn.cursor()) as c:
            c.execute('''
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            ''', ('app_settings', json.dumps(settings_dict)))
            conn.commit()
