"""The context builder: turning a route into the smallest useful prompt.

    retrieved information
      ↓ relevance filtering
      ↓ deduplication
      ↓ provenance labels
      ↓ compression
      ↓ current task state
    minimal useful context → model

The target is the *minimum* context that preserves correctness, not the
maximum that fits. Everything selected here is competing for the same token
budget as the model's own reasoning, so a fragment earns its place by being
more useful than the one it displaces.

Every fragment carries its source, how it was arrived at, and an ID. That is
what lets an answer say "you told me this on Tuesday" rather than asserting
it, and what lets the model tell a recorded fact apart from its own earlier
guess.

Lexical search and file reading are injected rather than implemented: those
are V1 tools that already exist and already know this codebase's conventions.
This module decides *whether* to search and how much of the answer to keep —
not how to grep.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from primnox2.context.service import estimate_tokens
from v2 import episodes, graphify, router as routing, task_state, world_model

try:  # pragma: no cover - logging is incidental to behaviour
    from logger import get_logger

    log = get_logger("v2.context")
except Exception:  # pragma: no cover
    import logging

    log = logging.getLogger("v2.context")


DEFAULT_BUDGET_TOKENS = 1200

# Relative trust in each source when everything else is equal. Task state is
# first because what is happening now beats what was true last week; direct
# code evidence beats recalled memory for the same reason.
SOURCE_WEIGHT: dict[str, float] = {
    "task_state": 1.3,
    "graphify": 1.15,
    "search": 1.1,
    "read": 1.1,
    "memory": 1.0,
    "history": 0.95,
}

# How a fragment's origin scales its score. An inference has to be markedly
# more relevant than a recorded observation to outrank it.
ORIGIN_WEIGHT: dict[str, float] = {"stated": 1.15, "observed": 1.0, "inferred": 0.75, "exact": 1.15}

_FILE_TOKEN = re.compile(r"\b[\w./-]+\.(?:py|pyi|ts|tsx|js|jsx|json|md|toml|yaml|yml)\b")
_CALL_TOKEN = re.compile(r"\b([A-Za-z_][\w]*)\s*\(\s*\)")
_BACKTICKED = re.compile(r"`([^`]+)`")
_IDENTIFIER = re.compile(r"\b([a-z_][a-z0-9_]{3,}|[A-Z][a-zA-Z0-9]{2,})\b")

# Words that look like identifiers but are just English.
_STOPWORDS = {
    "about", "after", "again", "against", "before", "being", "between", "could", "does",
    "doing", "during", "each", "from", "have", "here", "into", "just", "like", "more",
    "most", "only", "other", "over", "same", "should", "some", "such", "than", "that",
    "their", "then", "there", "these", "they", "this", "those", "through", "under",
    "until", "very", "were", "what", "when", "where", "which", "while", "with", "would",
    "your", "file", "code", "function", "project", "change", "changed", "break", "breaks",
    "work", "working", "happen", "happened", "remember", "yesterday", "today", "still",
    "changes", "changing", "breaking", "failing", "using", "module", "something",
}

_TEMPORAL_TODAY = re.compile(r"\btoday\b|\bthis morning\b|\bthis afternoon\b", re.I)
_TEMPORAL_YESTERDAY = re.compile(r"\byesterday\b|\blast night\b", re.I)
_TEMPORAL_WEEK = re.compile(r"\blast week\b|\bthis week\b|\bfew days\b|\brecently\b|\blately\b", re.I)


@dataclass
class Fragment:
    """One piece of retrieved context, with the evidence for it."""

    kind: str
    text: str
    source: str
    origin: str = "observed"
    confidence: float = 0.8
    ref: str | None = None
    detail: str | None = None
    score: float = 0.0

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.render())

    def render(self) -> str:
        """One line, prefixed with where it came from and how sure it is."""
        tag = f"{self.source}"
        if self.origin and self.origin != "observed":
            tag += f" · {self.origin}"
        if self.ref:
            tag += f" · {self.ref}"
        return f"[{tag}] {self.text}"


@dataclass
class Context:
    """The assembled context, and an account of what was left out."""

    question: str
    route: routing.Route
    fragments: list[Fragment] = field(default_factory=list)
    dropped: int = 0
    budget_tokens: int = DEFAULT_BUDGET_TOKENS
    notes: list[str] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(f.tokens for f in self.fragments)

    def render(self) -> str:
        """The context block for the prompt, grouped by source."""
        if not self.fragments:
            return ""
        grouped: dict[str, list[Fragment]] = {}
        for fragment in self.fragments:
            grouped.setdefault(fragment.source, []).append(fragment)

        lines: list[str] = []
        for source in sorted(grouped, key=lambda s: -SOURCE_WEIGHT.get(s, 1.0)):
            lines.append(f"── {source} ──")
            lines += [f.render() for f in grouped[source]]
        if self.dropped:
            lines.append(f"({self.dropped} lower-ranked item(s) omitted; ask to retrieve more)")
        return "\n".join(lines)

    def provenance(self) -> list[dict]:
        """Machine-readable provenance for everything included."""
        return [
            {
                "kind": f.kind,
                "source": f.source,
                "origin": f.origin,
                "confidence": f.confidence,
                "ref": f.ref,
                "text": f.text,
            }
            for f in self.fragments
        ]


# ── Question analysis ────────────────────────────────────────────────────────


def extract_targets(question: str) -> dict:
    """Pull the code-ish things a structural query needs out of the question.

    Ordered by how explicit the mention was: a backticked or parenthesised
    name is unambiguous, a bare identifier is a guess. Graph queries try the
    explicit ones first so a stray English word does not become the subject
    of an impact analysis.
    """
    text = question or ""
    files = [m.group(0) for m in _FILE_TOKEN.finditer(text)]
    calls = _CALL_TOKEN.findall(text)
    quoted = [q.strip() for q in _BACKTICKED.findall(text)]

    identifiers: list[str] = []
    for match in _IDENTIFIER.finditer(text):
        word = match.group(1)
        if word.lower() in _STOPWORDS or word in identifiers:
            continue
        identifiers.append(word)

    explicit = [*quoted, *calls, *files]
    return {
        "files": files,
        "symbols": [*calls, *[q for q in quoted if "." not in q]],
        "explicit": explicit,
        "identifiers": identifiers,
    }


def temporal_window(question: str, *, now=None):
    """The time window a temporal question is asking about, if any."""
    text = question or ""
    if _TEMPORAL_YESTERDAY.search(text):
        return episodes.local_day_bounds(1, now=now)
    if _TEMPORAL_TODAY.search(text):
        return episodes.local_day_bounds(0, now=now)
    if _TEMPORAL_WEEK.search(text):
        start, _ = episodes.local_day_bounds(7, now=now)
        _, end = episodes.local_day_bounds(0, now=now)
        return start, end
    return None


# ── Per-source retrieval ─────────────────────────────────────────────────────


def _from_memory(question: str, project: str | None, limit: int) -> list[Fragment]:
    fragments: list[Fragment] = []
    for fact in world_model.search_facts(question, project=project, limit=limit):
        fragments.append(
            Fragment(
                kind="fact",
                text=fact["text"] + (" (marked stale)" if fact["stale"] else ""),
                source="memory",
                origin=fact["origin"],
                confidence=fact["confidence"],
                ref=fact["id"],
            )
        )
    if not fragments:
        for fact in world_model.current_facts(project=project, limit=limit):
            fragments.append(
                Fragment(
                    kind="fact", text=fact["text"], source="memory", origin=fact["origin"],
                    confidence=fact["confidence"], ref=fact["id"],
                )
            )
    return fragments


def _from_history(question: str, project: str | None, limit: int, now=None) -> list[Fragment]:
    fragments: list[Fragment] = []
    window = temporal_window(question, now=now)
    if window:
        reconstructed = episodes.timeline(window[0], window[1], project=project, max_entries=limit)
        for entry in reconstructed["entries"]:
            when = entry["started_at"][11:16]
            fragments.append(
                Fragment(
                    kind=entry["type"],
                    text=f"{when} — {entry['summary']}",
                    source="history",
                    origin=entry["origin"],
                    confidence=entry["confidence"],
                    ref=entry["id"],
                )
            )
        if reconstructed["truncated"]:
            fragments.append(
                Fragment(
                    kind="note",
                    text=f"{reconstructed['total_entries']} entries in this period; showing the most significant",
                    source="history", origin="observed", confidence=1.0,
                )
            )
        return fragments

    for event in episodes.recall(question, project=project, limit=limit):
        fragments.append(
            Fragment(
                kind="event",
                text=f"{event['occurred_at'][:16].replace('T', ' ')} — {event['summary']}",
                source="history", origin=event["origin"], confidence=event["confidence"],
                ref=event["result_ref"] or event["id"],
            )
        )
    return fragments


def _from_task_state(project: str | None, session: str | None, task: str | None) -> list[Fragment]:
    record = task_state.get(task) if task else task_state.resume(project=project, session=session)
    if record is None:
        return []
    rendered = task_state.render(record["id"])
    if not rendered:
        return []
    return [
        Fragment(
            kind="task", text=rendered, source="task_state", origin="observed",
            confidence=1.0, ref=record["id"],
        )
    ]


def _from_graph(question: str, project: str | None, limit: int) -> list[Fragment]:
    targets = extract_targets(question)
    fragments: list[Fragment] = []

    candidates = targets["explicit"] or targets["identifiers"][:3]
    for candidate in candidates[:3]:
        name = candidate.split("(")[0].strip()
        for caller in graphify.callers(name, project=project, limit=limit):
            fragments.append(
                Fragment(
                    kind="caller",
                    text=f"{caller['caller'] or caller['rel_path']} calls {name} "
                         f"({caller['rel_path']}:{caller['line']})"
                         + (" — index stale" if caller["stale"] else ""),
                    source="graphify",
                    origin="exact" if caller["confidence"] >= 1.0 else "inferred",
                    confidence=caller["confidence"],
                    ref=f"{caller['rel_path']}:{caller['line']}",
                )
            )
        for dependent in graphify.dependents(name, project=project, limit=limit):
            fragments.append(
                Fragment(
                    kind="dependent",
                    text=f"{dependent['rel_path']} imports {name}"
                         + (" — index stale" if dependent["stale"] else ""),
                    source="graphify",
                    origin="exact" if dependent["confidence"] >= 1.0 else "inferred",
                    confidence=dependent["confidence"],
                    ref=dependent["rel_path"],
                )
            )
        if fragments:
            break
    return fragments


def _from_callable(hook, question: str, kind: str, source: str, limit: int) -> list[Fragment]:
    """Adapt an injected search/read tool into fragments.

    Accepts a list of strings or of dicts with `text`/`ref`, because the
    caller's tool should not have to know this module's shapes.
    """
    if hook is None:
        return []
    try:
        results = hook(question) or []
    except Exception as exc:
        log.warning("%s hook failed (%s); continuing without it", source, exc)
        return []

    fragments: list[Fragment] = []
    for item in list(results)[:limit]:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("summary") or "").strip()
            ref = item.get("ref") or item.get("path") or item.get("result_id")
            confidence = float(item.get("confidence", 0.9))
        else:
            text, ref, confidence = str(item).strip(), None, 0.9
        if text:
            fragments.append(
                Fragment(kind=kind, text=text, source=source, origin="observed",
                         confidence=confidence, ref=ref)
            )
    return fragments


# ── Assembly ─────────────────────────────────────────────────────────────────


def _normalise(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def build(
    question: str,
    *,
    project: str | None = None,
    session: str | None = None,
    task: str | None = None,
    route: routing.Route | None = None,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
    per_source_limit: int = 6,
    searcher=None,
    reader=None,
    now=None,
) -> Context:
    """Retrieve, rank, dedupe and compress context for one request.

    `searcher` and `reader` are the injection points for V1's lexical search
    and file/artifact reading. When a route selects a source with no hook
    wired up, that is recorded in `notes` rather than silently producing an
    answer built from less evidence than the router asked for.
    """
    decision = route or routing.route(question)
    context = Context(question=question, route=decision, budget_tokens=budget_tokens)

    collected: list[Fragment] = []
    for source in decision.sources:
        if source == "M":
            collected += _from_memory(question, project, per_source_limit)
        elif source == "H":
            collected += _from_history(question, project, per_source_limit, now=now)
        elif source == "T":
            collected += _from_task_state(project, session, task)
        elif source == "G":
            collected += _from_graph(question, project, per_source_limit)
        elif source == "S":
            if searcher is None:
                context.notes.append("lexical search was selected but no searcher is wired up")
            collected += _from_callable(searcher, question, "match", "search", per_source_limit)
        elif source == "R":
            if reader is None:
                context.notes.append("a document read was selected but no reader is wired up")
            collected += _from_callable(reader, question, "document", "read", per_source_limit)

    # Rank: how trusted the source is, how the belief was arrived at, and how
    # confident the record itself was.
    for fragment in collected:
        fragment.score = (
            SOURCE_WEIGHT.get(fragment.source, 1.0)
            * ORIGIN_WEIGHT.get(fragment.origin, 1.0)
            * max(0.05, fragment.confidence)
        )
    collected.sort(key=lambda f: f.score, reverse=True)

    # Dedupe: the same statement reached through two sources is one piece of
    # evidence, and the higher-ranked path already carries it.
    seen: set[str] = set()
    unique: list[Fragment] = []
    for fragment in collected:
        key = _normalise(fragment.text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(fragment)

    # Compress: fill the budget with the best fragments and count the rest.
    used = 0
    for fragment in unique:
        cost = fragment.tokens
        if used + cost > budget_tokens and context.fragments:
            context.dropped += 1
            continue
        context.fragments.append(fragment)
        used += cost

    return context
