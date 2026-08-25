"""Stable typed IDs — the bridge between V2 subsystems.

Memory, the world model, the graph, artifacts, tool results and execution
state all have to be able to point at the same thing. A shared ID scheme is
what makes "memory M184 was derived from tool result res_ab12 while working
on task_9f30, which touched file ent_c4e1" expressible at all.

Two kinds of ID exist here, and the difference matters:

* :func:`stable_id` is **derived** from a natural key. Observing the same
  file, symbol or project twice produces the same ID, in this process or a
  later one, without a database round-trip. That is what lets an entity be
  upserted rather than duplicated every time it is seen.
* :func:`new_id` is **random**. Events, episodes and audit records are
  distinct occurrences even when their content is identical — two identical
  test runs a minute apart are two events, not one — so they must not
  collide.

The prefix is part of the ID rather than a separate column so that a bare ID
travelling through a log line, a prompt or a JSON blob still says what it
points at.
"""

from __future__ import annotations

import hashlib
import uuid

# Short, greppable prefixes. Keys of this map are the canonical "kind" names
# used across V2; the values are what actually appears in the ID string.
PREFIXES: dict[str, str] = {
    "entity": "ent",
    "relationship": "rel",
    "event": "evt",
    "episode": "epi",
    "memory": "mem",
    "result": "res",
    "task": "task",
    "artifact": "art",
    "credential": "cred",
    "audit": "aud",
    "conversation": "conv",
    "index": "idx",
}

# 16 hex chars ≈ 64 bits. Enough that a derived ID collision is not a
# practical concern for a single user's world model, short enough to stay
# readable in a prompt or log line.
_DIGEST_CHARS = 16


class UnknownKindError(ValueError):
    """Raised for an ID kind that is not in :data:`PREFIXES`.

    Deliberately loud: a typo'd kind would otherwise silently create a
    parallel namespace ("entty_...") that nothing else in V2 can resolve.
    """


def prefix_for(kind: str) -> str:
    """Return the ID prefix for `kind`, raising on an unknown kind."""
    try:
        return PREFIXES[kind]
    except KeyError:
        raise UnknownKindError(
            f"unknown ID kind {kind!r}; known kinds: {sorted(PREFIXES)}"
        ) from None


def stable_id(kind: str, *parts: object) -> str:
    """Deterministic ID derived from a natural key.

    The same `kind` and `parts` always produce the same ID. Parts are joined
    with a NUL byte, which cannot appear in the path/name strings V2 uses as
    natural keys, so ("a", "b:c") and ("a:b", "c") cannot collide the way
    they would under a colon separator.

    `None` parts are preserved as a distinct empty slot rather than being
    dropped, so `stable_id("entity", "file", None)` and
    `stable_id("entity", "file")` stay different IDs.
    """
    pre = prefix_for(kind)
    joined = "\x00".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]
    return f"{pre}_{digest}"


def new_id(kind: str) -> str:
    """Random ID for something that is a distinct occurrence, not a thing.

    Uses uuid4 rather than a counter so IDs stay unique across processes,
    threads and restarts without any shared state to coordinate.
    """
    pre = prefix_for(kind)
    return f"{pre}_{uuid.uuid4().hex[:_DIGEST_CHARS]}"


def content_id(kind: str, content: str) -> str:
    """ID derived from a full content string.

    Used where identity *is* the content — most importantly the tool result
    store, where two byte-identical results should resolve to one stored
    record instead of being transmitted and stored twice.
    """
    pre = prefix_for(kind)
    digest = hashlib.sha256(content.encode("utf-8", "replace")).hexdigest()[:_DIGEST_CHARS]
    return f"{pre}_{digest}"


def kind_of(identifier: str) -> str | None:
    """Reverse-map an ID to its kind, or None if the prefix is unrecognised.

    Returns None rather than raising: this is used on IDs arriving from
    stored data and model output, where an unrecognised string is an
    expected input, not a programming error.
    """
    if not identifier or "_" not in identifier:
        return None
    pre = identifier.split("_", 1)[0]
    for kind, candidate in PREFIXES.items():
        if candidate == pre:
            return kind
    return None


def is_id(identifier: object, kind: str | None = None) -> bool:
    """True if `identifier` looks like a V2 ID (optionally of a given kind).

    A shape check, not a existence check — it says nothing about whether the
    referenced record is actually in the database.
    """
    if not isinstance(identifier, str):
        return False
    found = kind_of(identifier)
    if found is None:
        return False
    if kind is not None and found != kind:
        return False
    suffix = identifier.split("_", 1)[1]
    return len(suffix) == _DIGEST_CHARS and all(c in "0123456789abcdef" for c in suffix)
