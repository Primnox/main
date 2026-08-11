"""
Cleanup Manager — enforces data-retention settings.

Runs on startup and every 24 hours. Deletes:
  • Memories older than `memory_auto_delete_days` days
  • Meeting folders older than `meeting_retention_days` days
    (uses screenshot_retention setting, default 10)
  • Orphaned TTS audio files older than 1 hour

All deletion is logged. Settings of 0 mean "keep forever".
"""
from __future__ import annotations

import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from logger import get_logger
from settings_manager import load_settings

log = get_logger("cleanup")

# ── Meetings ───────────────────────────────────────────────────────────────────

def _meetings_dir() -> Path:
    return Path.home() / "Documents" / "Primnox" / "Meetings"


def cleanup_meetings(retention_days: int) -> int:
    """Delete meeting folders older than retention_days. Returns count deleted."""
    if retention_days <= 0:
        return 0
    base = _meetings_dir()
    if not base.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=retention_days)
    deleted = 0
    for folder in base.iterdir():
        if not folder.is_dir():
            continue
        try:
            mtime = datetime.fromtimestamp(folder.stat().st_mtime)
            if mtime < cutoff:
                shutil.rmtree(folder)
                log.info(f"Deleted old meeting folder: {folder.name} (modified {mtime.date()})")
                deleted += 1
        except Exception as e:
            log.warning(f"Could not delete {folder}: {e}")
    return deleted


# ── Memories ───────────────────────────────────────────────────────────────────

def cleanup_memories(retention_days: int) -> int:
    """Delete memory rows older than retention_days. Returns count deleted.

    Timestamps in the DB are ISO-8601 strings; SQLite lexicographic comparison
    on them works correctly as long as the format is consistent (it is —
    datetime.now().isoformat() produces sortable strings).
    """
    if retention_days <= 0:
        return 0
    try:
        import sqlite3
        from memory import DB_PATH          # reuse the same DB path
        cutoff_iso = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM memories WHERE timestamp < ?", (cutoff_iso,))
            count = c.fetchone()[0]
            if count:
                c.execute("DELETE FROM memories WHERE timestamp < ?", (cutoff_iso,))
                conn.commit()
                log.info(f"Deleted {count} memories older than {retention_days} days")
            return count
    except Exception as e:
        log.warning(f"Memory cleanup failed: {e}")
        return 0


# ── TTS cache ──────────────────────────────────────────────────────────────────

def cleanup_tts(max_age_hours: int = 1) -> int:
    """Delete stale TTS .mp3/.wav files. Returns count deleted."""
    try:
        import tempfile, os
        tmp   = Path(tempfile.gettempdir())
        cutoff = time.time() - max_age_hours * 3600
        deleted = 0
        for f in tmp.glob("primnox_tts_*.mp3"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
            except Exception:
                pass
        for f in tmp.glob("primnox_tts_*.wav"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
            except Exception:
                pass
        if deleted:
            log.debug(f"Deleted {deleted} stale TTS files")
        return deleted
    except Exception as e:
        log.debug(f"TTS cleanup error: {e}")
        return 0


def cleanup_uploads(max_age_hours: int = 24) -> int:
    """Delete orphaned chat-upload temp files (images/attachments saved by
    /message but never tracked or cleaned up afterwards). Returns count deleted."""
    try:
        import tempfile
        tmp = Path(tempfile.gettempdir())
        cutoff = time.time() - max_age_hours * 3600
        deleted = 0
        for f in tmp.glob("primnox_upload_*"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
            except Exception:
                pass
        if deleted:
            log.debug(f"Deleted {deleted} orphaned upload temp files")
        return deleted
    except Exception as e:
        log.debug(f"Upload cleanup error: {e}")
        return 0


# ── Full pass ──────────────────────────────────────────────────────────────────

def compress_memories_pass() -> int:
    """Compress memories older than 7 days into weekly summaries. Returns originals replaced."""
    try:
        from memory import compress_old_memories
        return compress_old_memories(compress_after_days=7)
    except Exception as e:
        log.warning(f"Memory compression pass failed: {e}")
        return 0


def mark_stale_memories_pass(memory_days: int) -> int:
    """Flag memories past the retention cutoff as stale (read-hidden, not deleted)."""
    try:
        from memory import mark_stale_memories
        return mark_stale_memories(stale_after_days=memory_days)
    except Exception as e:
        log.warning(f"Stale-memory pass failed: {e}")
        return 0


def render_memory_mirror_pass() -> int:
    """Regenerate the Markdown memory mirror. Returns topic files written.

    Runs after mark_stale_memories_pass so the mirror never shows a memory
    the rest of the app already treats as stale.
    """
    try:
        from memory_mirror import render_memory_mirror
        return render_memory_mirror()
    except Exception as e:
        log.warning(f"Memory mirror render failed: {e}")
        return 0


def run_cleanup() -> dict:
    """Run all cleanup tasks. Returns summary dict."""
    settings = load_settings()

    memory_days  = int(settings.get("memory_auto_delete_days", 30))
    # meeting retention defaults to 0 (never auto-delete) until user explicitly sets it
    meeting_days = int(settings.get("meeting_retention_days", 0))

    # Compress old memories into weekly digests — no auto-deletion, user manages manually
    memories_compressed = compress_memories_pass()
    memories_marked_stale = mark_stale_memories_pass(memory_days)
    memory_mirror_topics = render_memory_mirror_pass()

    results = {
        "memories_compressed": memories_compressed,
        "memories_marked_stale": memories_marked_stale,
        "memory_mirror_topics": memory_mirror_topics,
        "meetings_deleted":    cleanup_meetings(meeting_days),
        "tts_deleted":         cleanup_tts(max_age_hours=1),
        "uploads_deleted":     cleanup_uploads(max_age_hours=24),
        "ran_at":              datetime.now().isoformat(timespec="seconds"),
    }

    log.info(
        f"Cleanup complete — compressed: {results['memories_compressed']}, "
        f"meetings deleted: {results['meetings_deleted']}, "
        f"tts: {results['tts_deleted']}"
    )
    return results


# ── Background scheduler ───────────────────────────────────────────────────────

_cleanup_thread: threading.Thread | None = None
_stop_event = threading.Event()


def start_cleanup_scheduler(interval_hours: int = 24):
    """
    Run cleanup once immediately, then every interval_hours.
    Call this once at server startup.
    """
    global _cleanup_thread

    def _loop():
        # Initial run at startup (small delay so server is ready)
        time.sleep(10)
        run_cleanup()
        while not _stop_event.wait(interval_hours * 3600):
            run_cleanup()

    _cleanup_thread = threading.Thread(target=_loop, daemon=True, name="cleanup")
    _cleanup_thread.start()
    log.info(f"Cleanup scheduler started (every {interval_hours}h)")


def stop_cleanup_scheduler():
    _stop_event.set()
