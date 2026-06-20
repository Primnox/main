import logging
import json
import time
import os
import platform
import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from collections import deque

# ── Single source of truth for the app version ───────────────────────────────
APP_VERSION = "0.0.91"

LOG_DIR = Path.home() / "Documents" / "Primnox" / "Logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "primnox.log"

# In-memory ring buffer for live log viewer (last 500 entries)
_log_buffer: deque = deque(maxlen=500)

# Track whether we have written the session banner yet (per-process)
_session_banner_written = False


def _write_session_banner():
    """Write a human-readable session header at the start of every run."""
    global _session_banner_written
    if _session_banner_written:
        return
    _session_banner_written = True

    now_utc  = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    now_local = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pid      = os.getpid()
    py_ver   = platform.python_version()
    os_info  = f"{platform.system()} {platform.release()}"

    banner_lines = [
        "",
        "=" * 70,
        f"  PRIMNOX  v{APP_VERSION}",
        f"  Started : {now_local}  ({now_utc})",
        f"  PID     : {pid}",
        f"  Python  : {py_ver}   OS: {os_info}",
        "=" * 70,
        "",
    ]
    banner_text = "\n".join(banner_lines) + "\n"

    # Write banner as plain text (not JSON) directly to the log file so it
    # stands out clearly when you open the raw log.
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(banner_text)

    # Also push a structured entry into the in-memory buffer for the UI viewer
    _log_buffer.append({
        "ts": round(time.time(), 3),
        "level": "INFO",
        "module": "primnox.startup",
        "msg": f"=== Primnox v{APP_VERSION} started — PID {pid} — {now_utc} ===",
        "version": APP_VERSION,
        "pid": pid,
        "python": py_ver,
        "os": os_info,
    })


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        _log_buffer.append(entry)
        return json.dumps(entry)


class BufferHandler(logging.Handler):
    """Just writes to the in-memory buffer (JsonFormatter already does it, this is a no-op sink)."""
    def emit(self, record):
        pass


def _build_logger(name: str) -> logging.Logger:
    global _session_banner_written

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    # Write session banner on first logger creation
    _write_session_banner()

    logger.setLevel(logging.DEBUG)

    # Rotating file — 5 MB x 3 files
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    # Console — human-readable
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"))
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    return _build_logger(f"primnox.{name}")


def get_log_buffer(limit: int = 200, level: str = "all") -> list:
    entries = list(_log_buffer)
    if level != "all":
        entries = [e for e in entries if e.get("level", "").upper() == level.upper()]
    return entries[-limit:]
