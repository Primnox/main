"""Once-a-day summary: today's calendar, open tasks, and the last day and a
half of memory activity, folded into one short brief — one LLM call per
calendar day, not a continuous "subconscious" polling loop.
"""
import threading
import time
from datetime import datetime, timedelta

from logger import get_logger
from settings_manager import load_settings, save_settings

log = get_logger("daily_digest")


def _gather_context() -> dict:
    from memory import list_memories
    from notes_manager import get_tasks

    cutoff = (datetime.now() - timedelta(hours=36)).isoformat()
    recent_memories = [m for m in list_memories() if m.get("timestamp", "") >= cutoff][:20]
    tasks = [t for t in get_tasks() if not t.get("completed")][:10]

    events = []
    try:
        from skills.calendar_skill import CalendarIslandSkill
        events = CalendarIslandSkill()._fetch_events()
    except Exception as e:
        log.debug(f"Calendar unavailable for digest: {e}")

    return {"memories": recent_memories, "tasks": tasks, "events": events}


def _build_context_block(ctx: dict) -> str:
    lines = []
    if ctx["events"]:
        lines.append("EVENTS TODAY:")
        for ev in ctx["events"][:10]:
            try:
                lines.append(f"- {ev.title} at {ev.start.astimezone().strftime('%I:%M %p')}")
            except Exception:
                continue
    if ctx["tasks"]:
        lines.append("\nOPEN TASKS:")
        for t in ctx["tasks"]:
            lines.append(f"- {t['text']} (priority: {t.get('priority', 'normal')})")
    if ctx["memories"]:
        lines.append("\nRECENT ACTIVITY:")
        for m in ctx["memories"]:
            lines.append(f"- {m['text']}")
    return "\n".join(lines)


def generate_daily_digest() -> str | None:
    """Build today's digest, save it as a note, and return the text — or
    None if there's nothing worth summarizing (fresh install, quiet day)."""
    ctx = _gather_context()
    if not ctx["memories"] and not ctx["tasks"] and not ctx["events"]:
        return None

    context_block = _build_context_block(ctx)

    try:
        from brain import think
        resp = think(
            "Write a short daily brief for the user based on the data below. "
            "2-4 sentences, conversational, no headers or bullet points. Mention "
            "what's on today, anything due, and one relevant thing from recent "
            "activity if it's genuinely useful. Skip any section that's empty — "
            "don't say 'no events' or similar.\n\n" + context_block,
            system_override=(
                "You are writing a short daily brief for the user. Be direct and "
                "useful, not falsely upbeat. No preamble, no sign-off."
            ),
        )
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        log.warning(f"Daily digest LLM call failed: {e}")
        return None

    if not text:
        return None

    try:
        from notes_manager import add_note
        add_note(text, title=f"Daily Brief: {datetime.now().strftime('%Y-%m-%d')}")
    except Exception as e:
        log.warning(f"Could not save daily digest note: {e}")

    return text


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def maybe_run_daily_digest(broadcast_callback=None) -> bool:
    """Generate today's digest if it hasn't run yet today. Persists the last
    generated date in settings so restarts don't regenerate the same day's
    digest, and so a day isn't skipped just because the app wasn't running
    exactly 24h after the last run. Returns True if a digest was generated."""
    settings = load_settings()
    today = _today_str()
    if settings.get("last_daily_digest_date") == today:
        return False

    text = generate_daily_digest()
    settings = load_settings()  # re-read in case something else wrote settings meanwhile
    settings["last_daily_digest_date"] = today
    save_settings(settings)

    if text and broadcast_callback:
        try:
            broadcast_callback("daily_digest", {"text": text, "date": today})
        except Exception as e:
            log.warning(f"Daily digest broadcast failed: {e}")

    return bool(text)


_digest_thread: threading.Thread | None = None
_stop_event = threading.Event()


def start_daily_digest_scheduler(broadcast_callback=None, check_interval_hours: float = 1.0):
    """Check once an hour whether today's digest has run yet; generating it
    is idempotent per calendar day (see maybe_run_daily_digest), so an hourly
    check just means it fires within an hour of the app being open past
    midnight rather than needing to be running at a specific instant."""
    global _digest_thread

    def _loop():
        time.sleep(10)  # small initial delay so the server is ready
        while not _stop_event.is_set():
            try:
                maybe_run_daily_digest(broadcast_callback)
            except Exception as e:
                log.error(f"Daily digest check failed: {e}")
            if _stop_event.wait(check_interval_hours * 3600):
                break

    _digest_thread = threading.Thread(target=_loop, daemon=True, name="daily-digest")
    _digest_thread.start()
    log.info("Daily digest scheduler started (checks hourly, generates once per calendar day)")


def stop_daily_digest_scheduler():
    _stop_event.set()
