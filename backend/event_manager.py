"""Local calendar event storage — uses memory.db via memory.get_db()."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from memory import get_db
from logger import get_logger

log = get_logger("events")


def init_events_table() -> None:
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            start_dt    TEXT NOT NULL,
            end_dt      TEXT NOT NULL,
            all_day     INTEGER DEFAULT 0,
            color       TEXT    DEFAULT '#6366f1',
            location    TEXT    DEFAULT '',
            description TEXT    DEFAULT '',
            recurrence  TEXT    DEFAULT 'none',
            calendar    TEXT    DEFAULT 'Personal',
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        )
    """)
    # Optional single link to a note (e.g. meeting prep doc, follow-up notes).
    try:
        conn.execute("ALTER TABLE events ADD COLUMN note_id INTEGER")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def list_events(start_iso: Optional[str] = None, end_iso: Optional[str] = None) -> list[dict]:
    conn = get_db()
    c = conn.cursor()
    if start_iso and end_iso:
        c.execute(
            "SELECT * FROM events WHERE start_dt >= ? AND start_dt <= ? ORDER BY start_dt",
            (start_iso, end_iso),
        )
    else:
        c.execute("SELECT * FROM events ORDER BY start_dt")
    rows = c.fetchall()
    return [dict(r) for r in rows]


def create_event(data: dict) -> dict:
    now = datetime.now().isoformat()
    ev = {
        "id":          str(uuid.uuid4()),
        "title":       data["title"],
        "start_dt":    data["start_dt"],
        "end_dt":      data["end_dt"],
        "all_day":     int(bool(data.get("all_day", False))),
        "color":       data.get("color", "#6366f1") or "#6366f1",
        "location":    data.get("location", "") or "",
        "description": data.get("description", "") or "",
        "recurrence":  data.get("recurrence", "none") or "none",
        "calendar":    data.get("calendar", "Personal") or "Personal",
        "note_id":     data.get("note_id"),
        "created_at":  now,
        "updated_at":  now,
    }
    conn = get_db()
    conn.execute(
        """INSERT INTO events
           (id, title, start_dt, end_dt, all_day, color, location, description,
            recurrence, calendar, note_id, created_at, updated_at)
           VALUES (:id, :title, :start_dt, :end_dt, :all_day, :color, :location,
                   :description, :recurrence, :calendar, :note_id, :created_at, :updated_at)""",
        ev,
    )
    conn.commit()
    ev["all_day"] = bool(ev["all_day"])
    log.info(f"Created event: {ev['title']} @ {ev['start_dt']}")
    return ev


def update_event(event_id: str, data: dict) -> Optional[dict]:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    row = c.fetchone()
    if not row:
        return None
    ex = dict(row)
    now = datetime.now().isoformat()
    up = {
        "id":          event_id,
        "title":       data.get("title",       ex["title"]),
        "start_dt":    data.get("start_dt",    ex["start_dt"]),
        "end_dt":      data.get("end_dt",      ex["end_dt"]),
        "all_day":     int(bool(data.get("all_day", ex["all_day"]))),
        "color":       data.get("color",       ex["color"]) or "#6366f1",
        "location":    data.get("location",    ex["location"]) or "",
        "description": data.get("description", ex["description"]) or "",
        "recurrence":  data.get("recurrence",  ex["recurrence"]) or "none",
        "calendar":    data.get("calendar",    ex["calendar"]) or "Personal",
        "note_id":     data.get("note_id",     ex.get("note_id")),
        "created_at":  ex["created_at"],
        "updated_at":  now,
    }
    conn.execute(
        """UPDATE events
           SET title=:title, start_dt=:start_dt, end_dt=:end_dt, all_day=:all_day,
               color=:color, location=:location, description=:description,
               recurrence=:recurrence, calendar=:calendar, note_id=:note_id, updated_at=:updated_at
           WHERE id=:id""",
        up,
    )
    conn.commit()
    up["all_day"] = bool(up["all_day"])
    log.info(f"Updated event {event_id}: {up['title']}")
    return up


def delete_event(event_id: str) -> bool:
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE id = ?", (event_id,))
    affected = c.rowcount
    conn.commit()
    return bool(affected)
