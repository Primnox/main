# Conversation Runtime Specification

**CRS/1.0** · Status: Draft · 2026-08-14

This document defines the immutable contracts of the Primnox conversation
runtime: the objects, their lifecycles, the event log, transaction rules,
ordering guarantees, delivery semantics, reconnection, and cancellation.

Every subsystem — chat, tools, skills, assets, workspaces, memory, voice, and
any future agent — implements these contracts. No subsystem defines its own
lifecycle, its own event shape, or its own socket path.

Architecture rationale lives in [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md).
This document is the normative part. Where the two disagree, this one wins.

---

## 0. Conformance

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**,
and **MAY** are to be interpreted as in RFC 2119.

A component is **CRS-conformant** if it satisfies every MUST in the sections
that apply to it. §12 lists the requirements for a new subsystem.

### 0.1 Terminology

| Term | Meaning |
|---|---|
| **Runtime** | The backend process implementing this specification |
| **Client** | Any consumer of the event stream (the desktop UI, the island window, a test harness) |
| **Actor** | Code performing work on behalf of a turn (a job worker) |
| **State tables** | The durable tables from which current state is reconstructable |
| **Event log** | The append-only `events` table |

---

## 1. Identifiers

1.1. Every object identifier **MUST** have the form `<prefix>_<uuid7>`.

| Object | Prefix |
|---|---|
| Conversation | `conv` |
| Turn | `turn` |
| Message | `msg` |
| Job | `job` |
| Event | `evt` |
| Workspace | `ws` |
| Asset | `asset` |

1.2. UUIDv7 is **REQUIRED** because it is time-ordered: identifiers sort by
creation, which makes index locality good and debugging tractable.

1.3. Identifiers are opaque to clients. A client **MUST NOT** parse, order by,
or derive meaning from an identifier's contents. Ordering comes from
`sequence` (§3), never from an id.

1.4. Identifiers are permanent. An object's id **MUST NOT** change, and
**MUST NOT** be reused after deletion.

---

## 2. Objects

### 2.1 Conversation

A conversation is an ordered container of turns. It owns nothing else.

**Invariants**

- A conversation **MUST NOT** own workspaces or assets. It references them.
- Deleting a conversation **MUST NOT** delete referenced workspaces or assets.
- `incognito` is set at creation and **MUST** be immutable thereafter.

### 2.2 Turn

A turn is one user message and the complete response to it, including every
job that response required.

**Invariants**

- A turn **MUST** have exactly one user message.
- A turn **MUST** have at most one assistant message.
- A turn **MUST** reach a terminal status (§5.1) or be swept on boot (§10.3).
- A turn **MUST NOT** be mutated after reaching a terminal status, except by
  the retention policy (§3.7).
- Every job **MUST** belong to at most one turn. A job with `turn_id = NULL`
  is ambient or maintenance work (§11).

### 2.3 Job

A job is a unit of expensive, interruptible, resumable work.

**Invariants**

- A job **MUST** declare its `kind` from a registered set.
- A job **MUST** declare whether it is idempotent.
- A job **MUST** poll `cancel_requested` at its defined checkpoints (§9.2).
- A job **MUST NOT** write to a client socket. It emits events (§3).

### 2.4 Event

An event is an immutable, durable record of something that happened.

**Invariants**

- Events **MUST** be append-only. No update, no delete outside retention.
- An event **MUST** be durably committed before it is pushed to any client
  (§3.4).
- An event's `sequence` **MUST** be assigned inside the same transaction as
  the state change it describes (§4.2).

### 2.5 Workspace

A workspace is a versioned, editable artifact that outlives the conversation
that produced it.

**Invariants**

- Every mutation **MUST** create a new `WorkspaceVersion`. Versions are
  immutable.
- `current_version` **MUST** point at an existing version.
- A workspace **MUST** record its `origin_turn_id`, and **MUST** remain valid
  when that turn or conversation is deleted.

### 2.6 Asset

An asset is ingested content — a file, screenshot, recording, or extraction
result — addressed by id.

**Invariants**

- An asset **MUST** be content-addressed by `sha256`. Identical bytes
  **SHOULD** deduplicate to one asset.
- An asset **MUST** have status `ingesting`, `ready`, or `failed`.
- A turn referencing an asset that is not `ready` **MUST** either wait on it
  and report `TOOL_RUNNING`, or fail explicitly. It **MUST NOT** proceed with
  empty content.

---

## 3. The event log

### 3.1 Global sequence

3.1.1. There is exactly **one** monotonic sequence counter for the runtime.
It is global — not per conversation, not per turn.

3.1.2. `sequence` **MUST** be assigned by incrementing a counter row inside
the same transaction as the event insert:

```sql
BEGIN IMMEDIATE;
UPDATE event_seq SET value = value + 1 WHERE id = 1;
SELECT value FROM event_seq WHERE id = 1;   -- → the sequence to use
INSERT INTO events (event_id, sequence, ...) VALUES (...);
COMMIT;
```

3.1.3. The sequence **MUST** be gapless. A rolled-back transaction rolls back
the counter with it. This is why `AUTOINCREMENT` **MUST NOT** be used for
`sequence` — a rolled-back `AUTOINCREMENT` burns its value and leaves a
permanent gap, which destroys the client's ability to distinguish "nothing
happened" from "I missed something".

3.1.4. Gaplessness serializes all event appends on one row. This is
acceptable and costs nothing: SQLite in WAL mode already permits only one
writer.

3.1.5. A single global counter is correct — and does not require the client to
track per-conversation cursors — **only because of §3.3.** Read it before
concluding that a global cursor loses information.

### 3.2 Envelope

Every event **MUST** have exactly this envelope:

```json
{
  "event_id": "evt_01J8XQ2M7K3P5R8T",
  "sequence": 4813,
  "ts": 1786650256334,
  "scope": "conversation",
  "conversation_id": "conv_01J8W...",
  "turn_id": "turn_01J8X...",
  "kind": "token",
  "payload": { "text": "Hello" }
}
```

| Field | Rule |
|---|---|
| `event_id` | REQUIRED, unique, permanent |
| `sequence` | REQUIRED, global, gapless, strictly increasing |
| `ts` | REQUIRED, epoch ms, informational only — **MUST NOT** be used for ordering |
| `scope` | REQUIRED: `conversation` \| `ambient` \| `system` |
| `conversation_id` | REQUIRED when `scope = conversation`, else `null` |
| `turn_id` | REQUIRED when the event belongs to a turn, else `null` |
| `kind` | REQUIRED, from the registered set (§3.6) |
| `payload` | REQUIRED, object, kind-specific |

A client receiving an unknown `kind` **MUST** ignore it and **MUST** still
advance its cursor. This is what makes adding event kinds backward-compatible.

### 3.3 The event log is not the history

**This is the load-bearing rule of the specification.**

3.3.1. Conversation history **MUST** be fully reconstructable from the state
tables alone (`conversations`, `turns`, `messages`, `workspaces`, `assets`),
with no reference to the event log.

3.3.2. The event log exists **solely** to close the gap between a client's
last-seen state and live. It is a recovery mechanism, not a storage format.

3.3.3. A client opening a conversation it has not seen **MUST** load it from
the state tables (§7.1), never by replaying events from the beginning.

3.3.4. **Consequence — why a global cursor is sufficient.** Because history
never comes from the log, a client may safely advance its cursor past events
it was not shown (events for conversations it does not have open). Those
events are not lost information; their effects are durable in the state
tables and will be read the next time that conversation is opened. Without
§3.3, a global cursor would require every client to receive every event for
every conversation, and filtering would silently drop state.

3.3.5. Retention (§3.7) **MUST NOT** be able to destroy history. Any retention
policy that would lose user-visible state violates §3.3.1 and is invalid.

### 3.4 Durability before delivery

3.4.1. An event **MUST** be committed to the log before it is written to any
socket.

3.4.2. If the socket write fails, the event still occurred. The runtime
**MUST NOT** roll back, retract, or re-emit it with a new sequence.

3.4.3. Streaming tokens are **not** exempt. A token that reached the user but
not the log would be unrecoverable on reconnect.

### 3.5 Ordering

3.5.1. Events form a total order by `sequence`.

3.5.2. Events for a single turn form a subsequence of that total order, and
their relative order **MUST** reflect causal order.

3.5.3. A client **MUST** apply events in `sequence` order. On receiving
`sequence > expected`, it **MUST** buffer and wait rather than apply out of
order (§8.4).

### 3.6 Registered event kinds

| Kind | Payload | Scope |
|---|---|---|
| `turn.created` | `{turn, user_message}` | conversation |
| `turn.status` | `{status, detail?}` | conversation |
| `turn.completed` | `{assistant_message, usage}` | conversation |
| `turn.failed` | `{code, message, retryable}` | conversation |
| `turn.cancelled` | `{partial_text}` | conversation |
| `token` | `{text}` | conversation |
| `job.started` | `{job_id, kind, label}` | conversation \| ambient |
| `job.progress` | `{job_id, phase, pct?}` | conversation \| ambient |
| `job.completed` | `{job_id, status, result_ref?}` | conversation \| ambient |
| `tool.call` | `{job_id, name, arguments}` | conversation |
| `tool.result` | `{job_id, status, summary, result_ref?}` | conversation |
| `permission.request` | `{job_id, action, detail, options}` | conversation |
| `permission.resolved` | `{job_id, choice}` | conversation |
| `asset.ready` | `{asset_id, kind, name}` | conversation \| ambient |
| `asset.failed` | `{asset_id, reason}` | conversation \| ambient |
| `workspace.created` | `{workspace_id, kind, title}` | conversation |
| `workspace.updated` | `{workspace_id, version, changed_paths}` | conversation |
| `privacy.scrub` | `{mapping, model}` | conversation |
| `memory.written` | `{memory_id, text}` | conversation |
| `sync.complete` | `{head}` | system |

3.6.1. `token` payloads are **append-only**. A `token` event **MUST NOT**
replace previously delivered text. Corrections are a new turn, not a rewrite.

3.6.2. `turn.failed` **MUST NOT** be represented as an assistant message. A
failure is a failure, structurally distinct from a reply.

### 3.7 Retention

3.7.1. The log **MAY** be pruned. Pruning **MUST** respect §3.3.5.

3.7.2. The runtime **MUST** record the lowest retained sequence as
`min_retained_seq`. If a client presents `last_event_seen < min_retained_seq`,
the runtime **MUST** respond with a full-resync directive (§8.3) rather than a
partial replay.

---

## 4. Transactions

### 4.1 Single database

4.1.1. All state tables and the event log **MUST** live in one SQLite
database, `primnox.db`.

4.1.2. Splitting state across database files is **PROHIBITED**. A state change
and its event cannot be made atomic across files without `ATTACH` and a shared
journal; if a crash lands between them, a client's replayed stream disagrees
with stored state — the exact inconsistency the log exists to prevent.

### 4.2 Atomicity

4.2.1. A state change and the event describing it **MUST** be one transaction.

```sql
BEGIN IMMEDIATE;
  UPDATE event_seq SET value = value + 1 WHERE id = 1;
  UPDATE turns SET status = 'completed', completed_at = ? WHERE id = ?;
  INSERT INTO messages (...) VALUES (...);
  INSERT INTO events (event_id, sequence, kind, ...) VALUES (..., 'turn.completed', ...);
COMMIT;
```

Either both exist or neither does.

4.2.2. `BEGIN IMMEDIATE` is **REQUIRED** for any transaction that will write.
Deferred transactions upgrade mid-flight and can fail with `SQLITE_BUSY` after
partial work.

4.2.3. Sockets **MUST** be written after `COMMIT`, never inside the
transaction.

### 4.3 Required PRAGMAs

| Pragma | Value | Reason |
|---|---|---|
| `journal_mode` | `WAL` | concurrent readers during streaming writes |
| `synchronous` | `NORMAL` | correct under WAL; `FULL` costs latency for no gain here |
| `foreign_keys` | `ON` | referential integrity is not optional |
| `busy_timeout` | `5000` | absorbs contention instead of erroring |

4.3.1. `foreign_keys` is per-connection in SQLite and **MUST** be set on every
connection, not once at startup.

### 4.4 Migrations

4.4.1. Schema version **MUST** be tracked in a `schema_migrations` table.

4.4.2. Migrations **MUST** be forward-only and idempotent.

4.4.3. The runtime **MUST** refuse to start against a database whose version
is newer than it understands, rather than corrupting it.

---

## 5. Turn lifecycle

### 5.1 States

```
queued → building_context → thinking → streaming → completed
                │               │  ▲       │  ▲
                │               ▼  │       ▼  │
                │            tool_running ─────┤
                │               │  ▲          │
                │               ▼  │          │
                │          awaiting_input ─────┤
                │               │             │
                ▼               ▼             ▼
             failed         cancelled     completed
```

Terminal: `completed`, `failed`, `cancelled`.

5.1.1. `building_context`, `thinking` and `streaming` **MUST** remain distinct.
They describe three different situations — assembling the prompt, a model call
in flight with no token yet, and tokens arriving — and only the middle one is
the provider being slow. Collapsing them yields a single spinner that cannot
tell a user whether anything is wrong, which is the V1 behaviour this rule
exists to prevent.

5.1.2. A turn **MUST** enter `streaming` on its first token, not before.

### 5.2 Transition rules

5.2.1. Every status change **MUST** emit `turn.status` in the same transaction.

5.2.2. `failed` and `cancelled` are reachable from any non-terminal state.

5.2.3. Terminal states **MUST NOT** transition. A retry creates a **new** turn
that references the failed one; it does not reopen it.

5.2.4. A turn **MUST NOT** enter `streaming` before its user message is
durably committed.

### 5.3 There is no global status

5.3.1. The runtime **MUST NOT** expose a global `thinking`/`idle` state.

5.3.2. Aggregate indicators are derived by the client from the set of
non-terminal turns. A runtime-level scalar cannot represent five queued turns,
which is precisely the V1 defect this rule exists to prevent.

---

## 6. Job lifecycle

### 6.1 States

`queued → running → completed | failed | cancelled`

### 6.2 Rules

6.2.1. A job **MUST** emit `job.started` on entering `running` and exactly one
of `job.completed` / `job.failed` on leaving it.

6.2.2. A job's failure **MUST NOT** silently fail its turn. The turn decides:
a failed memory-extraction job **MUST NOT** fail a completed turn.

6.2.3. Retries: idempotent jobs **MAY** be retried automatically up to
`max_attempts`. Non-idempotent jobs **MUST NOT** be retried automatically.

6.2.4. Large job output **MUST** be stored as an asset and referenced by
`result_ref`, not inlined into an event payload. Events are not a blob store.

---

## 7. Delivery: streaming vs replay

**Replay is recovery. Streaming is delivery. The two MUST NOT be blurred.**

### 7.1 First delivery

7.1.1. Every token **MUST** be emitted exactly once, live, as it is produced.

7.1.2. The runtime **MUST NOT** simulate streaming by replaying stored text.
No fake typing of a completed response.

7.1.3. Loading a conversation the client has not seen is a **state read**
(§3.3.3), not a replay, and produces no events.

### 7.2 Delivery guarantees

| Layer | Guarantee |
|---|---|
| Log append | exactly once |
| Live socket push | at most once (a write may be lost) |
| Replay | at least once |
| Client reducer | **exactly once, in order** (via §8.4 dedupe + buffer) |

---

## 8. Reconnection

### 8.1 Handshake

```json
→ { "type": "hello",
    "last_event_seen": 4812,
    "conversations": ["conv_01J8W..."],
    "want_ambient": true }
```

```json
← events 4813, 4814, 4815 …   (filtered per §8.2)
← { "kind": "sync.complete", "payload": { "head": 4831 } }
← … live stream continues …
```

8.1.1. If `last_event_seen` equals the current head, the runtime **MUST**
replay zero events and send `sync.complete` immediately.

8.1.2. `sync.complete` **MUST** be sent even when zero events were replayed.
It is the client's signal that it is live.

### 8.2 Filtering

8.2.1. The runtime **MUST** filter replayed events to the client's declared
conversations, plus `system` scope, plus `ambient` if requested.

8.2.2. On `sync.complete`, the client **MUST** set its cursor to `head`, not
to the highest sequence it received. Events filtered out are not missing —
their effects are in the state tables (§3.3.4).

### 8.3 Full resync

8.3.1. If `last_event_seen < min_retained_seq`, the runtime **MUST** respond:

```json
{ "kind": "sync.required", "payload": { "reason": "retention", "head": 4831 } }
```

8.3.2. The client **MUST** then discard local conversation state and reload
from the state tables.

### 8.4 Client obligations

8.4.1. A client **MUST** deduplicate by `event_id`.

8.4.2. A client **MUST** buffer events whose `sequence` exceeds the expected
next value, and apply them only when the gap closes.

8.4.3. A client **MUST** be a pure fold: `reduce(state, event) → state`. It
**MUST NOT** infer, synthesize, or repair state the runtime did not send.

---

## 9. Cancellation

### 9.1 Request

```
DELETE /turns/{turn_id}
```

9.1.1. Sets `cancel_requested` on the turn and on every non-terminal job
belonging to it, in one transaction.

9.1.2. Cancellation is **REQUIRED** to be idempotent. Cancelling an already
terminal turn is a no-op returning success.

9.1.3. Cancelling a `queued` turn **MUST** take effect immediately, without
starting the work.

### 9.2 Checkpoints

An actor **MUST** check `cancel_requested` at minimum:

- each iteration of a token loop,
- between agentic steps,
- before and after each tool invocation,
- at each declared progress phase of a long-running job.

### 9.3 Partial output

9.3.1. A cancelled turn **MUST** persist whatever assistant text was produced,
and emit `turn.cancelled` carrying it.

9.3.2. Discarding partial output on cancel is **PROHIBITED**. Losing the
half-written answer is the one thing a stop button must never do.

### 9.4 Uncancellable work

9.4.1. A tool that cannot be interrupted **MUST** declare
`cancellable: false`. The runtime **MUST** then mark the turn `cancelled`,
stop emitting its events, and let the tool finish detached — it **MUST NOT**
claim to have stopped work it did not stop.

9.4.2. Subprocess tools **MAY** be hard-killed after a grace period.

---

## 10. Failure

### 10.1 Representation

10.1.1. Failures **MUST** be `turn.failed`, never an assistant message.

10.1.2. `turn.failed.retryable` **MUST** be set truthfully. A missing API key
and a rate limit are both failures; only one is worth a retry button.

10.1.3. `message` **MUST** be human-actionable. Raw provider exceptions and
raw Python tracebacks **MUST NOT** be surfaced as user-facing text. (V1's
`_explain_api_error` is the correct behaviour and is retained; only its
delivery channel changes.)

### 10.2 Error codes

| Code | Retryable | Meaning |
|---|---|---|
| `provider_unreachable` | yes | network / local model down |
| `provider_rate_limited` | yes | back off and retry |
| `provider_auth` | no | key rejected — user action required |
| `provider_quota` | no | billing — user action required |
| `model_unavailable` | no | model not on this account |
| `context_overflow` | no | conversation outgrew the window |
| `tool_failed` | maybe | per-tool |
| `asset_unavailable` | maybe | referenced asset not ready |
| `cancelled_by_user` | n/a | not an error |
| `internal` | maybe | bug — log with correlation id |

### 10.3 Crash recovery

10.3.1. On boot the runtime **MUST** sweep jobs left in `running`:
idempotent jobs requeue; non-idempotent jobs move to `failed` with
`interrupted by shutdown`.

10.3.2. Turns left non-terminal **MUST** be moved to `failed` with
`code = internal`, preserving any partial text. A turn **MUST NOT** be left
non-terminal across a restart.

---

## 11. Scopes

### 11.1 Ambient

11.1.1. Ambient events (`scope: "ambient"`) have `conversation_id = null` and
`turn_id = null`.

11.1.2. Ambient events **MUST NOT** be persisted to the log. They are
ephemeral telemetry; the island does not need replay.

11.1.3. Ambient producers **MUST NOT** write into a conversation directly.
The only path is **promotion**:

| Ambient occurrence | Promotion |
|---|---|
| Proactive suggestion accepted by the user | creates a Turn |
| Meeting recording ends | creates an Asset |
| Reminder fires | creates a system Turn |

11.1.4. Ambient events consume no global sequence numbers. They carry a
separate, non-durable `ambient_seq` for local ordering only.

### 11.2 Incognito

11.2.1. An incognito conversation **MUST NOT** write rows to
`conversations`, `turns`, `messages`, or `events`.

11.2.2. Its events exist in memory, delivered only to currently connected
clients.

11.2.3. Reconnecting into an incognito conversation loses its history. This is
correct and **MUST** be surfaced in the UI, not silently tolerated.

11.2.4. Assets and workspaces created from an incognito turn **MUST** be
either fully ephemeral or explicitly promoted by the user. Silently persisting
them violates the incognito contract.

---

## 12. Subsystem conformance

A new subsystem — Graphlit-style asset ingestion, tool emulation, voice,
autonomous agents — is CRS-conformant if and only if:

1. It performs turn-scoped work **only** as a registered job kind.
2. It emits `job.started`, `job.progress`, `job.completed` with its `job_id`.
3. It polls `cancel_requested` at the §9.2 checkpoints.
4. It declares idempotency (§6.2.3) and `cancellable` (§9.4.1).
5. It writes **no** bytes to any client socket. All output is events.
6. It stores large output as an asset and emits a `result_ref` (§6.2.4).
7. It performs state change and event append in one transaction (§4.2).
8. It introduces **no** new lifecycle, status enum, or ordering scheme.
9. It adds event kinds by registration (§3.6), never ad-hoc.
10. If it reaches a non-local provider, it passes through the Model Gateway so
    the Privacy Mirror boundary applies (§13.2).

**A subsystem that needs a lifecycle this specification cannot express is a
signal to amend this specification — not to invent a private one.** That is
the failure mode that produced `core.py`.

---

## 13. Cross-cutting rules

### 13.1 Model capability

13.1.1. No code outside `models/` **MAY** branch on provider name.

13.1.2. The tool contract belongs to the runtime (§ARCH-5.2). Provider
adapters translate to it; the runtime never adopts a provider's format.

### 13.2 Privacy boundary

13.2.1. All outbound model traffic **MUST** pass the Model Gateway.

13.2.2. The Gateway is the **only** place PII scrubbing is applied, and the
only place the local/cloud decision is made. One gate, one audit point.

13.2.3. A subsystem that reaches a provider directly, bypassing the Gateway,
is non-conformant regardless of any other property.

### 13.3 Time

13.3.1. All timestamps are epoch milliseconds, UTC.

13.3.2. Timestamps are informational. Ordering is `sequence` and only
`sequence` (§3.2). Wall-clock skew, NTP steps, and DST **MUST NOT** be able to
reorder anything.

---

## 14. Versioning

14.1. This specification is versioned `CRS/<major>.<minor>`.

14.2. Additive changes — new event kinds, new job kinds, new optional payload
fields — are **minor**. Clients ignore what they do not know (§3.2).

14.3. Changes to the envelope, sequence semantics, state machines, or
transaction rules are **major**.

14.4. The runtime **MUST** advertise its CRS version in the handshake response.
A client **MUST** refuse to operate against a major version it does not
implement, rather than degrading silently.

---

## Appendix A — Rule index

The rules that, if violated, reintroduce a known V1 defect:

| Rule | V1 defect it prevents |
|---|---|
| §3.2 envelope (`turn_id`, `sequence`) | tokens landing in the wrong reply; cross-window bleed |
| §3.3 log is not history | unbounded log; replay-as-history |
| §3.4 durability before delivery | tokens unrecoverable after a drop |
| §4.1 single database | replayed stream disagreeing with stored state |
| §4.2 atomicity | half-committed turn completions |
| §5.3 no global status | "idle" while four turns are still queued |
| §7.1.2 no fake streaming | replayed text presented as live generation |
| §9.3 preserve partial output | stop button destroying the answer |
| §10.1 failures are not messages | `error thinking: Expecting value…` as a chat bubble |
| §11.1.3 promotion only | ambient noise entering conversation history |
| §12.8 no private lifecycles | the next `core.py` |
