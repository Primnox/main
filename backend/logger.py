import logging
import json
import time
import os
import shutil
import subprocess
import sys
import threading
import platform
import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from collections import deque

# ── Single source of truth for the app version ───────────────────────────────
APP_VERSION = "1.2.0-beta"

LOG_DIR = Path.home() / "Documents" / "Primnox" / "Logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "primnox.log"

# In-memory ring buffer for live log viewer (last 500 entries)
_log_buffer: deque = deque(maxlen=500)

# Track whether we have written the session banner yet (per-process)
_session_banner_written = False

# Guards the check-then-act in _build_logger. Several background threads
# (feed loop, recorder, background worker) start within milliseconds of each
# other at launch and each may request the same logger name for the first
# time; without this lock two threads can both see `logger.handlers` empty
# and each attach their own file+console handler, doubling every line that
# logger ever writes for the rest of the process.
_logger_build_lock = threading.Lock()


def _write_session_banner():
    """Write a human-readable session header at the start of every run."""
    global _session_banner_written
    if _session_banner_written:
        return
    _session_banner_written = True

    now_utc  = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
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


def _record_to_entry(record: logging.LogRecord) -> dict:
    entry = {
        "ts": round(time.time(), 3),
        "level": record.levelname,
        "module": record.name,
        "msg": record.getMessage(),
    }
    if record.exc_info:
        entry["exc"] = logging.Formatter().formatException(record.exc_info)
    return entry


class JsonFormatter(logging.Formatter):
    """Pure formatter — MUST NOT have side effects.

    RotatingFileHandler.shouldRollover() calls format(record) once just to
    measure the rendered size, then emit() calls it again to actually write
    the line — so format() runs twice per log call by design. It used to
    also append to _log_buffer here, which silently doubled every entry the
    live log viewer shows. The buffer append now lives in BufferHandler.emit,
    which the logging module guarantees runs exactly once per record.
    """
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(_record_to_entry(record))


class BufferHandler(logging.Handler):
    """Appends each record to the in-memory ring buffer exactly once."""
    def emit(self, record):
        _log_buffer.append(_record_to_entry(record))


def _build_logger(name: str) -> logging.Logger:
    global _session_banner_written

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    with _logger_build_lock:
        if logger.handlers:
            return logger  # a racing thread finished configuring it first

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

        # In-memory ring buffer for the live log viewer
        bh = BufferHandler()
        bh.setLevel(logging.DEBUG)
        logger.addHandler(bh)

        logger.propagate = False
        return logger


def get_logger(name: str) -> logging.Logger:
    return _build_logger(f"primnox.{name}")


def get_log_buffer(limit: int = 200, level: str = "all") -> list:
    entries = list(_log_buffer)
    if level != "all":
        entries = [e for e in entries if e.get("level", "").upper() == level.upper()]
    return entries[-limit:]


def get_log_path() -> str:
    """Absolute path of the active log file, for the UI and bug reports."""
    return str(LOG_FILE)


# ————— Crash capture ——————————————————————————————————————————————————————
# Without these an uncaught exception prints to a stderr nobody reads and the
# process dies leaving nothing in the log. Background threads are worse: they
# die silently and the feature they served just stops working.

_crash_handlers_installed = False


def install_crash_handlers() -> None:
    """Route every uncaught exception — main thread, worker threads, asyncio,
    and interpreter shutdown — into the log file."""
    global _crash_handlers_installed
    if _crash_handlers_installed:
        return
    _crash_handlers_installed = True

    log = get_logger("crash")

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            # Ctrl-C is a user action, not a crash — keep default behaviour.
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        log.critical("UNCAUGHT EXCEPTION", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _hook

    def _thread_hook(args):
        if issubclass(args.exc_type, SystemExit):
            return
        log.critical(
            f"UNCAUGHT EXCEPTION in thread {args.thread.name if args.thread else '?'}",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_hook

    try:
        def _unraisable_hook(unraisable):
            log.error(
                f"UNRAISABLE in {unraisable.object!r}: {unraisable.err_msg or ''}",
                exc_info=(
                    unraisable.exc_type,
                    unraisable.exc_value,
                    unraisable.exc_traceback,
                ),
            )

        sys.unraisablehook = _unraisable_hook
    except Exception:
        pass

    log.debug("Crash handlers installed.")


def install_asyncio_handler(loop) -> None:
    """Attach an exception handler to a running asyncio loop.

    Call once the loop exists; unhandled task exceptions are otherwise only
    reported when the task is garbage collected, if at all.
    """
    log = get_logger("crash")

    def _handler(_loop, context):
        exc = context.get("exception")
        message = context.get("message", "unhandled asyncio error")
        if exc is not None:
            log.error(f"ASYNCIO: {message}", exc_info=exc)
        else:
            log.error(f"ASYNCIO: {message} | {context}")

    try:
        loop.set_exception_handler(_handler)
    except Exception as e:
        log.warning(f"Could not attach asyncio exception handler: {e}")


def capture_stdlib_logging(level: int = logging.INFO) -> None:
    """Send third-party logs (uvicorn, transformers, httpx) to the same file.

    They log to the root logger, which by default has no handler pointing at
    the Primnox log, so their warnings are invisible in bug reports.
    """
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    fh.setLevel(level)
    root.addHandler(fh)
    root.setLevel(level)


# ————— Environment + capability diagnostics ———————————————————————————————
# A port fails quietly: a missing framework or an ungranted permission turns a
# feature into a no-op with no error. This records, at every startup, exactly
# which backend resolved and which permissions are actually held.

def _probe_macos() -> dict:
    caps = {}
    try:
        from ApplicationServices import AXIsProcessTrusted
        caps["pyobjc"] = True
        caps["accessibility_granted"] = bool(AXIsProcessTrusted())
    except Exception as e:
        caps["pyobjc"] = False
        caps["accessibility_granted"] = False
        caps["pyobjc_error"] = str(e)

    try:
        import Quartz
        caps["quartz"] = True
        # Preflight does not prompt; it only reports current state.
        if hasattr(Quartz, "CGPreflightScreenCaptureAccess"):
            caps["screen_recording_granted"] = bool(Quartz.CGPreflightScreenCaptureAccess())
        else:
            caps["screen_recording_granted"] = "unknown (old macOS)"
    except Exception as e:
        caps["quartz"] = False
        caps["quartz_error"] = str(e)

    return caps


def _probe_windows() -> dict:
    caps = {}
    for mod in ("win32gui", "uiautomation", "pythoncom"):
        try:
            __import__(mod)
            caps[mod] = True
        except Exception:
            caps[mod] = False
    return caps


def _probe_linux() -> dict:
    return {
        "xdotool": shutil.which("xdotool") is not None,
        "display": os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or None,
    }


def _probe_audio() -> dict:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        inputs = [d["name"] for d in devices if d.get("max_input_channels", 0) > 0]
        return {"sounddevice": True, "input_device_count": len(inputs)}
    except Exception as e:
        return {"sounddevice": False, "error": str(e)}


def log_environment() -> dict:
    """Log a full capability + permission matrix. Returns it for the UI too."""
    log = get_logger("env")

    info = {
        "app_version": APP_VERSION,
        "python": platform.python_version(),
        "platform": sys.platform,
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "pid": os.getpid(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "cwd": os.getcwd(),
        "log_file": str(LOG_FILE),
    }

    if sys.platform == "darwin":
        info["capabilities"] = _probe_macos()
    elif sys.platform == "win32":
        info["capabilities"] = _probe_windows()
    else:
        info["capabilities"] = _probe_linux()

    info["audio"] = _probe_audio()

    log.info(f"ENVIRONMENT: {json.dumps(info)}")

    # Permission gaps are the single most common cause of "feature silently does
    # nothing" on macOS, so surface them as warnings rather than burying them.
    caps = info["capabilities"]
    if sys.platform == "darwin":
        if not caps.get("pyobjc"):
            log.warning("pyobjc missing — window titles and element scanning unavailable.")
        elif not caps.get("accessibility_granted"):
            log.warning(
                "Accessibility permission NOT granted — element scanning disabled. "
                "System Settings -> Privacy & Security -> Accessibility."
            )
        if caps.get("screen_recording_granted") is False:
            log.warning(
                "Screen Recording permission NOT granted — screen capture will be blank. "
                "System Settings -> Privacy & Security -> Screen Recording."
            )

    return info
