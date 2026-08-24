"""Performance budgets — every commit must stay inside them.

The budgets in the specification's table were truncated in transmission, so
these are set from what the architecture actually promises and are marked for
review. They are deliberately loose enough not to flake on a busy laptop and
tight enough that a real regression trips them: each one is roughly an order of
magnitude above the measured value.

The one that matters most is `turn_accepted`. ARCH §4.1 promises the HTTP call
returns a turn_id before any model work begins; if that budget is ever missed,
the runtime has started doing work on the request path again, which is the V1
behaviour the whole rewrite exists to remove.
"""
from __future__ import annotations

import time

import pytest
from conftest import run_turn, wait_for_turn

from primnox2.chat import turns
from primnox2.context import service as context
from primnox2.kernel.events import bus
from primnox2.storage import db

# name -> milliseconds. REVIEW: confirm against the intended table.
BUDGETS = {
    "turn_accepted": 50,
    "first_token": 400,
    "history_load_100_turns": 200,
    "replay_1000_events": 200,
    "context_build": 250,
    "event_emit": 25,
}

_measured: dict[str, float] = {}


def budget(name: str, elapsed_ms: float) -> None:
    _measured[name] = elapsed_ms
    limit = BUDGETS[name]
    assert elapsed_ms <= limit, (
        f"{name} took {elapsed_ms:.1f}ms, over its {limit}ms budget "
        f"({elapsed_ms / limit:.1f}x)"
    )


def test_turn_accepted_before_any_model_work(conversation):
    """ARCH §4.1 — the response carries a turn_id and returns immediately."""
    start = time.perf_counter()
    turn = turns.create_turn(conversation, "how fast are you?")
    elapsed = (time.perf_counter() - start) * 1000
    assert turn["turn_id"].startswith("turn_")
    budget("turn_accepted", elapsed)


def test_first_token_latency(conversation, events, scripted):
    scripted("Fast enough.", chunk=2)
    start = time.perf_counter()
    tid = run_turn(conversation, "hello")
    deadline = time.time() + 10
    while time.time() < deadline and not events.of_kind("token", tid):
        time.sleep(0.005)
    elapsed = (time.perf_counter() - start) * 1000
    wait_for_turn(tid)
    budget("first_token", elapsed)


def test_history_load(conversation):
    for i in range(100):
        turn = turns.create_turn(conversation, f"message {i}")
        turns.complete(turn["turn_id"], f"reply {i}")

    start = time.perf_counter()
    history = turns.get_history(conversation)
    elapsed = (time.perf_counter() - start) * 1000
    assert len(history) >= 100
    budget("history_load_100_turns", elapsed)


def test_event_replay(conversation):
    before = bus.head()
    for _ in range(1000):
        bus.emit("token", {"text": "x"}, conversation_id=conversation)

    start = time.perf_counter()
    replayed = bus.replay(before, [conversation])
    elapsed = (time.perf_counter() - start) * 1000
    assert len(replayed) >= 1000
    budget("replay_1000_events", elapsed)


def test_context_build(conversation):
    start = time.perf_counter()
    bundle = context.build(conversation, "assemble this", budget=8000)
    elapsed = (time.perf_counter() - start) * 1000
    assert bundle.messages
    budget("context_build", elapsed)


def test_event_emit(conversation):
    start = time.perf_counter()
    for _ in range(20):
        bus.emit("token", {"text": "x"}, conversation_id=conversation)
    elapsed = (time.perf_counter() - start) * 1000 / 20
    budget("event_emit", elapsed)


@pytest.fixture(scope="module", autouse=True)
def _report():
    yield
    if _measured:
        print("\n\nPerformance budgets")
        print(f"{'metric':<26} {'measured':>10} {'budget':>9}  headroom")
        for name, value in _measured.items():
            limit = BUDGETS[name]
            print(f"{name:<26} {value:>8.1f}ms {limit:>7}ms  {limit / max(value, 0.01):>5.1f}x")
