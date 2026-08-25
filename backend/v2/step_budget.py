"""Adaptive step budgets and cache economics.

The measurements this module encodes, from Primnox's own benchmark of the
same task at increasing step counts:

    steps   billed (no cache)   billed (cached)
      1              350               353
      2              848               842
      4            2,283             1,905
      8            7,032             4,376

Two things follow, and both are implemented here rather than left as advice.

**Steps are the dominant cost surface.** Eight steps cost twenty times one
step, not eight times, because each step carries every earlier result
forward. So the budget starts at one and doubles only while the task is
genuinely unfinished — a trivial question must not become an eight-step
agent loop.

**Caching is a function of turn length, not a default.** At one step the
cache write costs more than it saves (353 > 350). By eight steps it saves
almost 40%. So caching is switched on by predicted length, from the numbers
above, instead of being enabled globally and hoped about.

The metric that matters is cost per *successful* task. A cheap turn that
fails and gets retried is not cheap, which is why :func:`record_turn` tracks
success alongside tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from v2 import ids, store

try:  # pragma: no cover - logging is incidental to behaviour
    from logger import get_logger

    log = get_logger("v2.step_budget")
except Exception:  # pragma: no cover
    import logging

    log = logging.getLogger("v2.step_budget")


# The escalation ladder. Doubling rather than incrementing: if one step was
# not enough, the next attempt usually needs materially more room, and
# 1→2→3→4 pays the re-plan cost too often.
LADDER: tuple[int, ...] = (1, 2, 4, 8)

# Measured billed tokens for the same task at each ladder position, as
# (uncached, cached). Kept as data because the caching policy is derived
# from it — if the numbers are re-measured, the policy follows.
MEASURED_BILLED_TOKENS: dict[int, tuple[int, int]] = {
    1: (350, 353),
    2: (848, 842),
    4: (2283, 1905),
    8: (7032, 4376),
}

# A cache write on a short turn is only worth it if the stable prefix is
# large enough to matter. Below this, the measured 2-step saving (6 tokens)
# is indistinguishable from noise.
CACHE_MIN_PREFIX_TOKENS = 1500

# Result budgets by predicted length. Tighter for long turns, because that
# is where accumulation hurts — but note the benchmark's other finding: a
# small result cap helped less than expected, so this is a secondary control
# behind step count and compaction, not the primary one.
RESULT_BUDGETS: dict[int, int] = {1: 800, 2: 600, 4: 400, 8: 300}

_SIMPLE = re.compile(
    r"^\s*(what|who|where|when|which)\s+(is|are|was|does|do)\b|^\s*(define|explain)\b", re.I
)
_MULTI_STEP = re.compile(
    r"\brefactor\b|\bmigrate\b|\brewrite\b|\bacross the (codebase|repo|project)\b"
    r"|\bevery (file|module|test)\b|\ball the (files|modules|tests)\b|\bend[- ]to[- ]end\b"
    r"|\bthen\b.*\band\b",
    re.I,
)
_ACTION = re.compile(
    r"\b(run|deploy|install|delete|create|write|send|commit|push|fix|rename|update|implement)\b",
    re.I,
)


@dataclass(frozen=True)
class Plan:
    """A per-turn cost plan: how long, whether to cache, how big results may be."""

    predicted_steps: int
    max_steps: int
    cache: bool
    result_budget_tokens: int
    compact: bool
    rationale: str

    def as_dict(self) -> dict:
        return {
            "predicted_steps": self.predicted_steps,
            "max_steps": self.max_steps,
            "cache": self.cache,
            "result_budget_tokens": self.result_budget_tokens,
            "compact": self.compact,
            "rationale": self.rationale,
        }


def cache_pays_off(steps: int) -> bool:
    """Does caching reduce billed tokens at this step count, as measured?

    Interpolates between measured rungs by taking the nearest measured step
    count at or below `steps`, so an unmeasured 3-step turn is judged by the
    2-step numbers rather than by optimism.
    """
    known = [n for n in sorted(MEASURED_BILLED_TOKENS) if n <= steps] or [min(MEASURED_BILLED_TOKENS)]
    uncached, cached = MEASURED_BILLED_TOKENS[known[-1]]
    return cached < uncached


def predict(question: str, route=None) -> int:
    """Predict how many steps this request will need.

    Deliberately conservative in the cheap direction: under-predicting costs
    one escalation, while over-predicting costs the whole difference between
    one step and eight on every request that did not need it.
    """
    text = (question or "").strip()
    if not text:
        return 1

    if _MULTI_STEP.search(text):
        return 8

    sources = len(getattr(route, "sources", []) or [])
    intent = getattr(route, "intent", "retrieve")

    if intent == "act":
        # Doing something has to be planned, done and verified.
        return 8 if _MULTI_STEP.search(text) else 4
    if sources >= 3:
        return 4
    if _ACTION.search(text):
        return 4
    if sources == 2:
        return 2
    if _SIMPLE.match(text) or intent in {"remember", "forget"}:
        return 1
    return 2


# How many turns at a route label before what actually happened is allowed to
# move the prediction, and how far back to look. Small enough to adapt within a
# session, large enough that one unusual turn does not swing the ladder.
_FEEDBACK_MIN_TURNS = 5
_FEEDBACK_WINDOW = 20


def observed_ceiling(route_label: str | None) -> int | None:
    """The rung recent turns at this label actually needed, if it is known.

    Only ever used to correct DOWNWARD, which is the asymmetry `predict()`
    already documents: under-predicting costs one escalation, over-predicting
    costs the difference between one step and eight on every request that did
    not need it. So a label whose turns keep finishing early gets a cheaper
    plan, and one that keeps running long is left alone — the escalation path
    handles that direction already.

    Takes the MAX of the window rather than the mean. The question is "what
    does this kind of request need", and a mean lets a run of trivial turns
    starve the occasional long one into an escalation it could have avoided.
    """
    if not route_label:
        return None
    _init()
    rows = store.connect().execute(
        "SELECT steps_used FROM turn_costs WHERE route_label = ? AND success = 1"
        " ORDER BY rowid DESC LIMIT ?",
        (route_label, _FEEDBACK_WINDOW),
    ).fetchall()
    if len(rows) < _FEEDBACK_MIN_TURNS:
        return None
    worst = max(int(r["steps_used"] or 0) for r in rows)
    # Snap up to a real rung: the ladder is what the rest of the module speaks.
    for rung in LADDER:
        if worst <= rung:
            return rung
    return LADDER[-1]


def plan(question: str, route=None, *, prefix_tokens: int = 0) -> Plan:
    """Build the cost plan for one turn."""
    predicted = predict(question, route)
    # The telemetry recorded every miss and nothing read it back, so a label
    # that had over-predicted six times running still predicted the same on the
    # seventh. Measured: predicted 8, used 2, six times — prediction_accuracy
    # 0.0, and the next plan unchanged. Over-prediction is not free either: at
    # 8 it turns compaction on and cuts the result budget to 300 tokens, so a
    # turn that needed two steps gets its results deferred to asset reads it
    # then pays to fetch back.
    observed = observed_ceiling(getattr(route, "label", None))
    corrected_from = None
    if observed is not None and observed < predicted:
        corrected_from, predicted = predicted, observed
    cache = cache_pays_off(predicted) and (
        predicted >= 4 or prefix_tokens >= CACHE_MIN_PREFIX_TOKENS
    )
    rationale_parts = [f"predicted {predicted} step(s)"]
    if route is not None:
        rationale_parts.append(f"route {getattr(route, 'label', '?')}")
    rationale_parts.append("cache on" if cache else "cache off")
    if predicted >= 4:
        rationale_parts.append("compaction on")
    if corrected_from is not None:
        rationale_parts.append(
            f"lowered from {corrected_from} — recent turns at this route finished sooner")

    return Plan(
        predicted_steps=predicted,
        max_steps=predicted,
        cache=cache,
        result_budget_tokens=RESULT_BUDGETS.get(predicted, 400),
        compact=predicted >= 4,
        rationale="; ".join(rationale_parts),
    )


class StepBudget:
    """The escalation ladder, as an object a tool loop can drive.

    Usage is: run up to `remaining` steps, and if the task is still
    unfinished, ask to `escalate()`. The ladder stops at 8 — a task that
    cannot be finished in eight steps needs a different plan, not a longer
    loop.
    """

    def __init__(self, predicted: int = 1, *, ceiling: int = LADDER[-1]) -> None:
        self.ceiling = ceiling
        self.limit = self._snap(predicted)
        self.used = 0
        self.escalations = 0

    @staticmethod
    def _snap(value: int) -> int:
        for rung in LADDER:
            if value <= rung:
                return rung
        return LADDER[-1]

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0

    def step(self) -> int:
        """Consume one step and return how many are left."""
        self.used += 1
        return self.remaining

    def escalate(self) -> bool:
        """Move to the next rung. False when the ceiling has been reached."""
        if self.limit >= self.ceiling:
            return False
        self.limit = self._snap(self.limit + 1)
        self.escalations += 1
        return True

    def as_dict(self) -> dict:
        return {
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "escalations": self.escalations,
            "exhausted": self.exhausted,
        }


# ── Telemetry ────────────────────────────────────────────────────────────────

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS turn_costs (
        id              TEXT PRIMARY KEY,
        task_id         TEXT,
        session_id      TEXT,
        route_label     TEXT,
        predicted_steps INTEGER NOT NULL,
        steps_used      INTEGER NOT NULL,
        billed_tokens   INTEGER NOT NULL DEFAULT 0,
        cached          INTEGER NOT NULL DEFAULT 0,
        success         INTEGER NOT NULL DEFAULT 0,
        latency_ms      REAL,
        created_at      TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_turn_costs_session ON turn_costs(session_id, created_at)",
]


def _init() -> None:
    store.ensure_schema("step_budget", _SCHEMA)


def record_turn(
    *,
    predicted_steps: int,
    steps_used: int,
    billed_tokens: int = 0,
    success: bool = True,
    cached: bool = False,
    task: str | None = None,
    session: str | None = None,
    route_label: str | None = None,
    latency_ms: float | None = None,
) -> str:
    """Record what a turn actually cost. Returns the telemetry row ID."""
    _init()
    row_id = ids.new_id("audit")
    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO turn_costs (id, task_id, session_id, route_label, predicted_steps,
                                    steps_used, billed_tokens, cached, success, latency_ms,
                                    created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row_id, task, session, route_label, predicted_steps, steps_used, billed_tokens,
                1 if cached else 0, 1 if success else 0, latency_ms, store.utc_now(),
            ),
        )
    return row_id


def cost_report(*, session: str | None = None) -> dict:
    """Cost per successful task, and how well predictions held up.

    Cost per *successful* task is the headline number: tokens per request
    can be driven down by giving up early, and this is the metric that
    notices.
    """
    _init()
    clause, params = ("WHERE session_id = ?", [session]) if session else ("", [])
    row = store.connect().execute(
        f"""
        SELECT COUNT(*) AS turns,
               COALESCE(SUM(billed_tokens), 0) AS billed,
               COALESCE(SUM(success), 0) AS successes,
               COALESCE(SUM(steps_used), 0) AS steps,
               COALESCE(SUM(CASE WHEN cached = 1 THEN 1 ELSE 0 END), 0) AS cached_turns,
               COALESCE(SUM(CASE WHEN steps_used > predicted_steps THEN 1 ELSE 0 END), 0) AS underestimates,
               COALESCE(SUM(CASE WHEN steps_used < predicted_steps THEN 1 ELSE 0 END), 0) AS overestimates
          FROM turn_costs {clause}
        """,
        params,
    ).fetchone()

    turns = row["turns"] or 0
    successes = row["successes"] or 0
    return {
        "turns": turns,
        "successes": successes,
        "billed_tokens": row["billed"],
        "steps": row["steps"],
        "cached_turns": row["cached_turns"],
        "cost_per_successful_task": round(row["billed"] / successes, 1) if successes else None,
        "cost_per_turn": round(row["billed"] / turns, 1) if turns else None,
        "underestimated": row["underestimates"],
        "overestimated": row["overestimates"],
        "prediction_accuracy": (
            round((turns - row["underestimates"] - row["overestimates"]) / turns, 3) if turns else None
        ),
    }
