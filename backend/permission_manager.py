"""Confirm-before-destructive-action gate for LLM-initiated tool calls.

Primnox previously had zero permission gating anywhere — no tool the model
could call was destructive, so nothing needed it. This module is the gate,
introduced alongside the first tools that actually need it (delete_memory /
delete_note in tools.py).

Design constraints, validated against how this app actually runs:
- `POST /message` dispatches into `core.py`'s pipeline via FastAPI
  `BackgroundTasks`, which runs it in a worker thread (anyio's default
  40-slot capacity limiter), not on the asyncio event loop. So blocking that
  thread on `threading.Event.wait()` while we wait for the user to click
  Allow/Deny does not freeze the WebSocket or the rest of the app — this is
  a single-user local app, and tying up one of 40 thread-pool slots for up
  to `timeout` seconds is a non-issue at this scale.
- The frontend answers via a normal async FastAPI route
  (`POST /api/permission_response`), which runs on the event loop thread.
  Calling `.set()` on an `Event` a different thread is waiting on is exactly
  what `threading.Event` is for — no extra synchronization needed.
- Fail-closed: a timeout or an unrecognized token is always treated as deny.
"""

import threading
import time
import uuid

# token -> {"event": threading.Event, "result": bool | None, "session_id": str, "created": float, "timeout": float}
_pending: dict[str, dict] = {}
_lock = threading.Lock()

_broadcast_cb = None


def set_broadcast_callback(cb):
    global _broadcast_cb
    _broadcast_cb = cb


def _sweep_expired():
    """Prunes entries whose wait would already have timed out, plus a grace
    window — covers the case where request_permission() itself never got to
    run its own cleanup (e.g. process interrupted). No background thread:
    this runs inline on every new request, which is enough for the handful
    of permission requests a single-user app will ever have in flight."""
    now = time.time()
    with _lock:
        stale = [
            tok for tok, entry in _pending.items()
            if now - entry["created"] > entry["timeout"] + 300
        ]
        for tok in stale:
            _pending.pop(tok, None)


def request_permission(action: str, description: str, session_id: str = "", timeout: float = 120) -> bool:
    """Blocks the calling thread until the user answers a permission prompt
    (or `timeout` seconds elapse, which counts as deny). Broadcasts a
    `permission_request` WS event for the frontend to render as an
    Allow/Deny chat card."""
    _sweep_expired()

    token = uuid.uuid4().hex[:12]
    event = threading.Event()
    with _lock:
        _pending[token] = {
            "event": event,
            "result": None,
            "session_id": session_id,
            "created": time.time(),
            "timeout": timeout,
        }

    if _broadcast_cb:
        try:
            _broadcast_cb("permission_request", {
                "token": token,
                "action": action,
                "description": description,
                "session_id": session_id,
            })
        except Exception:
            pass

    got_response = event.wait(timeout=timeout)

    with _lock:
        entry = _pending.pop(token, None)

    return bool(got_response and entry and entry["result"] is True)


def resolve_permission(token: str, allow: bool) -> bool:
    """Called by the `/api/permission_response` route. Returns True if a
    matching pending request was found and resolved, False if the token is
    unknown/already expired (e.g. the user answered after the timeout already
    fired) — the caller should treat False as "too late, nothing to do"."""
    with _lock:
        entry = _pending.get(token)
        if entry is None:
            return False
        entry["result"] = bool(allow)
    entry["event"].set()
    return True
