import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path("C:/Users/aniketh/Projects/Primnox/backend/memory.db")
NOTES_PATH = Path("C:/Users/aniketh/Projects/Primnox/backend/notes.json")
TASKS_PATH = Path("C:/Users/aniketh/Projects/Primnox/backend/tasks.json")
CONV_PATH = Path("C:/Users/aniketh/Projects/Primnox/backend/conversations.json")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    text TEXT,
    key_points TEXT,
    action_items TEXT,
    timestamp TEXT,
    project TEXT
)''')

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

# Migrate notes
if NOTES_PATH.exists():
    try:
        with open(NOTES_PATH, "r", encoding="utf-8") as f:
            notes = json.load(f)
            for n in notes:
                kp = json.dumps(n.get("key_points", []))
                ai = json.dumps(n.get("action_items", []))
                c.execute("INSERT INTO notes (title, text, key_points, action_items, timestamp, project) VALUES (?, ?, ?, ?, ?, ?)",
                          (n.get("title"), n.get("text"), kp, ai, n.get("timestamp"), n.get("project")))
        NOTES_PATH.rename(NOTES_PATH.with_suffix('.json.bak'))
    except Exception as e:
        print("Notes migration error:", e)

# Migrate tasks
if TASKS_PATH.exists():
    try:
        with open(TASKS_PATH, "r", encoding="utf-8") as f:
            tasks = json.load(f)
            for t in tasks:
                c.execute("INSERT INTO tasks (text, priority, due_date, completed, timestamp) VALUES (?, ?, ?, ?, ?)",
                          (t.get("text"), t.get("priority"), t.get("due_date"), 1 if t.get("completed") else 0, t.get("timestamp")))
        TASKS_PATH.rename(TASKS_PATH.with_suffix('.json.bak'))
    except Exception as e:
        print("Tasks migration error:", e)

# Migrate conversations
if CONV_PATH.exists():
    try:
        with open(CONV_PATH, "r", encoding="utf-8") as f:
            convs = json.load(f)
            for cv in convs:
                kp = json.dumps(cv.get("key_points", []))
                ai = json.dumps(cv.get("action_items", []))
                c.execute("INSERT INTO conversations (text, speaker, key_points, action_items, timestamp) VALUES (?, ?, ?, ?, ?)",
                          (cv.get("text"), cv.get("speaker"), kp, ai, cv.get("timestamp")))
        CONV_PATH.rename(CONV_PATH.with_suffix('.json.bak'))
    except Exception as e:
        print("Conversations migration error:", e)

conn.commit()
conn.close()
print("Migration completed.")
