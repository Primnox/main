# backend/reminder_manager.py
"""
Lightweight reminder engine.
- parse_reminder(text)      → {'delay_secs': int, 'message': str} | None
- add_reminder(msg, secs)   → queues a reminder
- set_callback(cb)          → cb('reminder_triggered', {'text': msg}) when it fires

The background loop runs as a daemon thread from import time — no explicit start needed.
"""

import re
import time
import threading
from logger import get_logger

log = get_logger("reminders")

_reminders: list[dict] = []   # {message, fire_at, fired}
_callback = None
_lock = threading.Lock()


# ── Public API ─────────────────────────────────────────────────────────────────

def set_callback(cb):
    global _callback
    _callback = cb


def parse_reminder(text: str) -> dict | None:
    """
    Detect natural-language reminder requests and return
    {'delay_secs': int, 'message': str}, or None if not a reminder.

    Supports:
      "remind me in 30 minutes to take a break"
      "set a reminder for 2 hours to check the build"
      "remind me in 10 mins to drink water"
      "set reminder 5 minutes stand up"
    """
    t = text.lower().strip()

    PATTERNS = [
        # remind me in N min(s) [to] ...
        (r'remind(?:\s+me)?\s+in\s+(\d+)\s*(?:min(?:ute)?s?)\s+(?:to\s+|about\s+)?(.+)', 60),
        # remind me in N hour(s) [to] ...
        (r'remind(?:\s+me)?\s+in\s+(\d+)\s*(?:hr?s?|hour?s?)\s+(?:to\s+|about\s+)?(.+)', 3600),
        # remind me in N second(s) [to] ...
        (r'remind(?:\s+me)?\s+in\s+(\d+)\s*(?:sec(?:ond)?s?)\s+(?:to\s+|about\s+)?(.+)', 1),
        # set a reminder for N min(s) [to/for] ...
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
    with _lock:
        _reminders.append({
            "message": message,
            "fire_at": time.time() + delay_secs,
            "fired": False,
        })
    log.info(f"Reminder queued: '{message}' in {delay_secs}s")


def cancel_reminder(index: int) -> bool:
    """Cancel a pending reminder by its position in the pending list (0-based)."""
    now = time.time()
    with _lock:
        pending = [r for r in _reminders if not r["fired"]]
        if 0 <= index < len(pending):
            pending[index]["fired"] = True
            log.info(f"Reminder cancelled: '{pending[index]['message']}'")
            return True
    return False


def list_reminders() -> list[dict]:
    """Return pending (unfired) reminders with seconds remaining."""
    now = time.time()
    with _lock:
        return [
            {
                "message": r["message"],
                "seconds_remaining": max(0, int(r["fire_at"] - now)),
            }
            for r in _reminders
            if not r["fired"]
        ]


# ── Background loop ────────────────────────────────────────────────────────────

def _loop():
    while True:
        now = time.time()
        fired_any = False
        with _lock:
            for r in _reminders:
                if not r["fired"] and now >= r["fire_at"]:
                    r["fired"] = True
                    fired_any = True
                    if _callback:
                        try:
                            _callback("reminder_triggered", {"text": r["message"]})
                            log.info(f"Reminder fired: '{r['message']}'")
                        except Exception as e:
                            log.error(f"Reminder callback error: {e}")
            # Prune reminders fired more than an hour ago
            _reminders[:] = [
                r for r in _reminders
                if not r["fired"] or (now - r["fire_at"]) < 3600
            ]
        time.sleep(10)


threading.Thread(target=_loop, daemon=True, name="reminder-loop").start()
