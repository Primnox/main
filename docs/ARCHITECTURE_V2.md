# Primnox V2 — Architecture

> Status: proposal. Supersedes the implicit V1 architecture described at the
> bottom of this document. Written against the codebase as of 2026-08-14
> (branch `claude/remove-electron`).

**Companion documents**

| Document | Role |
|---|---|
| [CONVERSATION_RUNTIME_SPEC.md](CONVERSATION_RUNTIME_SPEC.md) | **Normative.** The contracts every subsystem implements. Where it and this document disagree, it wins. |
| [schema/primnox_v2.sql](schema/primnox_v2.sql) | Executable DDL, constraint-tested |
| [schema/primnox_v2_erd.md](schema/primnox_v2_erd.md) | Entity relationships and delete behaviour |

This document is the *rationale*: why the design is shaped this way, and how
to get there from V1. The spec is the *contract*.

---

## 0. The one-sentence change

**V1's unit of work is a function call. V2's unit of work is an object.**

Everything else follows from that. A function call cannot be named, addressed,
cancelled, resumed, replayed, or attributed after the fact — which is why V1
cannot have a stop button, cannot show a queue, cannot survive a reconnect, and
cannot tell you which reply a token belongs to.

---

## 1. Principles

1. **The backend owns state. The frontend renders it.**
   The client never reconstructs, infers, or guesses. If the UI needs to know
   something, the backend said it explicitly.

2. **Every event has identity.**
   `event_id`, `turn_id`, `sequence`. No anonymous broadcasts.

3. **Chat owns nothing but conversation.**
   Not file parsing, not OCR, not artifact storage, not context assembly.
   Chat *references* those things by id.

4. **Expensive work is a Job.**
   Jobs are addressable, cancellable, and survive a crash.

5. **Models are interchangeable compute.**
   The runtime — not the provider — defines the tool contract.

6. **Local-first is the constraint, not the excuse.**
   SQLite, one process, no Kafka, no Postgres. The design has to earn its
   complexity on a laptop.

7. **One database, one source of truth, one immutable log.**
   State and the event describing it commit together or not at all.

8. **Replay is recovery. Streaming is delivery.**
   Never blurred. No token is ever emitted twice; no stored text is ever
   replayed as if it were live.

9. **Contracts before features.**
   Every subsystem implements the Conversation Runtime Specification. A
   subsystem that needs a lifecycle the spec cannot express is a reason to
   amend the spec — not to invent a private one. That failure mode is exactly
   what produced `core.py`.

---

## 2. The object model

```
Conversation
 └── Turn                (one user message → one assistant response)
      ├── Job[]          (chat / tool / skill / asset / memory)
      └── Event[]        (the append-only stream, replayable)

Workspace                (referenced by Turns, outlives them)
Asset                    (referenced by Turns, outlives them)
```

Conversations do **not** own workspaces or assets. They reference them. A
conversation can be deleted without destroying the React app it produced.

### 2.1 Conversation

```python
Conversation:
    id: str                 # conv_<uuid7>
    title: str
    folder_id: str | None
    created_at: int
    updated_at: int
    incognito: bool         # set at creation, immutable
```

There is deliberately no `last_seq` here. The reconnect anchor is a single
**global** cursor held by the client, not a per-conversation high-water mark —
see §3.1 and §3.3 for why that is sufficient rather than lossy.

### 2.2 Turn

The abstraction V1 is missing entirely.

```python
Turn:
    id: str                 # turn_<uuid7>
    conversation_id: str
    seq_in_conversation: int
    user_message: Message
    assistant_message: Message | None
    status: TurnStatus
    error: TurnError | None
    created_at: int
    completed_at: int | None
```

```python
class TurnStatus(str, Enum):
    QUEUED           = "queued"            # accepted, not started
    BUILDING_CONTEXT = "building_context"  # assembling the prompt bundle
    THINKING         = "thinking"          # model call in flight, no token yet
    STREAMING        = "streaming"         # tokens arriving
    TOOL_RUNNING     = "tool_running"      # blocked on a tool job
    AWAITING_INPUT   = "awaiting_input"    # blocked on a permission prompt
    COMPLETED        = "completed"
    FAILED           = "failed"
    CANCELLED        = "cancelled"
```

`thinking` and `streaming` are separate deliberately. "Waiting on a slow
provider" and "receiving a slow reply" are indistinguishable under one spinner,
and telling them apart is most of what a status is for.

**There is no global `thinking` state.** The current V1 `broadcast("state",
{"value": "idle"})` is deleted. Status is per-turn, and the UI derives whatever
aggregate indicator it wants from the set of live turns.

`AWAITING_INPUT` is required by the existing permission flow
(`permission_manager.py` + `POST /api/permission_response`), which today is a
broadcast the backend forgets it sent.

### 2.3 Turn state machine

```
QUEUED ──► BUILDING_CONTEXT ──► THINKING ──► STREAMING ──► COMPLETED
                  │                 │  ▲         │  ▲
                  │                 ▼  │         ▼  │
                  │              TOOL_RUNNING ────────┤
                  │                 │  ▲              │
                  │                 ▼  │              │
                  │            AWAITING_INPUT ─────────┤
                  │                 │                 │
                  ▼                 ▼                 ▼
                FAILED          CANCELLED         COMPLETED
```

Legal from any non-terminal state: `→ FAILED`, `→ CANCELLED`.
Terminal states never transition. A cancelled turn **keeps its partial
assistant text** and is persisted — losing the user's half-generated answer is
the thing a stop button must not do.

### 2.4 Job

```python
Job:
    id: str                 # job_<uuid7>
    turn_id: str | None     # null for ambient/scheduled jobs
    kind: JobKind           # chat | tool | skill | asset | memory | maintenance
    status: JobStatus       # queued|running|completed|failed|cancelled
    payload: dict
    result: dict | None
    error: str | None
    cancel_requested: bool
    attempts: int
    created_at: int
    started_at: int | None
    finished_at: int | None
```

A crash leaves rows in `running`. On boot the scheduler sweeps them: idempotent
kinds requeue, non-idempotent kinds move to `failed` with
`error = "interrupted by shutdown"`. Nothing is silently lost.

### 2.5 Asset

Files stop being parsed inline in the HTTP handler (V1 does this in
`server.py:256-340`, inside the request, on the event loop).

```python
Asset:
    id: str                 # asset_<uuid7>
    kind: str               # pdf | image | audio | text | code | screenshot | transcript
    source: str             # upload | screenshot | recording | watch_folder
    original_name: str
    path: str               # content-addressed, under appdata/assets/
    sha256: str
    bytes: int
    status: str             # ingesting | ready | failed
    extracted_text: str | None
    page_count: int | None
    metadata: dict
    created_at: int
```

Ingestion is an asset Job: hash → store → extract → chunk → embed → index. A
turn referencing an asset that is still `ingesting` waits on it explicitly and
reports that in the UI, instead of V1's behaviour of silently sending an empty
string to the model.

This is where the scanned-PDF problem stops being a special case in a chat
handler and becomes an asset with `extracted_text = None` and
`metadata.ocr_required = true`.

### 2.6 Workspace

Generated artifacts stop living inside message text.

```python
Workspace:
    id: str                 # ws_<uuid7>
    kind: str               # react | python | markdown | html | notebook | doc
    title: str
    origin_turn_id: str     # who created it
    current_version: int
    created_at: int
    updated_at: int

WorkspaceVersion:
    workspace_id: str
    version: int
    files: dict[str, str]   # path → content
    created_by_turn_id: str
    created_at: int
```

Versioned, because "only modify line 742" and "undo that" are the operations
that break V1 today. A workspace edit is a diff against
`current_version`, not a regeneration.

---

## 3. The event protocol

### 3.1 Envelope

Every event on the socket, without exception:

```json
{
  "event_id": "evt_01J8X...",
  "sequence": 4813,
  "ts": 1786650256334,
  "scope": "conversation",
  "conversation_id": "conv_01J8W...",
  "turn_id": "turn_01J8X...",
  "kind": "token",
  "payload": { "text": "hello" }
}
```

- `sequence` is **global** — one counter for the whole runtime, not per
  conversation and not per turn. Reconnect is then a single cursor
  ("everything after 4812") instead of a map of per-conversation cursors.
  `turn_id` already carries ownership; the sequence only has to carry order.
- It is **gapless**, assigned by incrementing a counter row inside the same
  transaction as the event insert. `AUTOINCREMENT` is wrong here: a
  rolled-back `AUTOINCREMENT` burns its value permanently, and a client then
  cannot distinguish "nothing happened" from "I missed something".
- Gaplessness serializes appends on one row, which costs nothing — WAL already
  permits exactly one writer.
- `turn_id` is `null` only for ambient events (§6).
- Events are appended **before** they are pushed to sockets. If the push
  fails, the event still happened.

A global cursor is only sufficient because of one rule, which is normative in
CRS §3.3 and worth stating here too:

> **The event log is not the history.** Conversation history must be fully
> reconstructable from the state tables alone. The log exists solely to close
> the gap between a client's last-seen state and live.

That is what makes it safe for a client to advance its cursor past events it
was never shown — events for conversations it does not have open. Those events
are not lost information; their effects are durable in `turns`, `messages`,
`workspaces` and `assets`, and will be read the next time that conversation is
opened. Without that rule, a global cursor would force every client to receive
every event for every conversation, and filtering would silently drop state.

### 3.2 Event kinds

Registered set — the authoritative list is CRS §3.6. A client receiving an
unknown kind ignores it and still advances its cursor, which is what makes
adding kinds backward-compatible.

| Kind | Payload | Notes |
|---|---|---|
| `turn.created` | `{turn, user_message}` | first event of every turn |
| `turn.status` | `{status, detail?}` | replaces V1's global `state` |
| `turn.completed` | `{assistant_message, usage}` | |
| `turn.failed` | `{code, message, retryable}` | **never** a chat message |
| `turn.cancelled` | `{partial_text}` | |
| `token` | `{text}` | append-only, never replaces |
| `job.started` | `{job_id, kind, label}` | |
| `job.progress` | `{job_id, phase, pct?}` | |
| `job.completed` | `{job_id, result_ref}` | |
| `tool.call` | `{job_id, name, arguments}` | |
| `tool.result` | `{job_id, status, summary, result_ref}` | |
| `permission.request` | `{job_id, action, detail, options}` | drives `AWAITING_INPUT` |
| `asset.ready` | `{asset_id, kind, name}` | |
| `workspace.created` | `{workspace_id, kind, title}` | |
| `workspace.updated` | `{workspace_id, version, changed_paths}` | |
| `privacy.scrub` | `{mapping, model}` | unchanged semantics |
| `memory.written` | `{memory_id, text}` | |

Errors are a **first-class event type with a `retryable` flag**, not a
`message` from "Primnox". This alone deletes the class of bug where
`error thinking: Expecting value: line 1 column 1 (char 0)` renders as five
assistant bubbles.

### 3.3 Reconnect

**Replay is recovery. Streaming is delivery. The two are never blurred.**

```
client → { "type": "hello", "last_event_seen": 4812,
           "conversations": ["conv_X"], "want_ambient": true }

server → events 4813, 4814, 4815 …   (filtered to those conversations)
       → { "kind": "sync.complete", "payload": { "head": 4831 } }
       → … live stream continues …
```

Like a TCP acknowledgement. If `last_event_seen` is already the head, zero
events are replayed — and `sync.complete` is still sent, because that is the
client's signal that it is live.

On `sync.complete` the client sets its cursor to `head`, **not** to the highest
sequence it actually received. The difference matters: events filtered out
were for conversations it does not have open, and per §3.1 their effects are
already durable in the state tables.

The runtime never simulates streaming by replaying stored text. No fake typing
of a completed response.

If `last_event_seen` predates retention (§7), the runtime answers
`sync.required` instead of a partial replay, and the client reloads from state.

### 3.4 Client-side reduction

The client is a pure fold:

```ts
function reduce(state: ConvState, e: Event): ConvState
```

Out-of-order events (possible across a reconnect boundary) are buffered by
`sequence` until the gap closes. Duplicate `event_id` is dropped. This is what
makes "half-written, missing, or overwriting an older reply" structurally
impossible rather than patched.

---

## 4. Services

```
gateway/          HTTP + WebSocket. Transport only. No logic.
kernel/           Scheduler, job queue, event bus, cancellation.
chat/             Conversations, turns, streaming assembly.
context/          Context bundle builder.
models/           Provider adapters + Model Capability Layer (§5).
tools/            Tool runtime, isolation, the universal tool protocol.
assets/           Ingest, extract, chunk, embed, retrieve.
workspaces/       Versioned artifact storage.
memory/           Semantic memory (largely unchanged).
ambient/          Feed, proactive, meetings, reminders (§6).
storage/          SQLite access, migrations, vault.
```

### 4.1 The request path

```
POST /conversations/{id}/turns  { text, asset_ids[] }
  └─► create Turn (QUEUED)
      append turn.created
      enqueue chat Job
      return { turn_id, sequence }        ← ~5ms, before any model work

scheduler picks up chat Job
  ├─ status → PREPARING
  ├─ ContextBuilder.build(turn)  ─────────┐
  ├─ Router.route(turn)  ◄────────────────┘ concurrent, NOT blocking
  ├─ status → STREAMING
  ├─ ModelGateway.stream(bundle)
  │    ├─ token          → append + push
  │    ├─ tool proposal  → enqueue tool Job, status → TOOL_RUNNING
  │    │                   ToolRuntime.execute() → result → resume
  │    └─ permission     → status → AWAITING_INPUT, park
  ├─ status → COMPLETED
  └─ enqueue memory Job (fire-and-forget, own Job, own retry)
```

Two differences from V1 worth naming:

**The router no longer blocks the first token.** V1 runs
`semantic_router.classify()` — a full model round-trip — before the stream
opens, on every message. In V2 routing runs concurrently with context assembly,
and if it resolves to a skill after streaming has begun, the turn transitions to
a skill job. Worst case matches V1; typical case saves an entire round-trip of
perceived latency.

**Skills are Jobs, not turn replacements.** V1's skill intercept `return`s
before the LLM ever runs, so a skill turn has no assistant message and no
conversational continuity. In V2 the Turn always exists and always completes;
a skill is a `kind="skill"` job whose result is folded into the turn.

### 4.2 Concurrency

V1 holds one mutex across the entire pipeline (`core.py:332`). V2 replaces it
with:

- **Per-conversation serialization of *history mutation* only.** Appending the
  user message and appending the assistant message take the conversation write
  lock. Everything between them — streaming, tools, assets — runs unlocked.
- **A bounded worker pool** for jobs, so five queued turns don't spawn five
  concurrent model streams.
- **An explicit queue the user can see.** `QUEUED` turns are visible, ordered,
  and individually cancellable. The V1 behaviour of Enter-spam silently buying
  55 seconds of unstoppable work is gone.

### 4.3 Cancellation

```
DELETE /turns/{turn_id}
  └─► turn.cancel_requested = true
      for each running job: job.cancel_requested = true
```

Cooperative, checked at three points: the token loop, between agentic steps,
and inside long-running tools (which must implement `cancel()`). Hard-kill is
available for subprocess tools only. Partial text is preserved and persisted.

---

## 5. Model Capability Layer

The runtime defines the tool contract. Providers adapt to it, never the reverse.

V1 already contains an ad-hoc, undocumented version of this: `brain.py` has
`_TOOLS_UNSUPPORTED_MARKERS`, `_rejects_tools()`, and
`_remember_tools_unsupported()` — it discovers tool-calling support by parsing
HTTP 400 bodies and caches the answer. MCL is that instinct made explicit.

### 5.1 Capability profile

```python
Capabilities:
    tool_calling: Literal["native", "emulated", "none"]
    vision:       Literal["native", "emulated", "none"]
    json_mode:    bool
    streaming:    bool
    context_window: int
    max_output: int
    parallel_tool_calls: bool
```

Resolved from a static registry, overridden by runtime probes, cached per
`(base_url, model)`. Nothing outside `models/` ever branches on provider name.

```python
executor = NativeToolExecutor() if caps.tool_calling == "native" else EmulatedToolExecutor()
```

### 5.2 Universal tool protocol

One schema, Primnox's own — not OpenAI's, not Anthropic's:

```json
{
  "name": "run_shell",
  "description": "Execute a shell command",
  "parameters": { "command": { "type": "string", "required": true } },
  "danger": "high",
  "cancellable": true
}
```

Provider adapters translate this into whatever the wire format demands. Adding
a provider means writing a translation, never touching `tools/`.

### 5.3 Emulation grammar

For `tool_calling: "emulated"`, inject a grammar the model can actually hit:

```
<tool name="run_shell">
{"command": "git status"}
</tool>
```

Delimited, not free-form JSON — a bare-JSON contract fails on any model that
prefixes prose, and prose-prefixing is exactly what weak models do. The parser
scans for the delimiters, extracts, validates against the schema, and on
failure issues **one** structured correction ("your tool block was malformed;
here is the schema") before falling back to treating the output as prose.

### 5.4 Vision emulation

`vision: "emulated"` routes images through the asset pipeline —
OCR (`easyocr`) + UIA/layout description (`spatial_engine.py`) — and injects a
text description. A text-only model gains pseudo-vision instead of failing.

### 5.5 Structured continuation

Tool output is injected as a typed record, not a raw log dump:

```json
{"type": "tool_result", "tool": "run_shell", "status": "success",
 "summary": "3 files changed", "output_ref": "asset_01J8..."}
```

Large outputs become assets and are referenced, not inlined — which is also how
a 200k-line log stops blowing the context window.

### 5.6 What this unlocks

Model hot-swap mid-conversation. Because the tool contract belongs to the
runtime, switching from Qwen to GPT-5 to DeepSeek inside one conversation
changes nothing about the conversation's structure. Models become
interchangeable compute engines. Neither ChatGPT nor Claude exposes this.

---

## 6. The ambient layer

Your outline doesn't cover this, and it's a third of the running code
(`feed_manager.py`, `proactive.py`, `meeting_recorder.py`,
`reminder_manager.py`, `emotion_agent.py`, `profiler.py`).

These produce events with **no turn and no conversation**. They get their own
stream:

```json
{ "event_id": "evt_...", "conversation_id": null, "turn_id": null,
  "scope": "ambient", "ambient_seq": 118, "kind": "now_playing", "payload": {...} }
```

Ambient events consume **no global sequence numbers** — they carry a separate,
non-durable `ambient_seq` for local ordering only. They are **not** persisted
to `events` (ephemeral telemetry; the island doesn't need replay), and they
never enter a conversation unless promoted:

- A proactive suggestion the user accepts → creates a Turn.
- A meeting recording that ends → creates an Asset.
- A fired reminder → a system Turn in the target conversation.

Promotion is the only bridge. This is what stops ambient noise from polluting
conversation history, which in V1 it structurally can (everything goes down the
same unaddressed pipe).

---

## 7. Storage

One database, table namespaces instead of files. Splitting state across
database files is prohibited (CRS §4.1).

```
appdata/primnox.db
  schema_migrations
  event_seq
  folders, conversations, turns, messages
  assets, asset_chunks, asset_embeddings, turn_assets
  jobs
  events
  workspaces, workspace_versions, workspace_files, turn_workspaces
  memories
  settings
appdata/vault/            encrypted secrets (unchanged)
appdata/assets/           content-addressed blobs
```

Full DDL: [schema/primnox_v2.sql](schema/primnox_v2.sql). Relationships and
delete behaviour: [schema/primnox_v2_erd.md](schema/primnox_v2_erd.md).

The reason is correctness, not tidiness: **a turn status change and its event
append must be atomic.** Across two SQLite files they cannot be, without
`ATTACH` and a shared journal — and if a crash lands between them the client's
replayed stream disagrees with the turn's stored status, which is precisely the
inconsistency the event log exists to prevent.

One turn completion is one transaction:

```sql
BEGIN IMMEDIATE;
  UPDATE event_seq SET value = value + 1 WHERE id = 1;
  UPDATE turns SET status = 'completed', completed_at = ? WHERE id = ?;
  INSERT INTO messages (...) VALUES (...);
  INSERT INTO events (sequence, event_id, kind, ...)
    VALUES ((SELECT value FROM event_seq WHERE id = 1), ?, 'turn.completed', ...);
COMMIT;
-- sockets are written AFTER commit, never inside the transaction
```

Either both exist, or neither does.

### 7.1 Required configuration

| Setting | Value | Reason |
|---|---|---|
| `journal_mode` | `WAL` | concurrent reads while streaming writes |
| `synchronous` | `NORMAL` | correct under WAL; `FULL` costs latency for no gain here |
| `foreign_keys` | `ON` | referential integrity is not optional |
| `busy_timeout` | `5000` | absorbs contention instead of erroring |
| Migrations | version table, forward-only | refuse to start on an unknown newer version |

`foreign_keys` is **per-connection** in SQLite. Setting it once at startup does
nothing for the rest of the pool — every connection has to set it.

`BEGIN IMMEDIATE` for anything that will write. A deferred transaction upgrades
mid-flight and can fail with `SQLITE_BUSY` after doing partial work.

### 7.2 Retention

`events` is pruned by age or count; `min_retained_seq` is tracked so a client
presenting a cursor older than retention gets a full-resync directive rather
than a silently incomplete replay. An unbounded event log on a laptop is a
disk-space bug waiting to happen.

Retention can never destroy history — by §3.1's rule, history lives in the
state tables, and any retention policy that would lose user-visible state is
invalid by construction.

### 7.3 Carried over

Retain `memory.db`'s corruption-recovery path (`memory.py:83-101`) — restore
from vault, else move aside and start clean. It's good, and it was earned the
hard way.

### 7.4 Incognito

With a persisted event log this needs an explicit rule: an incognito
conversation writes **no** rows to `conversations`, `turns`, `messages`, or
`events`. Its events exist only in memory and only for connected sockets.
Reconnect into an incognito conversation loses history — correct, and surfaced
in the UI rather than silently tolerated.

---

## 8. Where the Privacy Mirror goes

Currently inside `brain.think_stream` (`brain.py:1131`), wrapping the stream
and rehydrating tokens. Keep the mechanism; move the boundary.

In V2 scrubbing is a **Model Gateway concern**, applied to the outbound Context
Bundle and the inbound token stream, gated by `is_local_provider`. It is not a
chat concern and not a brain-internals concern.

This matters more in V2 than V1, because the Context Bundle now aggregates
asset text, workspace contents, and retrieved memory — considerably more
surface than V1's single prompt. One gate, one place, one audit point.

---

## 9. Migration

Every stage ships independently and leaves the app working. No big bang.

### Stage 0 — Schema + spec
Land `primnox.db` alongside the existing databases, with the migration runner
and the required PRAGMAs. Backfill `chat.db` → `conversations`/`turns`/
`messages` (each V1 message pair becomes one completed turn). Nothing reads
from it yet. Adopt CRS/1.0 as the governing contract.

### Stage 1 — Identity (no UX change)
Add `Turn`, add the event envelope, assign `turn_id` + `sequence` to every
existing broadcast. Frontend routes by id instead of appending to one global
buffer. **Deletes:** cross-window token bleed, lost replies, overwritten
replies.

### Stage 2 — Jobs + cancellation
Introduce the job table and scheduler. `POST /turns` returns before work
starts. `DELETE /turns/{id}` works. **Deletes:** the unstoppable Enter-spam
queue.

### Stage 3 — Per-turn status
Remove the global `state` scalar. Queue becomes visible. Errors become
`turn.failed` with a retry affordance. **Deletes:** raw Python exceptions
rendered as assistant messages.

### Stage 4 — Asset service
File parsing moves out of the HTTP handler into ingest jobs. Chat receives
`asset_id` only.

### Stage 5 — Workspaces
Generated code/docs leave message bodies. Versioned edits.

### Stage 6 — Model Capability Layer
Formalize the existing ad-hoc probing. Emulated tool calling for local models.

### Stage 7 — Ambient separation + context service
Ambient gets its own scope. Context assembly leaves the chat path.

Stages 1–3 are where essentially all current user-visible pain lives, and they
are prerequisites for everything after.

### Module fate

| V1 | V2 |
|---|---|
| `core.py` `_process_input_locked` | `chat/turns.py` + `kernel/scheduler.py` |
| `core.py` background worker | `kernel/scheduler.py` (maintenance jobs) |
| `core.py` feed/proactive wiring | `ambient/` |
| `server.py` broadcast | `kernel/events.py` + `gateway/websocket.py` |
| `server.py` file extraction | `assets/ingest.py` |
| `brain.py` provider adapters | `models/providers/` |
| `brain.py` tool loop | `tools/runtime.py` |
| `brain.py` privacy wrapper | `models/gateway.py` |
| `brain.py` `_rejects_tools` etc. | `models/capabilities.py` |
| `skills/skill_router.py` | `kernel/router.py` + `tools/skills/` |
| `usePrimnox.ts` (37KB, all state) | `stores/` (conversation, turns, ambient) + thin socket client |

`core.py` does not survive as a file. Neither does the single 37KB hook.

---

## 10. What V1 got right — keep it

Not everything needs replacing, and the V2 rewrite must not lose:

- **Loopback-only binding** with the WS origin allowlist (`server.py:213`).
  The cross-site WebSocket hijack guard is subtle and correct.
- **Privacy Mirror** as a mechanism — scrub at the cloud boundary, rehydrate
  the stream.
- **`memory.db` corruption recovery** — restore from vault, else move aside.
- **Context-overflow handling** — `_drop_oldest_turn` / `_context_too_long`.
- **The local-provider circuit breaker** and Groq model rotation.
- **`_explain_api_error`** — mapping provider errors to actionable text. In V2
  it populates `turn.failed.message` instead of faking an assistant reply.
- **Tauri's stale-port reclaim** (`backend.rs`) — unglamorous, saves real pain.
- **Vault + mnemonic backup.**

---

## Appendix A — V1 for reference

Two processes: Tauri/WebView2 frontend, FastAPI backend on 127.0.0.1:4009,
spawned as a child process by `src-tauri/src/backend.rs`.

`POST /message` hands to `BackgroundTasks`, returns `{"status":"ok"}` with no
id. `core.handle_text_input` takes a per-session mutex held across the entire
pipeline: reminder intercept → skill routing (blocking model call) → memory
search → context assembly → `think_stream` → block extraction → persistence.
Post-exchange memory extraction and auto-titling run in a detached thread —
three upstream calls per message in total.

`broadcast(type, data)` fans out to every connected socket. ~45 event types.
`token` carries `{"text"}` only — no session, no message id, no sequence — and
the client appends to a single global buffer. `state` is a global scalar.
Errors are broadcast as `message` events from "Primnox".

Storage: `chat.db` (folders/sessions/messages), `memory.db` (memories/notes/
tasks/events), `settings.json`, `memory.db.vault`, rotating local backups.

The consequences are all one consequence: **the unit of work is a function
call**, so nothing can be named, cancelled, resumed, or attributed.
