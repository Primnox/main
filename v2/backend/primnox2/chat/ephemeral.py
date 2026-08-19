"""In-memory runtime for incognito conversations — CRS §11.2.

An incognito conversation writes no rows to `conversations`, `turns`,
`messages` or `events` (§11.2.1). That is a hard constraint, and it rules out
every mechanism the ordinary path is built on: the turn's status lives in a
table, the job queue is a table, and the job's payload — which is the user's
message — is a column in it. So incognito needs a store of its own.

This module is only the store. The rules about what a turn may do live in
`turns.py`, which owns both paths and chooses between them; keeping the state
machine in one place is what stops incognito quietly acquiring different
semantics from every other conversation.

Nothing here is durable, and that is the feature. A restart takes the whole
thing with it, which is what §11.2.3 describes — and the UI says so rather
than presenting an empty conversation as though nothing had been lost.
"""
from __future__ import annotations

import threading
import time
from typing import Any

now_ms = lambda: int(time.time() * 1000)

_lock = threading.RLock()
_conversations: dict[str, dict] = {}
_turns: dict[str, dict] = {}
_jobs: dict[str, dict] = {}
_queue: list[str] = []


# ── Conversations ────────────────────────────────────────────────────────────
def register_conversation(conversation_id: str, title: str) -> dict:
    ts = now_ms()
    record = {
        "id": conversation_id, "title": title, "folder_id": None,
        "incognito": 1, "created_at": ts, "updated_at": ts,
        "archived_at": None, "turn_count": 0,
    }
    with _lock:
        _conversations[conversation_id] = record
    return dict(record)


def is_incognito(conversation_id: str | None) -> bool:
    if conversation_id is None:
        return False
    with _lock:
        return conversation_id in _conversations


def conversation(conversation_id: str) -> dict | None:
    with _lock:
        record = _conversations.get(conversation_id)
        return dict(record) if record else None


def list_conversations() -> list[dict]:
    with _lock:
        out = []
        for record in _conversations.values():
            copy = dict(record)
            copy["turn_count"] = sum(1 for t in _turns.values()
                                     if t["conversation_id"] == record["id"])
            out.append(copy)
    return sorted(out, key=lambda c: c["updated_at"], reverse=True)


def rename_conversation(conversation_id: str, title: str) -> None:
    with _lock:
        record = _conversations.get(conversation_id)
        if record is not None:
            record["title"] = title


def forget_conversation(conversation_id: str) -> None:
    """Close it and it is gone — the only kind of deletion that needs no
    tombstone, because there was never anything to tombstone."""
    with _lock:
        _conversations.pop(conversation_id, None)
        gone = [tid for tid, t in _turns.items()
                if t["conversation_id"] == conversation_id]
        for tid in gone:
            _turns.pop(tid, None)
        for jid in [j for j, job in _jobs.items() if job.get("turn_id") in gone]:
            _jobs.pop(jid, None)
            if jid in _queue:
                _queue.remove(jid)


# ── Turns ────────────────────────────────────────────────────────────────────
def next_seq(conversation_id: str) -> int:
    with _lock:
        return 1 + sum(1 for t in _turns.values()
                       if t["conversation_id"] == conversation_id)


def put_turn(record: dict) -> None:
    with _lock:
        _turns[record["turn_id"]] = record
        conv = _conversations.get(record["conversation_id"])
        if conv:
            conv["updated_at"] = now_ms()


def has_turn(turn_id: str | None) -> bool:
    if turn_id is None:
        return False
    with _lock:
        return turn_id in _turns


def turn(turn_id: str) -> dict | None:
    with _lock:
        record = _turns.get(turn_id)
        return dict(record) if record else None


def update_turn(turn_id: str, **fields: Any) -> dict | None:
    with _lock:
        record = _turns.get(turn_id)
        if record is None:
            return None
        record.update(fields)
        conv = _conversations.get(record["conversation_id"])
        if conv:
            conv["updated_at"] = now_ms()
        return dict(record)


def history(conversation_id: str) -> list[dict]:
    with _lock:
        rows = [dict(t) for t in _turns.values()
                if t["conversation_id"] == conversation_id]
    return sorted(rows, key=lambda t: t["seq"])


# ── Jobs ─────────────────────────────────────────────────────────────────────
def enqueue_job(job: dict) -> None:
    with _lock:
        _jobs[job["id"]] = job
        _queue.append(job["id"])


def claim_job() -> dict | None:
    with _lock:
        while _queue:
            jid = _queue.pop(0)
            job = _jobs.get(jid)
            if job is None or job["status"] != "queued":
                continue
            job["status"] = "running"
            job["started_at"] = now_ms()
            job["attempts"] = job.get("attempts", 0) + 1
            return dict(job)
    return None


def has_job(job_id: str | None) -> bool:
    if job_id is None:
        return False
    with _lock:
        return job_id in _jobs


def update_job(job_id: str, **fields: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(fields)


def job_cancelled(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        return bool(job and job.get("cancel_requested"))


def turn_cancel_requested(turn_id: str) -> bool:
    with _lock:
        return any(j.get("turn_id") == turn_id and j.get("cancel_requested")
                   for j in _jobs.values())


def cancel_jobs_for_turn(turn_id: str) -> None:
    with _lock:
        for job in _jobs.values():
            if job.get("turn_id") == turn_id and job["status"] in ("queued", "running"):
                job["cancel_requested"] = True
                if job["status"] == "queued":
                    job["status"] = "cancelled"
                    job["finished_at"] = now_ms()


def reset() -> None:
    """For tests. Production has exactly one way to clear this: exit."""
    with _lock:
        _conversations.clear()
        _turns.clear()
        _jobs.clear()
        _queue.clear()
