"""Episodic and temporal memory: what happened, and when.

"What was I doing yesterday?" has to be reconstructed from timestamped
evidence, not guessed from whatever is still in the chat window. That is the
job of this module.

Two record types:

* **Events** — individual timestamped observations. A file was opened, a
  tool ran, a test failed, a commit landed. Cheap to write, written often.
* **Episodes** — coherent stretches of work, produced by consolidating a run
  of related events. Dozens of raw events become "spent 40 minutes debugging
  the retrieval router; three test runs, one fix".

Consolidation is what keeps episodic memory from being a log file with extra
steps. Raw events stay addressable by reference, but the durable, retrievable
unit is the episode.

Two design choices worth stating:

**Consolidation is deterministic by default.** Grouping is by time gap and
scope, and the default summary is built from the events themselves. A model
can produce a better sentence, and :func:`consolidate` takes a `summarizer`
hook for exactly that — but memory must not stop working when no provider is
reachable, and the common case should not cost tokens.

**Days are local, timestamps are UTC.** "Yesterday" is a question about the
user's calendar, not about UTC. Storage stays UTC (unambiguous, sortable);
:func:`local_day_bounds` converts a local day into the UTC interval to query.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from v2 import ids, store
from v2.world_model import (
    ORIGIN_CONFIDENCE,
    Provenance,
    SYSTEM_OBSERVED,
    ValidationError,
    project_id,
)

try:  # pragma: no cover - logging is incidental to behaviour
    from logger import get_logger

    log = get_logger("v2.episodes")
except Exception:  # pragma: no cover
    import logging

    log = logging.getLogger("v2.episodes")


# How long a pause between events ends one episode and starts the next.
# Half an hour is long enough to survive reading documentation or a coffee
# break, short enough that yesterday morning and yesterday evening do not
# collapse into one undifferentiated blob.
DEFAULT_GAP_MINUTES = 30

# Events below this importance are recorded but kept out of episode
# summaries, so a burst of routine file-open noise cannot bury the one
# meaningful thing that happened in the same window.
SUMMARY_IMPORTANCE_FLOOR = 0.3

# Per-kind importance. Anything unlisted gets DEFAULT_IMPORTANCE — the map
# only needs to encode what is unusually load-bearing or unusually routine.
IMPORTANCE: dict[str, float] = {
    "error": 0.9,
    "task_started": 0.8,
    "task_completed": 0.8,
    "task_failed": 0.9,
    "decision": 0.9,
    "commit": 0.8,
    "file_modified": 0.7,
    "test_failed": 0.8,
    "test_passed": 0.5,
    "tool_run": 0.5,
    "message": 0.5,
    "file_opened": 0.3,
    "file_read": 0.3,
    "screen_observed": 0.2,
}
DEFAULT_IMPORTANCE = 0.5

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS events (
        id           TEXT PRIMARY KEY,
        kind         TEXT NOT NULL,
        summary      TEXT NOT NULL,
        detail       TEXT,
        project_id   TEXT,
        task_id      TEXT,
        session_id   TEXT,
        entity_ids   TEXT NOT NULL DEFAULT '[]',
        result_ref   TEXT,
        source       TEXT NOT NULL,
        source_ref   TEXT,
        origin       TEXT NOT NULL,
        confidence   REAL NOT NULL,
        sensitivity  TEXT NOT NULL DEFAULT 'normal',
        retention    TEXT NOT NULL DEFAULT 'durable',
        importance   REAL NOT NULL DEFAULT 0.5,
        occurred_at  TEXT NOT NULL,
        recorded_at  TEXT NOT NULL,
        episode_id   TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_time ON events(occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_events_scope ON events(project_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_events_episode ON events(episode_id)",
    """
    CREATE TABLE IF NOT EXISTS episodes (
        id           TEXT PRIMARY KEY,
        summary      TEXT NOT NULL,
        project_id   TEXT,
        session_id   TEXT,
        started_at   TEXT NOT NULL,
        ended_at     TEXT NOT NULL,
        event_count  INTEGER NOT NULL,
        entity_ids   TEXT NOT NULL DEFAULT '[]',
        kinds        TEXT NOT NULL DEFAULT '[]',
        importance   REAL NOT NULL DEFAULT 0.5,
        origin       TEXT NOT NULL DEFAULT 'observed',
        confidence   REAL NOT NULL DEFAULT 0.8,
        created_at   TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_episodes_time ON episodes(started_at)",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
        summary, detail, content='events', content_rowid='rowid'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
        INSERT INTO events_fts(rowid, summary, detail) VALUES (new.rowid, new.summary, new.detail);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
        INSERT INTO events_fts(events_fts, rowid, summary, detail)
        VALUES('delete', old.rowid, old.summary, old.detail);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
        INSERT INTO events_fts(events_fts, rowid, summary, detail)
        VALUES('delete', old.rowid, old.summary, old.detail);
        INSERT INTO events_fts(rowid, summary, detail) VALUES (new.rowid, new.summary, new.detail);
    END
    """,
]


def _init() -> None:
    store.ensure_schema("episodes", _SCHEMA)


def _row(row) -> dict:
    out = dict(row)
    for key in ("entity_ids", "kinds"):
        if key in out:
            try:
                out[key] = json.loads(out[key] or "[]")
            except (TypeError, ValueError):
                out[key] = []
    return out


def _as_iso(value: str | datetime | None) -> str | None:
    """Accept either an ISO string or a datetime, always store UTC ISO.

    A naive datetime is interpreted as local time — that is what a caller
    who built one from `datetime.now()` meant — then converted to UTC.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.astimezone()
        return aware.astimezone(timezone.utc).isoformat()
    return str(value)


# ── Writing ──────────────────────────────────────────────────────────────────


def record_event(
    kind: str,
    summary: str,
    *,
    detail: str | None = None,
    project: str | None = None,
    task: str | None = None,
    session: str | None = None,
    entities: list[str] | None = None,
    result_ref: str | None = None,
    prov: Provenance = SYSTEM_OBSERVED,
    occurred_at: str | datetime | None = None,
    importance: float | None = None,
    sensitivity: str = "normal",
    retention: str = "durable",
) -> dict:
    """Record one timestamped observation.

    `result_ref` points at a tool result in the result store rather than
    inlining it: an event says *that* a dependency report was produced and
    where to find it, not what the whole report said.

    `occurred_at` defaults to now but is settable, because events are often
    recorded slightly after the fact (a file's mtime, a git commit date) and
    the temporal layer must order by when things *happened*.
    """
    if not summary or not summary.strip():
        raise ValidationError("event summary must not be empty")
    _init()

    now = store.utc_now()
    occurred = _as_iso(occurred_at) or now
    eid = ids.new_id("event")
    score = IMPORTANCE.get(kind, DEFAULT_IMPORTANCE) if importance is None else float(importance)

    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO events (id, kind, summary, detail, project_id, task_id, session_id,
                                entity_ids, result_ref, source, source_ref, origin, confidence,
                                sensitivity, retention, importance, occurred_at, recorded_at,
                                episode_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
            """,
            (
                eid, kind, summary.strip(), detail, project_id(project), task, session,
                json.dumps(list(entities or [])), result_ref, prov.source, prov.source_ref,
                prov.origin, prov.confidence, sensitivity, retention, score, occurred, now,
            ),
        )
        row = conn.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()
    return _row(row)


def get_event(event_id: str) -> dict | None:
    _init()
    row = store.connect().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return _row(row) if row else None


def get_episode(episode_id: str) -> dict | None:
    _init()
    row = store.connect().execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
    return _row(row) if row else None


# ── Temporal queries ─────────────────────────────────────────────────────────


def local_day_bounds(days_ago: int = 0, *, tz: timezone | None = None, now: datetime | None = None):
    """UTC bounds of a local calendar day, `days_ago` days back.

    `days_ago=0` is today, `1` is yesterday. Returns `(start_iso, end_iso)`
    with an exclusive end, so day queries tile without overlapping.
    """
    reference = now if now is not None else datetime.now(tz)
    if reference.tzinfo is None:
        # A naive reference means local time — that is what a caller who
        # built one from datetime.now() meant.
        reference = reference.astimezone()
    local_midnight = reference.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    start = local_midnight.astimezone(timezone.utc)
    end = (local_midnight + timedelta(days=1)).astimezone(timezone.utc)
    return start.isoformat(), end.isoformat()


def events_between(
    start: str | datetime,
    end: str | datetime,
    *,
    project: str | None = None,
    kinds: list[str] | None = None,
    session: str | None = None,
    min_importance: float = 0.0,
    include_sensitive: bool = False,
    limit: int = 500,
) -> list[dict]:
    """Events in `[start, end)`, oldest first."""
    _init()
    clauses = ["occurred_at >= ?", "occurred_at < ?", "importance >= ?"]
    params: list = [_as_iso(start), _as_iso(end), min_importance]
    if project is not None:
        clauses.append("project_id = ?")
        params.append(project_id(project))
    if session is not None:
        clauses.append("session_id = ?")
        params.append(session)
    if kinds:
        clauses.append(f"kind IN ({','.join('?' * len(kinds))})")
        params.extend(kinds)
    if not include_sensitive:
        clauses.append("sensitivity != 'secret'")
    params.append(limit)
    rows = store.connect().execute(
        f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY occurred_at ASC LIMIT ?",
        params,
    ).fetchall()
    return [_row(r) for r in rows]


def episodes_between(
    start: str | datetime,
    end: str | datetime,
    *,
    project: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Episodes overlapping `[start, end)`, oldest first.

    Overlap rather than containment: a session that ran from 23:40 to 00:20
    is part of both days' answers, and dropping it from either would be a
    hole in the timeline.
    """
    _init()
    clauses = ["started_at < ?", "ended_at >= ?"]
    params: list = [_as_iso(end), _as_iso(start)]
    if project is not None:
        clauses.append("project_id = ?")
        params.append(project_id(project))
    params.append(limit)
    rows = store.connect().execute(
        f"SELECT * FROM episodes WHERE {' AND '.join(clauses)} ORDER BY started_at ASC LIMIT ?",
        params,
    ).fetchall()
    return [_row(r) for r in rows]


def _fts_query(query: str) -> str | None:
    terms = [t for t in re.split(r"\W+", query or "") if t]
    if not terms:
        return None
    return " OR ".join(f'"{t}"' for t in terms)


def recall(
    query: str,
    *,
    project: str | None = None,
    limit: int = 10,
    include_sensitive: bool = False,
) -> list[dict]:
    """Full-text search over recorded events, most relevant first."""
    _init()
    match = _fts_query(query)
    if match is None:
        return []
    clauses, params = [], [match]
    if project is not None:
        clauses.append("e.project_id = ?")
        params.append(project_id(project))
    if not include_sensitive:
        clauses.append("e.sensitivity != 'secret'")
    where = f"AND {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    try:
        rows = store.connect().execute(
            f"""
            SELECT e.* FROM events_fts x JOIN events e ON x.rowid = e.rowid
             WHERE events_fts MATCH ? {where}
             ORDER BY bm25(events_fts) LIMIT ?
            """,
            params,
        ).fetchall()
    except Exception as exc:  # pragma: no cover - depends on SQLite build
        log.warning("event FTS search failed (%s); falling back to LIKE", exc)
        rows = store.connect().execute(
            f"SELECT e.* FROM events e WHERE e.summary LIKE ? {where} "
            f"ORDER BY e.occurred_at DESC LIMIT ?",
            [f"%{query}%"] + params[1:],
        ).fetchall()
    return [_row(r) for r in rows]


# ── Consolidation ────────────────────────────────────────────────────────────


def _default_summary(events: list[dict]) -> str:
    """Build an episode sentence from the events themselves, no model call.

    Leads with what was worked on (the entities touched most), then what was
    done to them (the dominant event kinds), because that is the order the
    question "what was I doing?" is actually asking about. Low-importance
    noise is excluded so a burst of file-open events cannot outvote the one
    error that mattered.
    """
    meaningful = [e for e in events if e["importance"] >= SUMMARY_IMPORTANCE_FLOOR] or events

    kind_counts = Counter(e["kind"] for e in meaningful)
    kinds = ", ".join(f"{kind.replace('_', ' ')} ×{n}" if n > 1 else kind.replace("_", " ")
                      for kind, n in kind_counts.most_common(4))

    subjects: Counter = Counter()
    for event in meaningful:
        for entity in event["entity_ids"]:
            subjects[entity] += 1

    detail = ""
    if subjects:
        from v2 import world_model

        names = []
        for entity_id, _ in subjects.most_common(3):
            record = world_model.get_entity(entity_id)
            names.append(record["label"] or record["key"] if record else entity_id)
        detail = f" on {', '.join(names)}"

    errors = kind_counts.get("error", 0) + kind_counts.get("task_failed", 0)
    tail = f"; {errors} error{'s' if errors > 1 else ''}" if errors else ""
    return f"{kinds}{detail}{tail}".strip() or "activity"


def consolidate(
    *,
    project: str | None = None,
    session: str | None = None,
    gap_minutes: int = DEFAULT_GAP_MINUTES,
    min_events: int = 1,
    before: str | datetime | None = None,
    summarizer=None,
    limit: int = 2000,
) -> list[dict]:
    """Group unconsolidated events into episodes.

    Events are grouped by scope (project and session, since work on two
    projects at once is two threads of activity, not one) and then split
    wherever the gap between consecutive events exceeds `gap_minutes`.

    `summarizer` receives the list of events for a group and returns a
    sentence; when it is None or raises, the deterministic summary is used
    instead. A memory system that goes quiet because a provider is down is
    worse than one that describes yesterday a little more plainly.

    `before` restricts consolidation to events older than a cutoff, so the
    stretch of work currently in progress is not frozen into an episode
    while it is still running.
    """
    _init()
    clauses = ["episode_id IS NULL"]
    params: list = []
    if project is not None:
        clauses.append("project_id = ?")
        params.append(project_id(project))
    if session is not None:
        clauses.append("session_id = ?")
        params.append(session)
    if before is not None:
        clauses.append("occurred_at < ?")
        params.append(_as_iso(before))
    params.append(limit)

    rows = store.connect().execute(
        f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY occurred_at ASC LIMIT ?",
        params,
    ).fetchall()
    events = [_row(r) for r in rows]
    if not events:
        return []

    groups: dict[tuple, list[dict]] = {}
    for event in events:
        groups.setdefault((event["project_id"], event["session_id"]), []).append(event)

    gap = timedelta(minutes=gap_minutes)
    created: list[dict] = []

    for (scope, sess), scoped in groups.items():
        run: list[dict] = []
        previous: datetime | None = None
        for event in scoped:
            occurred = store.parse_time(event["occurred_at"])
            if previous is not None and occurred is not None and occurred - previous > gap:
                created.extend(_flush(run, scope, sess, min_events, summarizer))
                run = []
            run.append(event)
            previous = occurred or previous
        created.extend(_flush(run, scope, sess, min_events, summarizer))

    return created


def _flush(run: list[dict], scope, session, min_events: int, summarizer) -> list[dict]:
    """Turn one run of events into an episode, if it is worth keeping."""
    if len(run) < max(1, min_events):
        return []

    summary = None
    if summarizer is not None:
        try:
            summary = summarizer(run)
        except Exception as exc:
            log.warning("episode summarizer failed (%s); using deterministic summary", exc)
    origin = "observed"
    if not summary:
        summary = _default_summary(run)
    else:
        # A model-written summary is an inference about what the events
        # meant, and has to be labelled as one — the architecture forbids an
        # inference quietly becoming an observation.
        origin = "inferred"

    entity_ids: list[str] = []
    for event in run:
        for entity in event["entity_ids"]:
            if entity not in entity_ids:
                entity_ids.append(entity)

    episode_id = ids.new_id("episode")
    kinds = sorted({e["kind"] for e in run})
    importance = max(e["importance"] for e in run)
    now = store.utc_now()

    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO episodes (id, summary, project_id, session_id, started_at, ended_at,
                                  event_count, entity_ids, kinds, importance, origin, confidence,
                                  created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                episode_id, summary, scope, session, run[0]["occurred_at"], run[-1]["occurred_at"],
                len(run), json.dumps(entity_ids), json.dumps(kinds), importance, origin,
                ORIGIN_CONFIDENCE[origin], now,
            ),
        )
        conn.executemany(
            "UPDATE events SET episode_id = ? WHERE id = ?",
            [(episode_id, e["id"]) for e in run],
        )
        row = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
    return [_row(row)]


def events_in_episode(episode_id: str, limit: int = 500) -> list[dict]:
    """The raw events an episode was built from — its evidence."""
    _init()
    rows = store.connect().execute(
        "SELECT * FROM events WHERE episode_id = ? ORDER BY occurred_at ASC LIMIT ?",
        (episode_id, limit),
    ).fetchall()
    return [_row(r) for r in rows]


# ── Reconstruction ───────────────────────────────────────────────────────────


def timeline(
    start: str | datetime,
    end: str | datetime,
    *,
    project: str | None = None,
    max_entries: int = 12,
) -> dict:
    """Reconstruct a compact account of a period.

    Returns consolidated episodes plus any events in the window that were
    never consolidated, ranked by importance and trimmed to `max_entries`.
    This is the shape "what was I doing yesterday?" answers from: a small
    ordered set of statements, each carrying its own evidence references,
    rather than a wall of raw events.
    """
    start_iso, end_iso = _as_iso(start), _as_iso(end)
    grouped = episodes_between(start_iso, end_iso, project=project)
    covered = {e["id"] for e in grouped}

    loose = [
        event
        for event in events_between(start_iso, end_iso, project=project)
        if event["episode_id"] is None or event["episode_id"] not in covered
    ]

    entries: list[dict] = [
        {
            "type": "episode",
            "id": ep["id"],
            "summary": ep["summary"],
            "started_at": ep["started_at"],
            "ended_at": ep["ended_at"],
            "event_count": ep["event_count"],
            "entity_ids": ep["entity_ids"],
            "importance": ep["importance"],
            "origin": ep["origin"],
            "confidence": ep["confidence"],
        }
        for ep in grouped
    ]
    entries += [
        {
            "type": "event",
            "id": ev["id"],
            "summary": ev["summary"],
            "started_at": ev["occurred_at"],
            "ended_at": ev["occurred_at"],
            "event_count": 1,
            "entity_ids": ev["entity_ids"],
            "importance": ev["importance"],
            "origin": ev["origin"],
            "confidence": ev["confidence"],
            "result_ref": ev["result_ref"],
        }
        for ev in loose
    ]

    entries.sort(key=lambda e: (-e["importance"], e["started_at"]))
    kept = entries[:max_entries]
    kept.sort(key=lambda e: e["started_at"])

    return {
        "start": start_iso,
        "end": end_iso,
        "entries": kept,
        "total_entries": len(entries),
        "truncated": len(entries) > len(kept),
    }


def last_activity(*, project: str | None = None, limit: int = 5) -> list[dict]:
    """The most recent events, newest first — "where did I leave off?"."""
    _init()
    clauses, params = [], []
    if project is not None:
        clauses.append("project_id = ?")
        params.append(project_id(project))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = store.connect().execute(
        f"SELECT * FROM events {where} ORDER BY occurred_at DESC LIMIT ?", params
    ).fetchall()
    return [_row(r) for r in rows]


# ── Deletion ─────────────────────────────────────────────────────────────────


def forget_session(session: str) -> int:
    """Delete every event recorded under a session.

    Backs "don't remember this": a session marked non-persistent still needs
    working state while it runs, and this is what removes it afterwards.
    """
    _init()
    with store.transaction() as conn:
        return conn.execute("DELETE FROM events WHERE session_id = ?", (session,)).rowcount


def purge_project(project: str) -> dict:
    """Delete a project's events and episodes."""
    _init()
    scope = project_id(project)
    with store.transaction() as conn:
        events = conn.execute("DELETE FROM events WHERE project_id = ?", (scope,)).rowcount
        eps = conn.execute("DELETE FROM episodes WHERE project_id = ?", (scope,)).rowcount
    return {"project_id": scope, "events_deleted": events, "episodes_deleted": eps}
