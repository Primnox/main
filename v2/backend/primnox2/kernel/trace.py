"""Replay Recorder — Primnox's equivalent of a crash dump.

When someone reports "my response duplicated", the answer should be to replay
that turn exactly, not to guess. This records the full execution trace of a
turn: its workflow states, every event, sandbox actions, database writes, and
provider calls, in order.

It is off by default. Recording every turn forever would be its own storage
problem, and the value is in being able to turn it on for a reproducible
complaint — or leave it on during development, which is what
`PRIMNOX2_TRACE=1` is for.

The trace is written when the turn reaches a terminal state, so a completed
trace on disk always describes a finished turn. A crash mid-turn leaves no
trace file, which is itself the signal that the turn never finished.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .. import paths
from .events import bus

now_ms = lambda: int(time.time() * 1000)

TERMINAL_KINDS = {"turn.completed", "turn.failed", "turn.cancelled"}


class ReplayRecorder:
    def __init__(self) -> None:
        self._traces: dict[str, list[dict]] = {}
        self._lock = threading.RLock()
        self._sid: int | None = None
        self._always = os.getenv("PRIMNOX2_TRACE") == "1"
        self._watched: set[str] = set()

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._sid is None:
            self._sid = bus.subscribe(self._on_event)

    def stop(self) -> None:
        if self._sid is not None:
            bus.unsubscribe(self._sid)
            self._sid = None

    def watch(self, turn_id: str) -> None:
        """Record this specific turn even when tracing is otherwise off."""
        with self._lock:
            self._watched.add(turn_id)
        self.start()

    def _recording(self, turn_id: str | None) -> bool:
        if turn_id is None:
            return False
        return self._always or turn_id in self._watched

    # ── capture ──────────────────────────────────────────────────────────
    def _on_event(self, event: dict) -> None:
        turn_id = event.get("turn_id")
        if not self._recording(turn_id):
            return
        self._append(turn_id, {
            "at": event.get("ts", now_ms()),
            "category": "event",
            "kind": event["kind"],
            "sequence": event.get("sequence"),
            "payload": _small(event.get("payload", {})),
        })
        if event["kind"] in TERMINAL_KINDS:
            self.flush(turn_id)

    def note(self, turn_id: str | None, category: str, **fields) -> None:
        """Record something the event stream does not carry.

        Provider calls and database transactions are deliberately not events —
        they are not things a client should see — but they are exactly what you
        need when reconstructing why a turn behaved oddly.
        """
        if not self._recording(turn_id):
            return
        self._append(turn_id, {"at": now_ms(), "category": category, **fields})

    def _append(self, turn_id: str, entry: dict) -> None:
        with self._lock:
            self._traces.setdefault(turn_id, []).append(entry)

    # ── output ───────────────────────────────────────────────────────────
    def flush(self, turn_id: str) -> Path | None:
        with self._lock:
            entries = self._traces.pop(turn_id, None)
            self._watched.discard(turn_id)
        if not entries:
            return None
        path = paths.traces_dir() / f"{turn_id}.json"
        try:
            path.write_text(json.dumps({
                "turn_id": turn_id,
                "recorded_at": now_ms(),
                "entries": entries,
            }, indent=2), encoding="utf-8")
        except OSError:
            return None
        return path

    def dump(self, turn_id: str) -> dict | None:
        """Read a trace back — live if still in memory, else from disk."""
        with self._lock:
            live = self._traces.get(turn_id)
        if live:
            return {"turn_id": turn_id, "live": True, "entries": list(live)}
        path = paths.traces_dir() / f"{turn_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def timeline(self, turn_id: str) -> list[str]:
        """A one-line-per-step human view — what you actually read first."""
        trace = self.dump(turn_id)
        if not trace:
            return []
        out = []
        base = trace["entries"][0]["at"] if trace["entries"] else 0
        for e in trace["entries"]:
            offset = e["at"] - base
            label = e.get("kind") or e.get("action") or e["category"]
            detail = ""
            if e["category"] == "event" and e.get("kind") == "turn.status":
                detail = f' → {e["payload"].get("status")}'
            elif e["category"] == "provider":
                detail = f' ({e.get("messages", "?")} messages, {e.get("tokens", "?")} tokens)'
            elif e["category"] == "sandbox":
                detail = f' {e.get("runtime", "")} exit={e.get("exit_code")}'
            out.append(f"{offset:>6}ms  {e['category']:<9} {label}{detail}")
        return out


def _small(payload: dict, limit: int = 400) -> dict:
    """Trim large values. A trace is a diagnostic, not a second copy of the
    conversation."""
    out = {}
    for k, v in (payload or {}).items():
        if isinstance(v, str) and len(v) > limit:
            out[k] = v[:limit] + f"… (+{len(v) - limit} chars)"
        else:
            out[k] = v
    return out


recorder = ReplayRecorder()
