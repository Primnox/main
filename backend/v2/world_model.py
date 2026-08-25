"""The world model: entities, relationships and durable facts.

This is the "common language" of V2. A vector search can retrieve text that
mentions `router.py`. The world model can say that `router.py` belongs to
the Primnox project, was modified during a task, is imported by `brain.py`,
and that the user stated on Tuesday that this project uses pnpm — and, for
every one of those, where the belief came from and whether it is still
current.

Three record types live here:

* **Entities** — the things (user, project, task, file, symbol, module,
  application, document, artifact, conversation, event, tool). Identified by
  a stable ID derived from type + scope + natural key, so observing the same
  file twice updates one row instead of creating two.
* **Relationships** — typed, directed edges between entities.
* **Facts** — durable semantic ("this project uses pnpm") and procedural
  ("deploys go through scripts/release.sh") memory. Episodic memory, which
  is about *when things happened*, lives in `episodes.py` instead.

All three carry the same metadata spine, because the architecture requires
every durable belief to be able to answer "why do you believe this?":

    source · source_ref · origin · confidence · sensitivity · retention
    observed_at · valid_from · valid_until · last_confirmed · superseded_by

Two rules from the architecture are enforced structurally rather than left
to convention:

1. **Historical truth is never destroyed by an update.** Superseding a fact
   closes its validity interval and links it forward; it does not delete the
   row. "What do you believe now" and "what did you believe then" are both
   answerable.
2. **An inference never silently becomes a fact.** `origin` is carried
   through supersession and ranking. A model's guess can outrank nothing but
   an older, weaker guess.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from v2 import ids, store

try:  # pragma: no cover - logging is incidental to behaviour
    from logger import get_logger

    log = get_logger("v2.world_model")
except Exception:  # pragma: no cover - keeps V2 importable standalone
    import logging

    log = logging.getLogger("v2.world_model")


# ── Vocabulary ───────────────────────────────────────────────────────────────

ENTITY_TYPES: set[str] = {
    "user",
    "project",
    "task",
    "file",
    "symbol",
    "module",
    "application",
    "document",
    "artifact",
    "conversation",
    "event",
    "tool",
}

RELATIONSHIPS: set[str] = {
    "works_on",
    "belongs_to",
    "contains",
    "references",
    "calls",
    "imports",
    "depends_on",
    "modified",
    "created",
    "related_to",
    "derived_from",
}

# Where a belief came from.
SOURCES: set[str] = {"user", "conversation", "file", "git", "os", "tool", "model", "artifact"}

# How it was arrived at. This is the axis that keeps a guess from being
# mistaken for a fact, so it is deliberately only three coarse values.
ORIGINS: set[str] = {"stated", "observed", "inferred"}

# Rank used when two beliefs disagree: what the user said outranks what the
# system saw, which outranks what a model concluded.
ORIGIN_RANK: dict[str, int] = {"stated": 3, "observed": 2, "inferred": 1}

# Default confidence per origin, used when a caller does not supply one.
ORIGIN_CONFIDENCE: dict[str, float] = {"stated": 0.95, "observed": 0.8, "inferred": 0.5}

SENSITIVITY_LEVELS: list[str] = ["public", "normal", "sensitive", "secret"]
RETENTION_POLICIES: set[str] = {"durable", "session", "ephemeral"}

FACT_KINDS: set[str] = {"semantic", "procedural"}

# How similar two facts in the same scope must be before they are treated as
# competing statements about the same thing. Matches the threshold V1's
# memory.py settled on for near-duplicate detection.
CONFLICT_SIMILARITY = 0.85

# How many current facts in a scope are compared against a new one when no
# explicit slot is given. Bounded so a large project cannot make every write
# scale with total fact count.
_CONFLICT_CANDIDATES = 200


class ValidationError(ValueError):
    """Raised for an unknown entity type, relationship or metadata value."""


# ── Provenance ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Provenance:
    """Where a belief came from and how much weight it carries.

    Frozen because provenance describes a past observation: rewriting it
    after the fact would defeat the point of recording it.
    """

    source: str = "user"
    source_ref: str | None = None
    origin: str = "stated"
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise ValidationError(f"unknown source {self.source!r}; known: {sorted(SOURCES)}")
        if self.origin not in ORIGINS:
            raise ValidationError(f"unknown origin {self.origin!r}; known: {sorted(ORIGINS)}")
        if self.confidence is None:
            object.__setattr__(self, "confidence", ORIGIN_CONFIDENCE[self.origin])
        elif not 0.0 <= float(self.confidence) <= 1.0:
            raise ValidationError(f"confidence must be within 0..1, got {self.confidence!r}")


def provenance(
    source: str = "user",
    source_ref: str | None = None,
    origin: str = "stated",
    confidence: float | None = None,
) -> Provenance:
    """Convenience constructor so call sites read as prose."""
    return Provenance(source=source, source_ref=source_ref, origin=origin, confidence=confidence)


USER_STATED = Provenance(source="user", origin="stated")
SYSTEM_OBSERVED = Provenance(source="os", origin="observed")
MODEL_INFERRED = Provenance(source="model", origin="inferred")


# ── Schema ───────────────────────────────────────────────────────────────────

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS entities (
        id             TEXT PRIMARY KEY,
        type           TEXT NOT NULL,
        key            TEXT NOT NULL,
        label          TEXT,
        project_id     TEXT,
        attributes     TEXT NOT NULL DEFAULT '{}',
        source         TEXT NOT NULL,
        source_ref     TEXT,
        origin         TEXT NOT NULL,
        confidence     REAL NOT NULL,
        sensitivity    TEXT NOT NULL DEFAULT 'normal',
        retention      TEXT NOT NULL DEFAULT 'durable',
        observed_at    TEXT NOT NULL,
        valid_from     TEXT NOT NULL,
        valid_until    TEXT,
        last_confirmed TEXT,
        superseded_by  TEXT,
        created_at     TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_entities_type_project ON entities(type, project_id)",
    "CREATE INDEX IF NOT EXISTS idx_entities_key ON entities(key)",
    """
    CREATE TABLE IF NOT EXISTS relationships (
        id             TEXT PRIMARY KEY,
        src_id         TEXT NOT NULL,
        rel            TEXT NOT NULL,
        dst_id         TEXT NOT NULL,
        project_id     TEXT,
        attributes     TEXT NOT NULL DEFAULT '{}',
        source         TEXT NOT NULL,
        source_ref     TEXT,
        origin         TEXT NOT NULL,
        confidence     REAL NOT NULL,
        observed_at    TEXT NOT NULL,
        valid_from     TEXT NOT NULL,
        valid_until    TEXT,
        last_confirmed TEXT,
        created_at     TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rel_src ON relationships(src_id, rel)",
    "CREATE INDEX IF NOT EXISTS idx_rel_dst ON relationships(dst_id, rel)",
    """
    CREATE TABLE IF NOT EXISTS facts (
        id             TEXT PRIMARY KEY,
        text           TEXT NOT NULL,
        kind           TEXT NOT NULL DEFAULT 'semantic',
        subject_id     TEXT,
        project_id     TEXT,
        slot           TEXT,
        source         TEXT NOT NULL,
        source_ref     TEXT,
        origin         TEXT NOT NULL,
        confidence     REAL NOT NULL,
        sensitivity    TEXT NOT NULL DEFAULT 'normal',
        retention      TEXT NOT NULL DEFAULT 'durable',
        observed_at    TEXT NOT NULL,
        valid_from     TEXT NOT NULL,
        valid_until    TEXT,
        last_confirmed TEXT,
        superseded_by  TEXT,
        supersedes     TEXT,
        stale          INTEGER NOT NULL DEFAULT 0,
        stale_reason   TEXT,
        disputed       INTEGER NOT NULL DEFAULT 0,
        access_count   INTEGER NOT NULL DEFAULT 0,
        created_at     TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_facts_scope ON facts(project_id, slot, valid_until)",
    "CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject_id)",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
        text, content='facts', content_rowid='rowid'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
        INSERT INTO facts_fts(rowid, text) VALUES (new.rowid, new.text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
        INSERT INTO facts_fts(facts_fts, rowid, text) VALUES('delete', old.rowid, old.text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
        INSERT INTO facts_fts(facts_fts, rowid, text) VALUES('delete', old.rowid, old.text);
        INSERT INTO facts_fts(rowid, text) VALUES (new.rowid, new.text);
    END
    """,
]


def _init() -> None:
    store.ensure_schema("world_model", _SCHEMA)


# ── Helpers ──────────────────────────────────────────────────────────────────


def project_id(project: str | None) -> str | None:
    """Normalise a project reference to a stable ID.

    Accepts either an existing entity ID or a plain project name. A name is
    hashed into the same ID the project entity would receive, so scoping
    works whether or not the project has been explicitly registered — the
    string "primnox" and the entity for it are the same scope.
    """
    if project is None:
        return None
    if ids.is_id(project, "entity"):
        return project
    return ids.stable_id("entity", "project", "", project)


def entity_id(type_: str, key: str, project: str | None = None) -> str:
    """The stable ID an entity of this type/key/scope has or would have."""
    if type_ not in ENTITY_TYPES:
        raise ValidationError(f"unknown entity type {type_!r}; known: {sorted(ENTITY_TYPES)}")
    scope = "" if type_ == "project" else (project_id(project) or "")
    return ids.stable_id("entity", type_, scope, key)


def _check_sensitivity(value: str) -> str:
    if value not in SENSITIVITY_LEVELS:
        raise ValidationError(f"unknown sensitivity {value!r}; known: {SENSITIVITY_LEVELS}")
    return value


def _check_retention(value: str) -> str:
    if value not in RETENTION_POLICIES:
        raise ValidationError(f"unknown retention {value!r}; known: {sorted(RETENTION_POLICIES)}")
    return value


def _row_to_dict(row) -> dict:
    out = dict(row)
    if "attributes" in out:
        try:
            out["attributes"] = json.loads(out["attributes"] or "{}")
        except (TypeError, ValueError):
            out["attributes"] = {}
    for flag in ("stale", "disputed"):
        if flag in out:
            out[flag] = bool(out[flag])
    return out


def strength(record: dict) -> tuple[int, float, str]:
    """Comparable evidence strength: (origin rank, confidence, observed_at).

    Ordered so that a plain tuple comparison encodes the architecture's
    evidence hierarchy: how the belief was arrived at dominates, confidence
    breaks ties within an origin, and recency breaks ties after that.
    """
    return (
        ORIGIN_RANK.get(record.get("origin", "inferred"), 0),
        float(record.get("confidence") or 0.0),
        str(record.get("observed_at") or ""),
    )


def is_stronger(candidate: dict, incumbent: dict) -> bool:
    """True if `candidate` should be allowed to supersede `incumbent`.

    Ties go to the newcomer only when it is at least as strong on origin and
    confidence — a fresh inference does not get to overwrite something the
    user stated just because it happened later.
    """
    cand, inc = strength(candidate), strength(incumbent)
    if cand[:2] == inc[:2]:
        return cand[2] >= inc[2]
    return cand > inc


# ── Entities ─────────────────────────────────────────────────────────────────


def upsert_entity(
    type_: str,
    key: str,
    *,
    label: str | None = None,
    project: str | None = None,
    attributes: dict | None = None,
    prov: Provenance = USER_STATED,
    sensitivity: str = "normal",
    retention: str = "durable",
    observed_at: str | None = None,
) -> dict:
    """Create or refresh an entity, returning the stored record.

    Re-observing an existing entity updates `last_confirmed` and merges new
    attributes rather than replacing the row: the second sighting of a file
    is evidence that it still exists, not a different file. An entity that
    had been expired is revived, because seeing it again is exactly the
    evidence that the expiry was wrong.
    """
    if type_ not in ENTITY_TYPES:
        raise ValidationError(f"unknown entity type {type_!r}; known: {sorted(ENTITY_TYPES)}")
    _check_sensitivity(sensitivity)
    _check_retention(retention)
    _init()

    now = observed_at or store.utc_now()
    eid = entity_id(type_, key, project)
    scope = None if type_ == "project" else project_id(project)
    attrs = dict(attributes or {})

    with store.transaction() as conn:
        existing = conn.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO entities (id, type, key, label, project_id, attributes, source,
                                      source_ref, origin, confidence, sensitivity, retention,
                                      observed_at, valid_from, valid_until, last_confirmed,
                                      superseded_by, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,NULL,?)
                """,
                (
                    eid, type_, key, label or key, scope, json.dumps(attrs), prov.source,
                    prov.source_ref, prov.origin, prov.confidence, sensitivity, retention,
                    now, now, now, now,
                ),
            )
        else:
            merged = _row_to_dict(existing)["attributes"]
            merged.update(attrs)
            # Keep the strongest provenance the entity has ever had: a file
            # first inferred from a window title and later read directly
            # should end up recorded as observed, not inferred.
            incoming = {"origin": prov.origin, "confidence": prov.confidence, "observed_at": now}
            keep_new = is_stronger(incoming, _row_to_dict(existing))
            conn.execute(
                """
                UPDATE entities
                   SET label = COALESCE(?, label),
                       attributes = ?,
                       source = CASE WHEN ? THEN ? ELSE source END,
                       source_ref = CASE WHEN ? THEN ? ELSE source_ref END,
                       origin = CASE WHEN ? THEN ? ELSE origin END,
                       confidence = CASE WHEN ? THEN ? ELSE confidence END,
                       observed_at = ?,
                       last_confirmed = ?,
                       valid_until = NULL,
                       superseded_by = NULL
                 WHERE id = ?
                """,
                (
                    label, json.dumps(merged),
                    keep_new, prov.source,
                    keep_new, prov.source_ref,
                    keep_new, prov.origin,
                    keep_new, prov.confidence,
                    now, now, eid,
                ),
            )
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
    return _row_to_dict(row)


def get_entity(entity: str) -> dict | None:
    """Fetch one entity by ID, or None."""
    _init()
    row = store.connect().execute("SELECT * FROM entities WHERE id = ?", (entity,)).fetchone()
    return _row_to_dict(row) if row else None


def find_entities(
    *,
    type_: str | None = None,
    project: str | None = None,
    key: str | None = None,
    key_like: str | None = None,
    include_expired: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Query entities by type/scope/key. Current entities only by default."""
    _init()
    clauses, params = [], []
    if type_:
        clauses.append("type = ?")
        params.append(type_)
    if project is not None:
        clauses.append("project_id = ?")
        params.append(project_id(project))
    if key is not None:
        clauses.append("key = ?")
        params.append(key)
    if key_like is not None:
        clauses.append("key LIKE ?")
        params.append(f"%{key_like}%")
    if not include_expired:
        clauses.append("valid_until IS NULL")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = store.connect().execute(
        f"SELECT * FROM entities {where} ORDER BY observed_at DESC LIMIT ?", params
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def confirm_entity(entity: str, at: str | None = None) -> bool:
    """Record that the entity was seen again without changing anything else."""
    _init()
    now = at or store.utc_now()
    with store.transaction() as conn:
        cur = conn.execute(
            "UPDATE entities SET last_confirmed = ?, valid_until = NULL WHERE id = ?", (now, entity)
        )
    return cur.rowcount > 0


def expire_entity(entity: str, *, at: str | None = None, superseded_by: str | None = None) -> bool:
    """Close an entity's validity interval — it existed, but no longer does.

    Not a delete: a file that was removed is still the correct answer to
    "what did I work on last week".
    """
    _init()
    now = at or store.utc_now()
    with store.transaction() as conn:
        cur = conn.execute(
            "UPDATE entities SET valid_until = ?, superseded_by = ? WHERE id = ? AND valid_until IS NULL",
            (now, superseded_by, entity),
        )
    return cur.rowcount > 0


def delete_entity(entity: str) -> int:
    """Hard-delete an entity and every edge touching it.

    Reserved for explicit user deletion ("forget this project"), where
    leaving history behind would violate the request rather than preserve
    truth. Returns the number of rows removed across both tables.
    """
    _init()
    with store.transaction() as conn:
        rels = conn.execute(
            "DELETE FROM relationships WHERE src_id = ? OR dst_id = ?", (entity, entity)
        ).rowcount
        ents = conn.execute("DELETE FROM entities WHERE id = ?", (entity,)).rowcount
    return rels + ents


# ── Relationships ────────────────────────────────────────────────────────────


def relate(
    src: str,
    rel: str,
    dst: str,
    *,
    project: str | None = None,
    attributes: dict | None = None,
    prov: Provenance = SYSTEM_OBSERVED,
    observed_at: str | None = None,
) -> dict:
    """Assert a typed edge between two entities.

    Idempotent: the same (src, rel, dst) triple maps to one stable row that
    is re-confirmed rather than duplicated, so re-indexing a repository does
    not multiply its edges.
    """
    if rel not in RELATIONSHIPS:
        raise ValidationError(f"unknown relationship {rel!r}; known: {sorted(RELATIONSHIPS)}")
    _init()
    now = observed_at or store.utc_now()
    rid = ids.stable_id("relationship", src, rel, dst)
    attrs = json.dumps(dict(attributes or {}))
    with store.transaction() as conn:
        existing = conn.execute("SELECT id FROM relationships WHERE id = ?", (rid,)).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO relationships (id, src_id, rel, dst_id, project_id, attributes,
                                           source, source_ref, origin, confidence, observed_at,
                                           valid_from, valid_until, last_confirmed, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?)
                """,
                (
                    rid, src, rel, dst, project_id(project), attrs, prov.source, prov.source_ref,
                    prov.origin, prov.confidence, now, now, now, now,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE relationships
                   SET attributes = ?, observed_at = ?, last_confirmed = ?, valid_until = NULL
                 WHERE id = ?
                """,
                (attrs, now, now, rid),
            )
        row = conn.execute("SELECT * FROM relationships WHERE id = ?", (rid,)).fetchone()
    return _row_to_dict(row)


def unrelate(src: str, rel: str, dst: str, *, hard: bool = False, at: str | None = None) -> bool:
    """Retract an edge — closed by default, hard-deleted on request."""
    _init()
    rid = ids.stable_id("relationship", src, rel, dst)
    with store.transaction() as conn:
        if hard:
            cur = conn.execute("DELETE FROM relationships WHERE id = ?", (rid,))
        else:
            cur = conn.execute(
                "UPDATE relationships SET valid_until = ? WHERE id = ? AND valid_until IS NULL",
                (at or store.utc_now(), rid),
            )
    return cur.rowcount > 0


def relations(
    entity: str,
    *,
    rel: str | None = None,
    direction: str = "both",
    include_expired: bool = False,
    limit: int = 200,
) -> list[dict]:
    """Edges touching an entity. `direction` is "out", "in" or "both"."""
    _init()
    if direction not in {"out", "in", "both"}:
        raise ValidationError(f"direction must be out/in/both, got {direction!r}")
    clauses, params = [], []
    if direction == "out":
        clauses.append("src_id = ?")
        params.append(entity)
    elif direction == "in":
        clauses.append("dst_id = ?")
        params.append(entity)
    else:
        clauses.append("(src_id = ? OR dst_id = ?)")
        params.extend([entity, entity])
    if rel:
        clauses.append("rel = ?")
        params.append(rel)
    if not include_expired:
        clauses.append("valid_until IS NULL")
    params.append(limit)
    rows = store.connect().execute(
        f"SELECT * FROM relationships WHERE {' AND '.join(clauses)} "
        f"ORDER BY observed_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def neighbors(
    entity: str, *, rel: str | None = None, direction: str = "out", limit: int = 200
) -> list[dict]:
    """The entities on the other end of an entity's edges.

    Edges pointing at entities the world model has never recorded are
    skipped rather than returned as holes — the graph can reference a symbol
    that was never upserted, and callers want entities, not dangling IDs.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for edge in relations(entity, rel=rel, direction=direction, limit=limit):
        other = edge["dst_id"] if edge["src_id"] == entity else edge["src_id"]
        if other in seen:
            continue
        seen.add(other)
        record = get_entity(other)
        if record is not None:
            record["via"] = edge["rel"]
            out.append(record)
    return out


# ── Facts ────────────────────────────────────────────────────────────────────


def _similar(a: str, b: str, threshold: float = CONFLICT_SIMILARITY) -> bool:
    """Cheap near-duplicate test, following V1's quick_ratio-first pattern."""
    matcher = SequenceMatcher(None, a, b)
    return matcher.quick_ratio() > threshold and matcher.ratio() > threshold


def _conflict_candidates(conn, *, scope: str | None, subject: str | None, slot: str | None):
    if slot:
        return conn.execute(
            """
            SELECT * FROM facts
             WHERE slot = ? AND valid_until IS NULL
               AND (project_id IS ? OR project_id = ?)
            """,
            (slot, scope, scope),
        ).fetchall()
    return conn.execute(
        """
        SELECT * FROM facts
         WHERE valid_until IS NULL
           AND (project_id IS ? OR project_id = ?)
           AND (? IS NULL OR subject_id = ?)
         ORDER BY observed_at DESC LIMIT ?
        """,
        (scope, scope, subject, subject, _CONFLICT_CANDIDATES),
    ).fetchall()


def record_fact(
    text: str,
    *,
    kind: str = "semantic",
    subject: str | None = None,
    project: str | None = None,
    slot: str | None = None,
    prov: Provenance = USER_STATED,
    sensitivity: str = "normal",
    retention: str = "durable",
    on_conflict: str = "auto",
    observed_at: str | None = None,
) -> dict:
    """Store a durable fact, resolving conflicts with what is already known.

    `slot` is the reliable conflict key: two facts sharing a slot within a
    scope are competing statements about the same property (say
    `package_manager` for a project), so a new one supersedes the old one
    outright. Without a slot, conflicts are detected by text similarity
    within the scope, which is softer and can miss.

    `on_conflict`:

    * ``"auto"`` (default) — supersede an existing fact when the new
      evidence is at least as strong; otherwise keep both and mark them
      disputed, because inventing a winner between two weak, contradictory
      beliefs is worse than admitting the uncertainty.
    * ``"supersede"`` — always win. For explicit user corrections.
    * ``"keep"`` — never supersede; just report what it collides with.

    Returns the stored fact with `superseded` and `disputed` lists naming
    the facts it acted on.
    """
    if kind not in FACT_KINDS:
        raise ValidationError(f"unknown fact kind {kind!r}; known: {sorted(FACT_KINDS)}")
    if on_conflict not in {"auto", "supersede", "keep"}:
        raise ValidationError(f"on_conflict must be auto/supersede/keep, got {on_conflict!r}")
    if not text or not text.strip():
        raise ValidationError("fact text must not be empty")
    _check_sensitivity(sensitivity)
    _check_retention(retention)
    _init()

    now = observed_at or store.utc_now()
    scope = project_id(project)
    fid = ids.new_id("memory")
    incoming = {"origin": prov.origin, "confidence": prov.confidence, "observed_at": now}

    superseded: list[str] = []
    disputed: list[str] = []

    with store.transaction() as conn:
        for row in _conflict_candidates(conn, scope=scope, subject=subject, slot=slot):
            candidate = _row_to_dict(row)
            if not slot and not _similar(text, candidate["text"]):
                continue
            if candidate["text"].strip() == text.strip():
                # Same statement restated: confirm it rather than creating a
                # second row that would then "conflict" with the first.
                conn.execute(
                    "UPDATE facts SET last_confirmed = ?, stale = 0, confidence = MAX(confidence, ?) "
                    "WHERE id = ?",
                    (now, prov.confidence, candidate["id"]),
                )
                row = conn.execute("SELECT * FROM facts WHERE id = ?", (candidate["id"],)).fetchone()
                result = _row_to_dict(row)
                result.update({"superseded": [], "disputed": [], "reconfirmed": True})
                return result
            if on_conflict == "keep":
                disputed.append(candidate["id"])
                continue
            if on_conflict == "supersede" or is_stronger(incoming, candidate):
                conn.execute(
                    "UPDATE facts SET valid_until = ?, superseded_by = ? WHERE id = ?",
                    (now, fid, candidate["id"]),
                )
                superseded.append(candidate["id"])
            else:
                conn.execute("UPDATE facts SET disputed = 1 WHERE id = ?", (candidate["id"],))
                disputed.append(candidate["id"])

        conn.execute(
            """
            INSERT INTO facts (id, text, kind, subject_id, project_id, slot, source, source_ref,
                               origin, confidence, sensitivity, retention, observed_at, valid_from,
                               valid_until, last_confirmed, superseded_by, supersedes, stale,
                               stale_reason, disputed, access_count, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,NULL,?,0,NULL,?,0,?)
            """,
            (
                fid, text.strip(), kind, subject, scope, slot, prov.source, prov.source_ref,
                prov.origin, prov.confidence, sensitivity, retention, now, now, now,
                json.dumps(superseded), 1 if disputed else 0, now,
            ),
        )
        row = conn.execute("SELECT * FROM facts WHERE id = ?", (fid,)).fetchone()

    result = _row_to_dict(row)
    result.update({"superseded": superseded, "disputed": disputed, "reconfirmed": False})
    if superseded:
        log.debug("fact %s superseded %s", fid, superseded)
    return result


def get_fact(fact_id: str) -> dict | None:
    """Fetch one fact by ID, or None."""
    _init()
    row = store.connect().execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
    return _row_to_dict(row) if row else None


def current_facts(
    *,
    project: str | None = None,
    subject: str | None = None,
    slot: str | None = None,
    kind: str | None = None,
    include_sensitive: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Facts believed to be true right now, strongest first.

    Superseded facts are excluded — this answers "what is true", not "what
    was ever believed". `include_sensitive` has to be asked for explicitly so
    that a secret cannot reach a prompt through a routine lookup.
    """
    _init()
    clauses = ["valid_until IS NULL"]
    params: list = []
    if project is not None:
        clauses.append("project_id = ?")
        params.append(project_id(project))
    if subject is not None:
        clauses.append("subject_id = ?")
        params.append(subject)
    if slot is not None:
        clauses.append("slot = ?")
        params.append(slot)
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    if not include_sensitive:
        clauses.append("sensitivity != 'secret'")
    params.append(limit)
    rows = store.connect().execute(
        f"SELECT * FROM facts WHERE {' AND '.join(clauses)} "
        f"ORDER BY stale ASC, observed_at DESC LIMIT ?",
        params,
    ).fetchall()
    records = [_row_to_dict(r) for r in rows]
    records.sort(key=strength, reverse=True)
    return records


def _fts_query(query: str) -> str | None:
    """Build a safe FTS5 MATCH expression from free text.

    Every term is double-quoted, which makes FTS5 treat it as a literal
    rather than syntax. V1 stripped punctuation with a regex instead, which
    silently dropped terms like `router.py` down to `routerpy`.
    """
    terms = [t for t in re.split(r"\W+", query or "") if t]
    if not terms:
        return None
    return " OR ".join(f'"{t}"' for t in terms)


def search_facts(
    query: str,
    *,
    project: str | None = None,
    kind: str | None = None,
    include_superseded: bool = False,
    include_sensitive: bool = False,
    limit: int = 8,
) -> list[dict]:
    """Full-text search over durable facts, ranked by BM25 then strength.

    Falls back to LIKE if the FTS index is unavailable, matching V1's
    behaviour: a degraded search beats an exception on the retrieval path.
    """
    _init()
    match = _fts_query(query)
    if match is None:
        return []

    clauses: list[str] = []
    params: list = [match]
    if not include_superseded:
        clauses.append("f.valid_until IS NULL")
    if project is not None:
        clauses.append("f.project_id = ?")
        params.append(project_id(project))
    if kind is not None:
        clauses.append("f.kind = ?")
        params.append(kind)
    if not include_sensitive:
        clauses.append("f.sensitivity != 'secret'")
    where = f"AND {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    conn = store.connect()
    try:
        rows = conn.execute(
            f"""
            SELECT f.* FROM facts_fts x JOIN facts f ON x.rowid = f.rowid
             WHERE facts_fts MATCH ? {where}
             ORDER BY bm25(facts_fts) LIMIT ?
            """,
            params,
        ).fetchall()
    except Exception as exc:  # pragma: no cover - depends on SQLite build
        log.warning("fact FTS search failed (%s); falling back to LIKE", exc)
        like_params = [f"%{query}%"] + params[1:]
        rows = conn.execute(
            f"SELECT f.* FROM facts f WHERE f.text LIKE ? {where} "
            f"ORDER BY f.observed_at DESC LIMIT ?",
            like_params,
        ).fetchall()

    records = [_row_to_dict(r) for r in rows]
    if records:
        with store.transaction() as write:
            write.executemany(
                "UPDATE facts SET access_count = access_count + 1 WHERE id = ?",
                [(r["id"],) for r in records],
            )
    records.sort(key=strength, reverse=True)
    return records


def mark_stale(fact_id: str, reason: str | None = None) -> bool:
    """Flag a fact as probably out of date without retracting it.

    Stale is not erased: the belief stays retrievable and keeps its history,
    but ranks below fresh evidence and can be surfaced with a caveat.
    """
    _init()
    with store.transaction() as conn:
        cur = conn.execute(
            "UPDATE facts SET stale = 1, stale_reason = ? WHERE id = ?", (reason, fact_id)
        )
    return cur.rowcount > 0


def forget(fact_id: str, *, mode: str = "supersede", at: str | None = None) -> bool:
    """Retire a fact.

    ``"supersede"`` closes its validity interval, keeping the historical
    record — the default, because most "forget that" requests mean "that is
    no longer true". ``"delete"`` removes the row outright, for when the
    user means the stronger thing.
    """
    if mode not in {"supersede", "delete"}:
        raise ValidationError(f"mode must be supersede/delete, got {mode!r}")
    _init()
    with store.transaction() as conn:
        if mode == "delete":
            cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        else:
            cur = conn.execute(
                "UPDATE facts SET valid_until = ? WHERE id = ? AND valid_until IS NULL",
                (at or store.utc_now(), fact_id),
            )
    return cur.rowcount > 0


def explain(fact_id: str) -> dict | None:
    """Answer "why do you remember that?" for one fact.

    Returns the belief with its provenance, its status (current, superseded,
    stale, disputed) and the chain of facts it replaced or was replaced by —
    never a reconstruction, only what was actually recorded.
    """
    record = get_fact(fact_id)
    if record is None:
        return None

    try:
        replaced = json.loads(record.get("supersedes") or "[]")
    except (TypeError, ValueError):
        replaced = []

    status = "current"
    if record["valid_until"]:
        status = "superseded" if record["superseded_by"] else "retracted"
    elif record["stale"]:
        status = "stale"
    elif record["disputed"]:
        status = "disputed"

    return {
        "id": record["id"],
        "text": record["text"],
        "status": status,
        "source": record["source"],
        "source_ref": record["source_ref"],
        "origin": record["origin"],
        "confidence": record["confidence"],
        "observed_at": record["observed_at"],
        "last_confirmed": record["last_confirmed"],
        "valid_from": record["valid_from"],
        "valid_until": record["valid_until"],
        "superseded_by": record["superseded_by"],
        "supersedes": replaced,
        "stale_reason": record["stale_reason"],
        "project_id": record["project_id"],
        "subject_id": record["subject_id"],
        "access_count": record["access_count"],
    }


def history(*, project: str | None = None, slot: str | None = None, limit: int = 50) -> list[dict]:
    """Every fact in a scope, current and superseded, newest first.

    The counterpart to :func:`current_facts`: "what have I believed about
    this over time", which is what makes a correction auditable.
    """
    _init()
    clauses, params = [], []
    if project is not None:
        clauses.append("project_id = ?")
        params.append(project_id(project))
    if slot is not None:
        clauses.append("slot = ?")
        params.append(slot)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = store.connect().execute(
        f"SELECT * FROM facts {where} ORDER BY observed_at DESC LIMIT ?", params
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def purge_project(project: str) -> dict:
    """Delete a project's world-model footprint, not just one table.

    "Delete this project from memory" has to cover the entities, the edges
    touching them and the scoped facts, or the project survives in whichever
    table was forgotten. Episodes, tool results and task state are purged by
    their own modules; the returned report names what this one removed.
    """
    _init()
    scope = project_id(project)
    with store.transaction() as conn:
        entity_rows = conn.execute(
            "SELECT id FROM entities WHERE project_id = ? OR id = ?", (scope, scope)
        ).fetchall()
        entity_ids = [r["id"] for r in entity_rows]
        rel_count = 0
        for eid in entity_ids:
            rel_count += conn.execute(
                "DELETE FROM relationships WHERE src_id = ? OR dst_id = ?", (eid, eid)
            ).rowcount
        rel_count += conn.execute(
            "DELETE FROM relationships WHERE project_id = ?", (scope,)
        ).rowcount
        fact_count = conn.execute("DELETE FROM facts WHERE project_id = ?", (scope,)).rowcount
        ent_count = conn.execute(
            "DELETE FROM entities WHERE project_id = ? OR id = ?", (scope, scope)
        ).rowcount
    return {
        "project_id": scope,
        "entities_deleted": ent_count,
        "relationships_deleted": rel_count,
        "facts_deleted": fact_count,
    }
