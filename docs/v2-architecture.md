# Primnox V2 — core substrate

> Implements the V2 Master Architecture, Architecture Bible and IRL
> Behavioural Specification. Lives in `backend/v2/`, additive to V1.

Primnox V2 is not a larger chat history. It is a secure, structured model of
the user's ongoing work: durable memory with provenance, a world model of
entities and relationships, structural code intelligence, a retrieval router,
resumable execution state, and cost-aware context construction.

This document describes what exists in `backend/v2/`, the rules it enforces,
and how V1 adopts it.

---

## Why

A simple assistant is `conversation → LLM → tool → result → LLM → answer`.
That works for short tasks and degrades badly for long ones, because every
step carries all previous results forward:

```
step 1:  question + result₁
step 2:  question + result₁ + result₂
step 3:  question + result₁ + result₂ + result₃
```

Primnox's own benchmark of one task at increasing step counts:

| steps | billed (no cache) | billed (cached) |
|------:|------------------:|----------------:|
| 1     | 350               | 353             |
| 2     | 848               | 842             |
| 4     | 2,283             | 1,905           |
| 8     | 7,032             | 4,376           |

Eight steps cost twenty times one step, not eight times. Three consequences
are built into this substrate rather than left as advice:

1. **Reduce steps.** Budgets start at 1 and escalate 1 → 2 → 4 → 8 only
   while the task is genuinely unfinished (`step_budget.py`).
2. **Keep results out of the transcript.** The model gets a compact
   observation and a `res_…` handle; the full output lives in a store
   (`result_store.py`).
3. **Cache by turn length, and never rewrite the cached prefix.** At one
   step a cache write is a net loss; by eight it saves ~38%. Compaction
   appends an immutable block instead of rewriting history
   (`compaction.py`).

---

## Module map

| Module | Responsibility |
|---|---|
| `ids.py` | Stable typed IDs — the bridge between subsystems |
| `store.py` | One SQLite database, schema registry, UTC time helpers |
| `world_model.py` | Entities, relationships, durable facts, provenance, supersession |
| `episodes.py` | Timestamped events, consolidation into episodes, temporal recall |
| `result_store.py` | Full tool results out of context; compact observations; dedupe |
| `task_state.py` | Goal, constraints, actions, four-valued outcomes, resumability |
| `graphify.py` | Symbol/AST index, callers, dependents, impact, corpus filtering, staleness |
| `router.py` | Retrieval routing — M / S / G / R / T / H / C |
| `context.py` | Retrieve → rank → dedupe → label provenance → compress |
| `step_budget.py` | Adaptive step ladder, cache economics, cost telemetry |
| `compaction.py` | Immutable, cache-preserving compaction |
| `policy.py` | Trust boundary, credential isolation, permissions, audit, coordinated deletion |
| `integration.py` | The seam V1 calls — four functions |

Everything is **stdlib-only** (no new pip dependencies), **additive** (no V1
file is modified), and **import-cheap** (importing a module opens no database
and starts no thread).

---

## Flow

```
request
  ↓
router.route()            →  M | S | G | R | T | H | C   (+ intent)
  ↓
context.build()           →  retrieve · rank · dedupe · provenance · compress
  ↓
step_budget.plan()        →  steps · cache · result budget
  ↓
model + tools
  ↓
result_store.put()        →  compact observation + res_…
  ↓
compaction.compact()      →  frozen block appended after the cache boundary
  ↓
task_state / episodes / policy.record()
```

---

## Rules enforced structurally

These are the architecture's non-negotiables. Each is enforced by the code
rather than by convention, with a test naming the scenario it protects.

**An inference never silently becomes a fact.** Every durable belief carries
`origin` (stated / observed / inferred) and provenance. Evidence strength is
`(origin rank, confidence, recency)` in that order, so a newer guess cannot
overwrite something the user stated. When two weak, contradictory beliefs
collide, both are kept and marked disputed rather than a winner being
invented.

**Historical truth survives correction.** Superseding closes a fact's
validity interval and links it forward; it does not delete the row.
`current_facts()` answers "what is true", `history()` answers "what have I
believed about this".

**External content is data, not authority.**
`policy.memory_provenance_for("web", stated=True)` returns an *inference* —
a web page cannot produce a stated fact whatever it claims about itself.
Untrusted content is wrapped in `<untrusted_content>` markers before it
reaches a prompt.

**The model is not the credential vault.** `policy` stores credential *names*
and usage records only. What reaches a prompt is
`cred_34e6… (groq_api_key: available)`. The value is fetched through
`resolve_credential(...)`, which requires a grant, a stated purpose, an
injected resolver (V1's keyring/vault), and is audited on every call.

**A task is never reported complete while part of it never ran.**
`task_state.finish(task, "completed")` raises while any action is failed or
unresolved; the derived status is `partial`. Outcomes are four-valued —
completed, failed, partial, **unknown** — because a tool that died after
writing a file did not fail cleanly, and a blind retry is how recovery
becomes data loss.

**Never confidently return obsolete graph data.** Every indexed file records
size, mtime and hash; query results carry a `stale` flag when the file has
moved on, and `refresh()` re-indexes only what changed.

**No mandatory Graphify-before-grep.** There is no such hook. Lexical
questions route to `S` and never touch the graph; the router's own tests
assert `"G" not in route.sources` for "Where is the API key handling?".

**Compaction never rewrites the cached prefix.** `compact()` returns the
prefix by reference and appends one frozen block; `prefix_unchanged()` is
available to assert it.

**A failed write is never reported as a success.** Storage errors propagate;
`integration.note_activity()` returns `None` rather than a false
confirmation.

---

## Worked examples

### "What was I doing yesterday?"

```python
from v2 import context
built = context.build("What was I doing yesterday?", project="primnox")

built.route.label        # "H"
built.render()
# ── history ──
# [history · epi_aa4d…] 14:00 — file modified ×2, test failed on app/auth.py
built.tokens             # ~20
```

Reconstructed from timestamped events consolidated into an episode — not
read out of the current chat.

### A 10,000-token tool result

```python
from v2 import result_store
stored = result_store.put("dependency_report", report, session=sid)

stored["full_tokens"]         # 18168
stored["observation_tokens"]  # 103
result_store.reference(stored)
# "2000 lines, starts with: …\n[full result: res_8e16… · 18168 tokens]"

# later, selectively:
result_store.section(stored["result_id"], r"\bmodule_1337\b")
```

### Resuming an interrupted task

```python
from v2 import task_state
task = task_state.resume(project="primnox")
task_state.verify(task["id"], lambda action: on_disk(action))   # check reality first
task_state.next_step(task["id"])["description"]                 # where to pick up
task_state.render(task["id"])                                   # ~74 tokens of state
```

### Structural questions

```python
from v2 import graphify
graphify.index("backend", project="primnox")     # 153 files, 2581 symbols, ~0.9s
graphify.callers("get_logger", project="primnox")
graphify.dependents("logger.py", project="primnox")
graphify.impact("memory.py", project="primnox", depth=2)   # + affected tests
```

---

## Storage

One SQLite file, `primnox_v2.db`, beside V1's `memory.db` and `chat.db` in
the app data directory. One file rather than one per subsystem, because the
point of the world model is that a memory, an event, a tool result and a task
can reference each other.

Redirect it with `store.configure(path)` or the `PRIMNOX_V2_DB` environment
variable. Tests use `store.reset_for_tests(tmp_path / "v2.db")`.

Tables: `entities`, `relationships`, `facts` (+FTS), `events` (+FTS),
`episodes`, `results`, `tasks`, `actions`, `code_files`, `symbols`,
`code_edges`, `turn_costs`, `credentials`, `audit_log`.

Encryption is not re-implemented here: V1's `local_vault.py` already wraps a
database file with AES-GCM and OS-keychain key storage, and the same
treatment applies to `primnox_v2.db`. BIP-39 remains what the architecture
says it is — a recovery representation for key material, not the encryption
layer.

---

## Adopting it from V1

`integration.py` is the whole surface. Four call sites:

**1. Before the request** — replaces the fixed `max_steps = 5` in
`brain.py`:

```python
from v2 import integration
plan = integration.plan_turn(prompt, project=project, session=session_id,
                             searcher=tools.search_code, reader=tools.read_file)
max_steps = plan.max_steps          # 1 / 2 / 4 / 8 instead of always 5
system_context = plan.context_block # provenance-labelled, budgeted
```

**2. Where a tool result is appended** — `brain.py` currently does
`messages.append({"role": "tool", ..., "content": str(result)})`:

```python
content = integration.observe_tool_result(func_name, result, session=session_id,
                                          args=args, project=project)
messages.append({"role": "tool", "tool_call_id": tc_id, "name": func_name,
                 "content": content})
```

**3. When a turn runs long:**

```python
compacted = integration.compact_if_needed(messages, boundary_index=cache_boundary)
messages, cache_boundary = compacted.messages, compacted.boundary_index
```

**4. After the turn:**

```python
integration.record_turn_outcome(plan, steps_used=step + 1, billed_tokens=usage,
                                success=True, session=session_id, project=project)
```

Ambient watchers (`observer.py`, `feed_manager.py`, `meeting_recorder.py`)
contribute episodic memory with one call:

```python
integration.note_activity("file_modified", "edited backend/router.py", project=project)
```

Every one of these degrades to V1's existing behaviour on failure: a broken
context build returns an empty block, an unavailable result store returns the
raw result, a failed compaction leaves the transcript alone, and bookkeeping
errors are logged and swallowed. Adopting V2 does not add a way for the chat
path to break.

The `searcher`/`reader` hooks are deliberate: lexical search and file reading
are V1 tools that already know this codebase. V2 decides *whether* to search
and how much of the answer to keep — not how to grep.

---

## What is deliberately not here

Per the V2 scope lock: no CLI, no proactive JARVIS behaviour, no continuous
screen perception, no always-listening voice, no cross-device sync, no
multi-agent shared memory, no self-evolving skills, no autonomous background
agent, no counterfactual simulation, no multi-user memory.

Still outstanding within V2 itself:

- **Wiring.** `integration.py` is tested but not yet called from `brain.py`;
  the four call sites above are the diff.
- **Artifacts as first-class objects.** `world_model` has the `artifact`
  entity type and `result_store` has durable retention, but PDF/screenshot
  import and artifact-derived memory are not built.
- **Provider routing.** `policy.may_use_external_model()` enforces the
  privacy boundary; capability/cost/latency selection across providers still
  lives in V1's `model_registry.py` + `brain.py` fallback chain.
- **Vault coverage for `primnox_v2.db`.** One call into `local_vault`, not
  yet made.
- **A tiny local routing model.** `router.route(classifier=...)` and
  `router.label_prompt()` are the hook; the heuristic is the default and is
  free.

---

## Tests

419 tests in `backend/tests/test_v2_*.py`, running on `pytest` alone with no
other dependency — the same environment CI's backend job provides.

| File | Covers |
|---|---|
| `test_v2_foundation.py` | ID stability, storage redirection, UTC time |
| `test_v2_world_model.py` | Entities, edges, facts, conflicts, provenance, deletion |
| `test_v2_episodes.py` | Events, consolidation, temporal windows, timelines |
| `test_v2_result_store.py` | Summarisation, dedupe, selective retrieval, retention |
| `test_v2_task_state.py` | Outcomes, resumption, verification, changed intent |
| `test_v2_graphify.py` | Corpus filtering, structure, impact, staleness, confidence |
| `test_v2_router.py` | Every worked example from the architecture documents |
| `test_v2_cost.py` | Prediction, cache economics, escalation, compaction |
| `test_v2_context.py` | Source selection, ranking, budget, injected tools |
| `test_v2_policy.py` | Trust, redaction, permissions, credentials, audit |
| `test_v2_integration.py` | The V1 seam, including every degradation path |
| `test_v2_scenarios.py` | 42 of the numbered IRL behavioural scenarios, end to end |

`test_v2_scenarios.py` is the one to read first: each test is a numbered
scenario from the behavioural specification, exercised across the subsystems
that have to cooperate to satisfy it.
