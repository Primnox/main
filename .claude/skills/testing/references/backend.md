# Backend, performance, reliability, data integrity

Covers domains 4 (Backend & API), 5 (Performance), 6 (Reliability & Chaos), and
15 (Data Integrity). The backend is the part of Primnox with a real, mature
harness — 599 tests across five layers. Extend it; don't build beside it.

## Running

From `C:\project`:

```bash
C:/project/backend/venv/Scripts/python.exe -m pytest backend/tests -q
```

Packages are installed only in `backend/venv`. A bare `python` or `pytest` on PATH
will fail on imports — that's an environment problem, not a code failure, and
misreading it wastes a whole triage cycle.

Useful narrowing:

```bash
C:/project/backend/venv/Scripts/python.exe -m pytest backend/tests/test_l4_chaos.py -x -q
```

`-x` stops at the first failure. When one fixture breaks, forty tests fail
downstream and the first failure is the only informative one.

## How the fixtures work, and why it matters

`conftest.py` makes two decisions that will bite you if you fight them.

**The runtime is session-scoped.** The database path is fixed at `configure()` time
and worker threads cache their own connections. Re-pointing the DB per test leaves
threads writing to a database your test no longer knows about — you get failures
that look like data loss and are actually two databases. Tests isolate by using
their own conversations instead. Follow that pattern.

**`PRIMNOX2_HOME` is pinned to a temp dir before any import.** `app.py` resolves the
path at module scope, so a `TestClient` constructed without this would point the
whole runtime at the developer's real database. If you ever see the suite writing
to `~/Documents/Primnox2`, something imported `primnox2` before `conftest` ran —
fix the import order rather than the symptom.

`PRIMNOX2_AUTO_APPROVE=all` is also set pre-import, so the tool broker doesn't block
on approval prompts.

Available fixtures and helpers:

- `runtime` (session, autouse) — configures paths, DB, starts the scheduler
- `fresh_db` — empties knowledge tables without re-pointing the database
- `run_turn`, `wait_for_turn`, `wait_until` — imported `from conftest` in the layer tests

## Choosing a layer

Put a new test where its failure would be most informative:

- **L0 `test_l0_contracts.py`** — the shape of the API and events. A break here means
  clients break. Cheapest and fastest gate.
- **L1 `test_l1_unit.py`** — pure logic, no I/O.
- **L2 `test_l2_http.py` / `test_l2_integration.py`** — the HTTP surface, and
  components wired together.
- **L3 `test_l3_scenarios.py`** — a user doing a real thing end to end.
- **L4 `test_l4_chaos.py`** — the runtime under violence.

A bug that a unit test could have caught belongs in L1, even if you found it at L3.
Tests at the lowest layer that can catch the defect are the ones that stay fast and
point at a line rather than a subsystem.

## Performance budgets

`test_perf_budgets.py` holds a `BUDGETS` dict of name → milliseconds:

```python
BUDGETS = {
    "turn_accepted": 50,
    "first_token": 400,
    "history_load_100_turns": 200,
    "replay_1000_events": 200,
    "context_build": 250,
    "event_emit": 25,
}
```

The budgets are set roughly an order of magnitude above measured values — loose
enough not to flake on a busy laptop, tight enough to catch a real regression.

**`turn_accepted` is the one that matters.** The architecture promises the HTTP call
returns a `turn_id` before any model work begins. If that budget trips, the runtime
has started doing work on the request path again — which is precisely the V1
behaviour the V2 rewrite exists to eliminate. Treat a `turn_accepted` regression as
architectural, not as a slow test.

When a budget fails: measure first. If the machine was genuinely loaded, re-run
before concluding. If it reproduces, find what got added to the path — don't raise
the budget. Raising a budget to make a test pass converts a regression into a
permanent loss.

## Chaos patterns

`test_l4_chaos.py` kills the backend mid-stream, kills sandboxed processes
mid-execution, fills the disk, and interrupts transactions.

Every chaos test asserts the same invariant, and any new one should too:

> Never a completed turn with no event. Never an event with no turn. Never a turn
> left non-terminal.

That invariant is what makes the runtime debuggable after a crash: a client can
always reason about what state it's in. A chaos test that only asserts "didn't
crash" is much weaker — the interesting failures leave the process alive and the
data incoherent.

Use `SIGKILL`-equivalent termination, not graceful shutdown, when simulating power
loss. Graceful paths run cleanup handlers and test nothing.

## Data integrity

Migrations: `test_schema_migrations.py`. Assert forward migration *and* that
re-running is idempotent — a migration that fails on second run breaks every
recovery scenario.

For referential integrity, orphans, and duplicates, prefer asserting the constraint
is enforced by the schema over asserting the application happens to behave. A
constraint holds against code paths you haven't written yet.

Event ordering (280) is load-bearing for replay — see `test_replay_recorder.py`.
If timestamps can collide, replay becomes non-deterministic and every downstream
test gets flaky in a way that's very hard to trace back.

## Reading a failure

1. Read the **first** failure, not the last.
2. Separate "the assertion is wrong" from "the code is wrong" — a test encoding
   stale expectations is a real finding too, just a different one.
3. Check whether it reproduces in isolation (`-k <name>`). If it passes alone and
   fails in the suite, you have cross-test contamination — usually shared runtime
   state, given the session-scoped fixture.
4. Only then read the code.
