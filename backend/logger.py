import logging
import json
import time
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from collections import deque

LOG_DIR = Path.home() / "Documents" / "Primnox" / "Logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "primnox.log"

# In-memory ring buffer for live log viewer (last 500 entries)
_log_buffer: deque = deque(maxlen=500)

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
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured
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
