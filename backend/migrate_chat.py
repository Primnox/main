import sqlite3
import json
import os
import uuid
import datetime
from pathlib import Path

# Resolve paths relative to this file. These were absolute paths on the
# original author's Windows machine, which leaked a username and broke the
# script for everyone else.
_BACKEND_DIR = Path(__file__).resolve().parent

JSON_FILE = str(_BACKEND_DIR / "chat_sessions.json")
DB_FILE = str(_BACKEND_DIR / "chat.db")

def get_current_time():
    return datetime.datetime.now().isoformat()

def migrate():
    print("Starting migration...")
    if not os.path.exists(JSON_FILE):
        print(f"{JSON_FILE} not found. Creating empty DB.")
        db_data = {"sessions": [], "folders": [], "messages": {}}
    else:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            db_data = json.load(f)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Create tables
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

    # Insert folders
    for f in db_data.get("folders", []):
        c.execute('INSERT OR IGNORE INTO folders (id, title) VALUES (?, ?)', (f["id"], f["title"]))

    # Default folders if empty
    if not db_data.get("folders"):
        c.execute("INSERT OR IGNORE INTO folders (id, title) VALUES ('f_research', 'Research')")
        c.execute("INSERT OR IGNORE INTO folders (id, title) VALUES ('f_projects', 'Projects')")

    # Insert sessions
    for s in db_data.get("sessions", []):
        c.execute('''
            INSERT OR IGNORE INTO sessions (id, title, date, folder_id, is_pinned) 
            VALUES (?, ?, ?, ?, ?)
        ''', (
            s["id"], 
            s.get("title", "Untitled"), 
            s.get("date", get_current_time()), 
            s.get("folderId"), 
            1 if s.get("isPinned") else 0
        ))

    # Insert messages
    messages = db_data.get("messages", {})
    for session_id, msgs in messages.items():
        for m in msgs:
            msg_id = str(uuid.uuid4())
            c.execute('''
                INSERT OR IGNORE INTO messages (id, session_id, text, speaker, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                msg_id,
                session_id,
                m.get("text", ""),
                m.get("speaker", "Unknown"),
                m.get("timestamp", get_current_time())
            ))

    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == '__main__':
    migrate()
