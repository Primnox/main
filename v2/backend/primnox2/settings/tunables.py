"""Declared tunables.

Every number in this system that someone might reasonably want to change lives
here, with a default, a range, and a sentence saying what moving it costs. The
alternative — a constant at the top of whichever module needed it — has three
failure modes this file exists to remove:

  It is invisible. Nobody knows `history_limit` is 100 until a 500-turn
  conversation loses the turn the user cited. Crucible found exactly that, and
  the fix was a number nobody had ever looked at.

  It cannot be changed without a rebuild. A user on a 200k-context model is
  held to limits chosen for a 32k one.

  It has no stated cost. A constant says what; it rarely says what happens if
  you double it, which is the only thing the person changing it wants to know.

WHAT IS NOT HERE. Genuine constants — the 8-point grid, EMU-per-point, Win32
error codes, the WCAG contrast floor. Those are facts or design decisions, not
knobs, and making them settable would invite someone to produce a deck that is
off-grid on purpose.

RESOLUTION ORDER. Environment variable, then stored setting, then default. The
environment wins because it is what an operator set deliberately for this
process; the stored value is what someone chose in the UI months ago.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass

from ..storage import db

now_ms = lambda: int(time.time() * 1000)


@dataclass(frozen=True)
class Tunable:
    key: str
    default: float | int
    kind: type
    minimum: float | int
    maximum: float | int
    summary: str
    cost: str            # what moving it actually costs

    @property
    def env(self) -> str:
        return "PRIMNOX2_" + self.key.replace(".", "_").upper()

    def clamp(self, value):
        return max(self.minimum, min(self.maximum, self.kind(value)))


def _t(*args, **kwargs) -> Tunable:
    return Tunable(*args, **kwargs)


REGISTRY: dict[str, Tunable] = {t.key: t for t in [
    # ── Context ──────────────────────────────────────────────────────────
    _t("context.history_turns", 2000, int, 10, 100_000,
       "Hard cap on turns fetched for history.",
       "A safety valve only — truncation should come from the token budget. "
       "Set it low and a conversation silently loses the turns a user cites by "
       "number; that was a critical Crucible finding at the old value of 100."),
    _t("context.chars_per_token", 3.5, float, 2.0, 8.0,
       "Characters per token, for budget estimation.",
       "Too high and prompts are rejected by the provider; too low and the "
       "window is under-used. Conservative beats accurate."),
    _t("context.output_reserve", 0.25, float, 0.05, 0.6,
       "Share of the window held back for the reply.",
       "Too small and long answers are cut off mid-sentence."),
    _t("context.asset_share", 0.2, float, 0.0, 0.9,
       "Max share of the remaining budget spent on raw asset text.",
       "Raw text is the fallback for documents the graph has not indexed. "
       "Raising it re-creates the problem the graph exists to solve."),
    _t("context.graph_share", 0.35, float, 0.0, 0.9,
       "Share of the remaining budget for knowledge-graph retrieval.",
       "This is the primary retrieval path. Zero disables it and returns the "
       "system to answering from history alone."),
    _t("context.graph_tokens_min", 400, int, 0, 20_000,
       "Floor for the graph block.", "Below ~200 a hit arrives without its citations."),
    _t("context.graph_tokens_max", 4000, int, 0, 100_000,
       "Ceiling for the graph block.", "Guards a 200k model from spending it all on graph."),
    _t("context.memory_tokens", 300, int, 0, 20_000,
       "Budget for permanent memory.",
       "Memory is small by construction; this rarely binds."),
    _t("context.live_tokens", 400, int, 0, 20_000,
       "Budget for the conversation's own graph.",
       "Too low and 'the option we picked earlier' stops resolving."),

    # ── Knowledge ────────────────────────────────────────────────────────
    _t("knowledge.query_tokens", 2000, int, 100, 50_000,
       "Default token budget for a graph query.",
       "Bounds the answer. The corpus side is unbounded, which is the point."),
    _t("knowledge.walk_depth", 2, int, 1, 6,
       "Hops from a seed node.",
       "Each hop multiplies results and latency; 3+ is a hairball on a large graph."),
    _t("knowledge.walk_limit", 60, int, 5, 5_000,
       "Max nodes returned by one walk.", "Directly bounds query cost."),
    _t("knowledge.seed_limit", 12, int, 1, 500,
       "Candidate seed nodes per query.", "More seeds, broader and slower answers."),
    _t("knowledge.view_node_limit", 400, int, 0, 200_000,
       "Nodes before the viewer switches to a community overview.",
       "0 means always render everything, which is a hairball above a few thousand."),

    # ── Conversation graph ───────────────────────────────────────────────
    _t("live.max_nodes", 400, int, 20, 20_000,
       "Working-set cap for a conversation's own graph.",
       "Unbounded turns a long chat into a slow memory leak. Decisions are "
       "never evicted regardless."),

    # ── Memory ───────────────────────────────────────────────────────────
    _t("memory.duplicate_threshold", 0.85, float, 0.0, 1.0,
       "Word-overlap score above which two memories are one.",
       "Too low merges distinct facts ('Postgres' vs 'Postgres 16'); too high "
       "fills the store with restatements of one sentence."),
    _t("memory.max_chars", 240, int, 40, 2_000,
       "Longest a single memory may be.",
       "Memory is injected into every prompt whole, on the assumption that it "
       "is small. One pasted paragraph spends the entire budget and silently "
       "clips every other fact out of the prompt."),

    # ── Assets ───────────────────────────────────────────────────────────
    _t("assets.chunk_chars", 1200, int, 200, 20_000,
       "Target retrieval chunk size.",
       "Smaller is more specific and more numerous; larger keeps a thought whole."),
    _t("assets.chunk_overlap", 150, int, 0, 5_000,
       "Overlap between chunks.",
       "Zero means a sentence spanning a boundary is retrievable from neither."),

    # ── Scheduler ────────────────────────────────────────────────────────
    _t("scheduler.asset_wait_s", 120, int, 5, 3_600,
       "How long a turn waits for an attached asset to finish ingesting.",
       "Too short and a large PDF fails a turn that would have succeeded."),
    _t("scheduler.flush_interval_s", 0.1, float, 0.01, 2.0,
       "Token batching interval for streaming.",
       "Lower feels smoother and costs more socket writes."),
    _t("scheduler.flush_tokens", 5, int, 1, 200,
       "Tokens batched per socket write.", "Higher is choppier but cheaper."),

    # ── Facts graph ──────────────────────────────────────────────────────
    _t("facts.min_mentions", 2, int, 1, 50,
       "Conversations that must mention something before it is a subject.",
       "At 1 every passing remark becomes a node and the canvas turns to "
       "confetti. Above 3 a thing discussed twice — which is most of them — "
       "never appears at all."),

    # ── Tools ────────────────────────────────────────────────────────────
    _t("tools.max_steps", 8, int, 1, 100,
       "Tool calls the model may chain inside one turn.",
       "Each step is a full model round-trip. Too low and a multi-step task "
       "stops half-finished; too high and a model stuck in a loop spends the "
       "whole turn before answering."),
    _t("tools.inline_output_chars", 2_000, int, 200, 200_000,
       "Characters of tool output shown to the model inline.",
       "The remainder is stored as an asset and referenced instead. Raising "
       "it puts a long log straight into the context window, which is the "
       "thing that indirection exists to prevent (CRS §6.2.4)."),

    # ── Skills ───────────────────────────────────────────────────────────
    _t("skills.inline_budget_chars", 32_000, int, 1_000, 500_000,
       "Max characters of skill instructions inlined into one prompt.",
       "A large skill can otherwise consume most of a small model's window "
       "before it reads the question."),
    _t("skills.max_asset_chars", 60_000, int, 1_000, 1_000_000,
       "Max characters read from one asset a skill pulls in.",
       "Bounds a single file's share of the prompt. Too low and a skill's "
       "reference material arrives cut off mid-section."),

    # ── Providers ────────────────────────────────────────────────────────
    _t("models.discovery_timeout_s", 10.0, float, 0.5, 120.0,
       "Seconds to wait while asking a provider what models it offers.",
       "A cloud endpoint behind a CDN can take several seconds on a cold "
       "handshake, and a timeout is indistinguishable from the provider "
       "offering nothing. A local daemon that is not running refuses at once "
       "and never waits, so raising this costs local setups nothing."),
]}

_lock = threading.RLock()
_cache: dict[str, float | int] | None = None


def _stored() -> dict:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        rows = {}
        try:
            for r in db.connect().execute(
                    "SELECT key, value FROM settings WHERE key LIKE 'tunable.%'"):
                try:
                    rows[r["key"][len("tunable."):]] = json.loads(r["value"])
                except Exception:
                    continue
        except Exception:
            # Before storage.configure(), or on a database that has not been
            # initialised yet. Defaults are still correct; the cache is left
            # unset so the next call retries rather than freezing the fallback.
            return {}
        _cache = rows
        return rows


def invalidate() -> None:
    global _cache
    with _lock:
        _cache = None


def get(key: str):
    """Resolve a tunable: environment, then stored, then default."""
    spec = REGISTRY.get(key)
    if spec is None:
        raise KeyError(f"unknown tunable {key!r}")

    raw = os.getenv(spec.env)
    if raw is not None and raw.strip():
        try:
            return spec.clamp(raw.strip())
        except (TypeError, ValueError):
            pass

    stored = _stored().get(key)
    if stored is not None:
        try:
            return spec.clamp(stored)
        except (TypeError, ValueError):
            pass
    return spec.default


def set_many(values: dict) -> dict:
    """Store tunables. Unknown keys and out-of-range values are reported back."""
    stored, rejected = {}, {}
    for key, value in values.items():
        spec = REGISTRY.get(key)
        if spec is None:
            rejected[key] = "unknown tunable"
            continue
        try:
            clamped = spec.clamp(value)
        except (TypeError, ValueError):
            rejected[key] = f"not a {spec.kind.__name__}"
            continue
        if clamped != spec.kind(value):
            rejected[key] = f"clamped to [{spec.minimum}, {spec.maximum}]"
        stored[key] = clamped

    if stored:
        ts = now_ms()
        with db.tx() as c:
            for key, value in stored.items():
                c.execute(
                    "INSERT INTO settings (key,value,updated_at) VALUES (?,?,?)"
                    " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                    "                                updated_at=excluded.updated_at",
                    (f"tunable.{key}", json.dumps(value), ts),
                )
        invalidate()
    return {"stored": stored, "rejected": rejected}


def reset(key: str | None = None) -> int:
    with db.tx() as c:
        if key:
            cur = c.execute("DELETE FROM settings WHERE key=?", (f"tunable.{key}",))
        else:
            cur = c.execute("DELETE FROM settings WHERE key LIKE 'tunable.%'")
    invalidate()
    return cur.rowcount


def describe() -> list[dict]:
    """Every tunable, its current value, and where that value came from.

    Provenance is the useful column: "why is this 40" is answered by whether it
    came from an environment variable, the database, or the default.
    """
    stored = _stored()
    out = []
    for key, spec in sorted(REGISTRY.items()):
        env_value = os.getenv(spec.env)
        if env_value is not None and env_value.strip():
            source = "environment"
        elif key in stored:
            source = "saved"
        else:
            source = "default"
        out.append({
            "key": key, "value": get(key), "default": spec.default,
            "min": spec.minimum, "max": spec.maximum,
            "type": spec.kind.__name__, "source": source,
            "env": spec.env, "summary": spec.summary, "cost": spec.cost,
        })
    return out
