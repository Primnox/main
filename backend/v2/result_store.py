"""Tool results kept out of the transcript.

The measured shape of the cost problem is not that individual results are
too big — it is that every step carries all previous results forward:

    step 1: question + result₁
    step 2: question + result₁ + result₂
    step 3: question + result₁ + result₂ + result₃

So an 8-step turn does not cost 8× a 1-step turn; it costs far more. The fix
is structural: the model receives a compact observation plus a stable ID, and
the full result lives here. If a later step actually needs the detail, it
fetches it — by ID, on purpose, once — instead of paying for it on every
turn from then on.

    tool call
      ↓
    full result ──→ result store ──→ res_ab12…
      ↓
    compact observation ──→ model

Three properties this has to get right:

* **The observation must be honest.** It says what the result contained and
  how much was left out, so the model can tell the difference between "the
  answer is here" and "the answer is in the part you did not get".
* **Repeats must not be re-transmitted.** The same tool returning the same
  bytes resolves to the same stored record, and the observation says so
  rather than spending the budget again.
* **Secrets must not leak into a summary.** A result marked secret is stored
  and referenced, but its content never appears in the observation — the
  model gets shape and size, and an authorised path fetches the value.
"""

from __future__ import annotations

import json
import re

from primnox2.context.service import estimate_tokens
from v2 import ids, store
from v2.world_model import ValidationError, project_id

try:  # pragma: no cover - logging is incidental to behaviour
    from logger import get_logger

    log = get_logger("v2.result_store")
except Exception:  # pragma: no cover
    import logging

    log = logging.getLogger("v2.result_store")


# Token budget for a compact observation. Sized to be a few sentences plus a
# sample — enough for the model to decide whether it needs the full result,
# not enough to reintroduce the problem this module exists to solve.
DEFAULT_OBSERVATION_TOKENS = 200

# How many lines of a multi-line result are shown before eliding.
_HEAD_LINES = 12
_TAIL_LINES = 6

# Results that look like failures are summarised from the end rather than the
# start: a traceback's useful line is the last one, and a head-only summary of
# a stack trace is the least informative possible excerpt.
_FAILURE_MARKERS = re.compile(
    r"traceback \(most recent call last\)|^\s*(error|fatal|exception)\b|\berror:", re.I | re.M
)

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS results (
        id             TEXT PRIMARY KEY,
        tool           TEXT NOT NULL,
        args           TEXT,
        content        TEXT NOT NULL,
        content_tokens INTEGER NOT NULL,
        content_bytes  INTEGER NOT NULL,
        line_count     INTEGER NOT NULL,
        observation    TEXT NOT NULL,
        shape          TEXT NOT NULL,
        session_id     TEXT,
        task_id        TEXT,
        project_id     TEXT,
        sensitivity    TEXT NOT NULL DEFAULT 'normal',
        retention      TEXT NOT NULL DEFAULT 'session',
        hits           INTEGER NOT NULL DEFAULT 1,
        created_at     TEXT NOT NULL,
        last_used_at   TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_results_session ON results(session_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_results_created ON results(created_at)",
]


def _init() -> None:
    store.ensure_schema("result_store", _SCHEMA)


# ── Normalisation and shape detection ────────────────────────────────────────


def _to_text(result: object) -> tuple[str, str]:
    """Return `(text, shape)` for any tool return value.

    Shape is one of "json", "lines", "text" and decides how the observation
    is built. Structured results get a structural summary; flat text gets an
    excerpt.
    """
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, ensure_ascii=False, default=str), "json"
        except (TypeError, ValueError):
            return str(result), "text"

    text = result if isinstance(result, str) else str(result)
    stripped = text.strip()
    if stripped[:1] in "{[" and stripped[-1:] in "}]":
        try:
            json.loads(stripped)
            return text, "json"
        except ValueError:
            pass
    return text, ("lines" if text.count("\n") >= 2 else "text")


def _describe_json(text: str, budget_tokens: int) -> str:
    """Summarise a structured result by its shape, not its bytes.

    "47 items, keys: path, line, match" tells the model what it is holding
    and whether it needs more, in a fraction of the tokens the array costs.
    """
    try:
        data = json.loads(text)
    except ValueError:  # pragma: no cover - _to_text already validated
        return _excerpt(text, budget_tokens)

    if isinstance(data, list):
        head = data[:3]
        keys: list[str] = []
        for item in data[:20]:
            if isinstance(item, dict):
                for key in item:
                    if key not in keys:
                        keys.append(key)
        parts = [f"list of {len(data)} item{'s' if len(data) != 1 else ''}"]
        if keys:
            parts.append(f"keys: {', '.join(keys[:8])}")
        sample = json.dumps(head, ensure_ascii=False, default=str)
        return f"{'; '.join(parts)}\nfirst {len(head)}: {_excerpt(sample, max(20, budget_tokens - 30))}"

    if isinstance(data, dict):
        keys = list(data)
        sample = {k: data[k] for k in keys[:6]}
        rendered = json.dumps(sample, ensure_ascii=False, default=str)
        return (
            f"object with {len(keys)} key{'s' if len(keys) != 1 else ''}: {', '.join(keys[:10])}\n"
            f"{_excerpt(rendered, max(20, budget_tokens - 30))}"
        )

    return _excerpt(text, budget_tokens)


def _excerpt(text: str, budget_tokens: int) -> str:
    """Trim text to a token budget, marking where the cut happened."""
    if estimate_tokens(text) <= budget_tokens:
        return text
    # estimate_tokens is ~4 chars/token; convert the budget back to a char
    # count and leave room for the elision marker.
    budget_chars = max(40, budget_tokens * 4 - 20)
    return f"{text[:budget_chars].rstrip()}…[truncated]"


def _describe_lines(text: str, budget_tokens: int) -> str:
    """Summarise a multi-line result as head (or tail, on failures) + count."""
    lines = text.splitlines()
    failure = bool(_FAILURE_MARKERS.search(text))

    if failure:
        shown = lines[-_TAIL_LINES:]
        prefix = f"{len(lines)} lines, ends with:"
    else:
        shown = lines[:_HEAD_LINES]
        prefix = f"{len(lines)} lines, starts with:"

    body = "\n".join(shown)
    hidden = len(lines) - len(shown)
    suffix = f"\n…{hidden} more line{'s' if hidden != 1 else ''} in the full result" if hidden > 0 else ""
    return _excerpt(f"{prefix}\n{body}", budget_tokens) + suffix


def summarize(result: object, *, budget_tokens: int = DEFAULT_OBSERVATION_TOKENS) -> str:
    """Build a compact observation for a result without storing anything.

    Exposed on its own so callers can preview what the model would see, and
    so the summarisation rules can be tested independently of storage.
    """
    text, shape = _to_text(result)
    if not text.strip():
        return "(empty result)"
    if shape == "json":
        return _describe_json(text, budget_tokens)
    if shape == "lines":
        return _describe_lines(text, budget_tokens)
    return _excerpt(text, budget_tokens)


# ── Storing and retrieving ───────────────────────────────────────────────────


def put(
    tool: str,
    result: object,
    *,
    args: dict | None = None,
    session: str | None = None,
    task: str | None = None,
    project: str | None = None,
    sensitivity: str = "normal",
    retention: str = "session",
    budget_tokens: int = DEFAULT_OBSERVATION_TOKENS,
) -> dict:
    """Store a full tool result and return what the model should see.

    The returned dict carries `observation` (compact text destined for the
    transcript), `result_id` (how to get the rest), and the token accounting
    that makes the saving measurable rather than assumed.

    A byte-identical result from the same tool resolves to the existing
    record: `duplicate` is True and the observation points at the ID the
    model has already seen, so a repeated result costs a reference instead of
    a second full summary.
    """
    if not tool:
        raise ValidationError("tool name is required")
    _init()

    text, shape = _to_text(result)
    now = store.utc_now()
    result_id = ids.content_id("result", f"{tool}\x00{text}")
    tokens = estimate_tokens(text)

    if sensitivity == "secret":
        # Shape and size only. The value is retrievable by ID through an
        # authorised path; it must never reach the transcript as a "summary".
        observation = (
            f"[withheld — {tool} returned a secret value, "
            f"{len(text)} bytes; reference {result_id}]"
        )
    else:
        observation = summarize(result, budget_tokens=budget_tokens)

    with store.transaction() as conn:
        existing = conn.execute("SELECT * FROM results WHERE id = ?", (result_id,)).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE results SET hits = hits + 1, last_used_at = ? WHERE id = ?", (now, result_id)
            )
            return {
                "result_id": result_id,
                "observation": f"[identical to {result_id}, already retrieved — reuse that result]",
                "duplicate": True,
                "full_tokens": existing["content_tokens"],
                "observation_tokens": estimate_tokens(existing["observation"]),
                "truncated": existing["content_tokens"] > estimate_tokens(existing["observation"]),
                "shape": existing["shape"],
                "tool": tool,
            }

        conn.execute(
            """
            INSERT INTO results (id, tool, args, content, content_tokens, content_bytes,
                                 line_count, observation, shape, session_id, task_id, project_id,
                                 sensitivity, retention, hits, created_at, last_used_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
            """,
            (
                result_id, tool, json.dumps(args or {}, default=str), text, tokens, len(text),
                text.count("\n") + 1 if text else 0, observation, shape, session, task,
                project_id(project), sensitivity, retention, now, now,
            ),
        )

    observation_tokens = estimate_tokens(observation)
    return {
        "result_id": result_id,
        "observation": observation,
        "duplicate": False,
        "full_tokens": tokens,
        "observation_tokens": observation_tokens,
        "truncated": observation_tokens < tokens,
        "shape": shape,
        "tool": tool,
    }


def reference(observation: dict | str, result_id: str | None = None) -> str:
    """Render an observation for the transcript with its retrieval handle.

    Kept separate from :func:`put` so a caller can decide where the handle
    appears in its own message format, but the default rendering is here so
    every call site is not inventing its own.
    """
    if isinstance(observation, dict):
        result_id = observation["result_id"]
        text = observation["observation"]
        if observation.get("truncated") and not observation.get("duplicate"):
            return f"{text}\n[full result: {result_id} · {observation['full_tokens']} tokens]"
        return f"{text}\n[result: {result_id}]"
    return f"{observation}\n[result: {result_id}]" if result_id else str(observation)


def get(result_id: str, *, mark_used: bool = True) -> str | None:
    """The full stored result, or None if it is not (or no longer) here."""
    _init()
    row = store.connect().execute("SELECT content FROM results WHERE id = ?", (result_id,)).fetchone()
    if row is None:
        return None
    if mark_used:
        with store.transaction() as conn:
            conn.execute(
                "UPDATE results SET last_used_at = ? WHERE id = ?", (store.utc_now(), result_id)
            )
    return row["content"]


def info(result_id: str) -> dict | None:
    """Metadata about a stored result without loading its content."""
    _init()
    row = store.connect().execute(
        """
        SELECT id, tool, args, content_tokens, content_bytes, line_count, observation, shape,
               session_id, task_id, project_id, sensitivity, retention, hits, created_at,
               last_used_at
          FROM results WHERE id = ?
        """,
        (result_id,),
    ).fetchone()
    return dict(row) if row else None


def _find(lines: list[str], query: str) -> list[int]:
    """Line indices matching `query` as a regex, falling back to literal text.

    Tried in that order rather than the reverse because a caller that means
    a pattern (`def \\w+_router`) gets what it asked for, while a caller that
    meant literal text still finds it on the second pass.
    """
    def scan(pattern: re.Pattern) -> list[int]:
        return [i for i, line in enumerate(lines) if pattern.search(line)]

    try:
        hits = scan(re.compile(query, re.I))
    except re.error:
        hits = []
    if hits:
        return hits
    literal = re.escape(query)
    if literal == query:
        return hits
    return scan(re.compile(literal, re.I))


def section(
    result_id: str,
    query: str,
    *,
    context_lines: int = 2,
    max_matches: int = 20,
    budget_tokens: int = 400,
) -> dict | None:
    """Pull just the relevant part of a stored result back into context.

    "The dependency report from earlier mentioned a circular import" should
    cost the matching lines and their neighbours, not the whole report. This
    is what makes external storage recoverable rather than merely cheap.

    `query` is treated as a regular expression, then retried as literal text
    if that finds nothing. A query written by a model is as likely to be a
    filename or a snippet of prose as a pattern, and `items[0]` is a valid
    regex that matches neither itself nor anything else useful.
    """
    content = get(result_id)
    if content is None:
        return None

    lines = content.splitlines()
    hits = _find(lines, query)
    if not hits:
        return {"result_id": result_id, "matches": 0, "text": "", "truncated": False}

    wanted: set[int] = set()
    for index in hits[:max_matches]:
        wanted.update(range(max(0, index - context_lines), min(len(lines), index + context_lines + 1)))

    selected = sorted(wanted)
    chunks: list[str] = []
    previous: int | None = None
    for index in selected:
        if previous is not None and index != previous + 1:
            chunks.append("…")
        chunks.append(lines[index])
        previous = index

    text = "\n".join(chunks)
    trimmed = _excerpt(text, budget_tokens)
    return {
        "result_id": result_id,
        "matches": len(hits),
        "text": trimmed,
        "truncated": trimmed != text or len(hits) > max_matches,
    }


def head(result_id: str, lines: int = 20) -> str | None:
    """First `lines` lines of a stored result."""
    content = get(result_id)
    if content is None:
        return None
    return "\n".join(content.splitlines()[:lines])


# ── Retention ────────────────────────────────────────────────────────────────


def forget_session(session: str) -> int:
    """Delete results captured under a session."""
    _init()
    with store.transaction() as conn:
        return conn.execute("DELETE FROM results WHERE session_id = ?", (session,)).rowcount


def purge_project(project: str) -> dict:
    """Delete results captured under a project."""
    _init()
    scope = project_id(project)
    with store.transaction() as conn:
        deleted = conn.execute("DELETE FROM results WHERE project_id = ?", (scope,)).rowcount
    return {"project_id": scope, "results_deleted": deleted}


def prune(*, keep_days: int = 14, keep_durable: bool = True) -> int:
    """Drop old results that nothing is holding on to.

    Results are working data, not memory: what is worth remembering about a
    tool run should have become an event or a fact by now. `keep_durable`
    spares anything explicitly stored with `retention="durable"`, which is
    how a result that an artifact or memory cites is protected from expiry.
    """
    _init()
    cutoff = store.parse_time(store.utc_now())
    if cutoff is None:  # pragma: no cover - utc_now is always parseable
        return 0
    from datetime import timedelta

    threshold = (cutoff - timedelta(days=keep_days)).isoformat()
    clause = "AND retention != 'durable'" if keep_durable else ""
    with store.transaction() as conn:
        return conn.execute(
            f"DELETE FROM results WHERE last_used_at < ? {clause}", (threshold,)
        ).rowcount


def stats(*, session: str | None = None) -> dict:
    """Aggregate accounting — how much context this store kept out of prompts.

    `tokens_saved` is the honest version of the number: full result tokens
    minus what the observations actually cost, counted once per stored
    result plus once more for every repeat that was answered by reference.
    """
    _init()
    clause, params = ("WHERE session_id = ?", [session]) if session else ("", [])
    row = store.connect().execute(
        f"""
        SELECT COUNT(*) AS results,
               COALESCE(SUM(content_tokens), 0) AS full_tokens,
               COALESCE(SUM(hits), 0) AS hits,
               COALESCE(SUM(content_bytes), 0) AS bytes
          FROM results {clause}
        """,
        params,
    ).fetchone()

    observation_rows = store.connect().execute(
        f"SELECT observation, content_tokens, hits FROM results {clause}", params
    ).fetchall()
    observation_tokens = sum(estimate_tokens(r["observation"]) for r in observation_rows)
    saved = sum(
        (r["content_tokens"] - estimate_tokens(r["observation"]))
        + max(0, r["hits"] - 1) * r["content_tokens"]
        for r in observation_rows
    )

    return {
        "results": row["results"],
        "hits": row["hits"],
        "bytes": row["bytes"],
        "full_tokens": row["full_tokens"],
        "observation_tokens": observation_tokens,
        "tokens_saved": max(0, saved),
    }
