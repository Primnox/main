# backend/reminder_manager.py
"""
Lightweight reminder engine with SQLite persistence.
- parse_reminder(text)     → {'delay_secs': int, 'message': str} | None
- add_reminder(msg, secs)  → queues + persists a reminder
- set_callback(cb)         → cb('reminder_triggered', {'text': msg}) when it fires
"""

import re
import time
import uuid
import threading
from logger import get_logger
from memory import get_db

log = get_logger("reminders")

_callback = None
_lock = threading.Lock()


# ── DB helpers ──────────────────────────────────────────────────────────────────

def init_reminders_table():
    conn = get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id          TEXT PRIMARY KEY,
                message     TEXT NOT NULL,
                fire_at     REAL NOT NULL,
                fired       INTEGER NOT NULL DEFAULT 0,
                fired_at    REAL,
                created_at  REAL NOT NULL
            )
        """)
        # Add fired_at column to existing databases that lack it
        try:
            conn.execute("ALTER TABLE reminders ADD COLUMN fired_at REAL")
        except Exception:
            pass  # column already exists
        conn.commit()
    finally:
        conn.close()


def _db_insert(reminder_id: str, message: str, fire_at: float):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO reminders (id, message, fire_at, fired, created_at) VALUES (?,?,?,0,?)",
            (reminder_id, message, fire_at, time.time())
        )
        conn.commit()
    finally:
        conn.close()


def _db_fire(reminder_id: str, fired_at: float):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE reminders SET fired=1, fired_at=? WHERE id=?",
            (fired_at, reminder_id)
        )
        conn.commit()
    finally:
        conn.close()


def _db_list_pending() -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, message, fire_at FROM reminders WHERE fired=0 ORDER BY fire_at"
        ).fetchall()
        return [{"id": r["id"], "message": r["message"], "fire_at": r["fire_at"]} for r in rows]
    finally:
        conn.close()


def _db_cancel_by_index(index: int) -> bool:
    """Cancel by 0-based position in fire_at order. Returns False if out of range."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id FROM reminders WHERE fired=0 ORDER BY fire_at"
        ).fetchall()
        if 0 <= index < len(rows):
            cursor = conn.execute(
                "UPDATE reminders SET fired=1, fired_at=? WHERE id=? AND fired=0",
                (time.time(), rows[index]["id"]),
            )
            conn.commit()
            return cursor.rowcount > 0
        return False
    finally:
        conn.close()


def _db_cancel_by_id(reminder_id: str) -> bool:
    """Cancel by stable row ID. Preferred over index-based cancel."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE reminders SET fired=1, fired_at=? WHERE id=? AND fired=0",
            (time.time(), reminder_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def _db_prune():
    """Remove reminders fired/cancelled more than an hour ago."""
    cutoff = time.time() - 3600
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM reminders WHERE fired=1 AND fired_at IS NOT NULL AND fired_at < ?",
            (cutoff,)
        )
        conn.commit()
    finally:
        conn.close()


# ── Public API ──────────────────────────────────────────────────────────────────

def set_callback(cb):
    global _callback
    _callback = cb


def parse_reminder(text: str) -> dict | None:
    """
    Detect natural-language reminder requests.
    Returns {'delay_secs': int, 'message': str}, or None.
    """
    t = text.lower().strip()

    PATTERNS = [
        (r'remind(?:\s+me)?\s+in\s+(\d+)\s*(?:min(?:ute)?s?)\s+(?:to\s+|about\s+)?(.+)', 60),
        (r'remind(?:\s+me)?\s+in\s+(\d+)\s*(?:hr?s?|hour?s?)\s+(?:to\s+|about\s+)?(.+)', 3600),
        (r'remind(?:\s+me)?\s+in\s+(\d+)\s*(?:sec(?:ond)?s?)\s+(?:to\s+|about\s+)?(.+)', 1),
        (r'set\s+(?:a\s+)?reminder\s+(?:for\s+)?(\d+)\s*(?:min(?:ute)?s?)\s+(?:to\s+|for\s+|about\s+)?(.+)', 60),
        (r'set\s+(?:a\s+)?reminder\s+(?:for\s+)?(\d+)\s*(?:hr?s?|hour?s?)\s+(?:to\s+|for\s+|about\s+)?(.+)', 3600),
    ]

    for pattern, multiplier in PATTERNS:
        m = re.search(pattern, t)
        if m:
            amount = int(m.group(1))
            message = m.group(2).strip().rstrip('.')
            if not message:
                message = "reminder"
            delay = amount * multiplier
            log.info(f"Parsed reminder: '{message}' in {delay}s")
            return {"delay_secs": delay, "message": message}

    return None


def add_reminder(message: str, delay_secs: int) -> None:
    if delay_secs <= 0:
        log.warning(f"add_reminder: ignoring non-positive delay {delay_secs}")
        return
    rid = str(uuid.uuid4())
    fire_at = time.time() + delay_secs
    with _lock:
        _db_insert(rid, message, fire_at)
    log.info(f"Reminder persisted: '{message}' in {delay_secs}s (id={rid})")


def cancel_reminder(index: int) -> bool:
    """Cancel by 0-based position. Prefer cancel_reminder_by_id for stability."""
    with _lock:
        ok = _db_cancel_by_index(index)
    if ok:
        log.info(f"Reminder at index {index} cancelled")
    return ok


def cancel_reminder_by_id(reminder_id: str) -> bool:
    """Cancel by stable row ID — not affected by concurrent firings."""
    with _lock:
        ok = _db_cancel_by_id(reminder_id)
    if ok:
        log.info(f"Reminder {reminder_id} cancelled by id")
    return ok


def list_reminders() -> list[dict]:
    """Return pending (unfired) reminders with seconds remaining and id."""
    now = time.time()
    with _lock:
        rows = _db_list_pending()
    return [
        {
            "id": r["id"],
            "message": r["message"],
            "seconds_remaining": max(0, int(r["fire_at"] - now)),
        }
        for r in rows
    ]


# ── Background loop ─────────────────────────────────────────────────────────────
# FIX: collect fired messages INSIDE the lock, call callbacks OUTSIDE the lock
# to prevent deadlock if a callback re-enters add_reminder/list_reminders.

def _loop():
    try:
        init_reminders_table()
    except Exception as e:
        log.error(f"Could not init reminders table: {e}")

    while True:
        now = time.time()
        fired_messages: list[str] = []

        with _lock:
            try:
                pending = _db_list_pending()
                for r in pending:
                    if now >= r["fire_at"]:
                        _db_fire(r["id"], now)
                        fired_messages.append(r["message"])
                        log.info(f"Reminder fired: '{r['message']}'")
                _db_prune()
            except Exception as e:
                log.error(f"Reminder loop DB error: {e}")

        # Invoke callbacks outside the lock so re-entrant calls don't deadlock
        if _callback and fired_messages:
            for msg in fired_messages:
                try:
                    _callback("reminder_triggered", {"text": msg})
                except Exception as e:
                    log.error(f"Reminder callback error: {e}")

        time.sleep(10)


threading.Thread(target=_loop, daemon=True, name="reminder-loop").start()
