# Primnox V2

A separate workspace implementing the V2 architecture. It runs alongside V1 —
different ports, different database — so nothing here can break the shipping
app.

| | V1 | V2 |
|---|---|---|
| Backend | `127.0.0.1:4009` | `127.0.0.1:4109` |
| Frontend | `:5173` | `:5273` |
| Database | `chat.db` + `memory.db` | `primnox.db` (one file) |

**Design documents**

- [`../docs/CONVERSATION_RUNTIME_SPEC.md`](../docs/CONVERSATION_RUNTIME_SPEC.md) — normative. The contracts.
- [`../docs/ARCHITECTURE_V2.md`](../docs/ARCHITECTURE_V2.md) — rationale and migration.
- [`../docs/SPEC_RECONCILIATION.md`](../docs/SPEC_RECONCILIATION.md) — what's adopted, kept, and unbuilt.
- [`../docs/schema/primnox_v2.sql`](../docs/schema/primnox_v2.sql) — the schema this backend applies.

## The kernel

Four subsystems, each with exactly one owner. Everything else — Chat, Assets,
Workspaces, Memory, Voice, Agents — is a consumer of these.

| Kernel service | Owns | Where |
|---|---|---|
| Workflow Engine | durable turn/job execution | `kernel/scheduler.py` |
| Event Bus | live events + reconnect replay | `kernel/events.py` |
| Sandbox Manager | safe code execution | `sandbox/` |
| Privacy Gateway | scrub → validate → rehydrate | `models/gateway.py` *(boundary only — V2.1)* |
| Verification Layer | proving the runtime behaves | `tests/` |

**Turn states**: `queued → building_context → thinking → streaming → completed`,
plus `tool_running`, `awaiting_input`, `failed`, `cancelled`. `thinking` and
`streaming` are separate on purpose — one is waiting on the provider, the other
is receiving the reply, and a single spinner cannot tell you which.

## Running it

```bash
cd v2/backend && python run.py
```

```bash
cd v2/frontend && npm install && npm run dev
```

The backend reads the provider you already configured in V1. To run with no
network and no key at all — which is how you tell a runtime bug apart from a
provider problem:

```bash
cd v2/backend && python run_echo.py
```

Any OpenAI-compatible or Anthropic endpoint works, including Ollama and
LlamaCpp:

```bash
PRIMNOX_BASE_URL=https://api.groq.com/openai/v1 PRIMNOX_API_KEY=… PRIMNOX_MODEL=llama-3.3-70b-versatile python run.py
```

## What is built

```
backend/primnox2/
  ids.py              UUIDv7 identifiers (§1)
  paths.py            content-addressed storage layout
  storage/db.py       one database, PRAGMAs, migrations, boot sweep (§4, §10.3)
  storage/schema.sql  19 tables, constraints enforcing the spec
  kernel/events.py    global gapless sequence, append-before-deliver, replay (§3)
  kernel/scheduler.py job queue, bounded workers, the agentic turn loop (§6, §9)
  kernel/trace.py     Replay Recorder — per-turn execution traces
  chat/turns.py       conversations, turn lifecycle, state machine (§2, §5)
  chat/ephemeral.py   the RAM-only runtime incognito conversations live in (§11.2)
  context/service.py  context bundles: token budget, ordering, asset references
  assets/service.py   ingest → hash → dedupe → extract → chunk (§2.6)
  workspaces/service.py  immutable versions, carry-forward edits, revert (§2.5)
  sandbox/            the Sandbox Manager, below — its own service
  tools/              universal tool protocol, emulation, permission broker
  models/gateway.py   capability layer, providers, the privacy boundary (§13)
  app.py              HTTP + WebSocket. Transport only.

frontend/src/
  lib/crs.ts          the client: pure fold, dedupe, out-of-order buffer, reconnect (§8.4)
  App.tsx             shell, transcript, composer, context rail
```

### The Sandbox Manager

A kernel service, not a helper under the tool service. Tools do not execute
code — they *request execution*.

```
sandbox/permissions.py  manifests, three tiers, validated before launch
sandbox/workspace.py    ephemeral vs persistent execution directories
sandbox/snapshots.py    before/after content diffs — execution is reversible
sandbox/appcontainer.py AppContainer isolation (V2's own, not V1's)
sandbox/supervisor.py   process supervision, timeouts, tree kill
sandbox/manager.py      ExecutionSession lifecycle and events
```

Every run is an `ExecutionSession` row: addressable, cancellable, and durable
across a crash. One turn may own several.

**What isolation actually enforces**, measured rather than assumed:

| Operation | Enforced |
|---|---|
| Read/write outside the workspace (incl. Documents) | ✅ blocked |
| Network access | ✅ blocked (no capability at all) |
| Registry **writes**, including the `Run` persistence key | ✅ blocked |
| Reads of protected registry keys | ✅ blocked |
| Reads of general machine config (`HKLM\SOFTWARE`, `HKCU\Environment`) | ❌ **readable** |

So `registry: deny` in a manifest means *no writes, no protected reads*. A
sandboxed script can still read ordinary machine configuration — a disclosure
boundary, not an integrity one. Stated here because a manifest claiming more
than the OS delivers is worse than no manifest.

If AppContainer cannot be provisioned, execution is **refused** rather than
silently downgraded. `PRIMNOX2_ALLOW_UNSANDBOXED=1` overrides that, and the
execution record stores which backend actually ran.

### Permissions

Every execution is gated. By default nothing prompts:

```
PRIMNOX2_AUTO_APPROVE=all   (default) grant everything, record it
PRIMNOX2_AUTO_APPROVE=safe  grant the sandboxed offline tier, ask for shell
PRIMNOX2_AUTO_APPROVE=off   ask every time
```

`all` is a real reduction in defence — the prompt is the last gate before
model-generated code runs, so the sandbox boundary above becomes the only one.
Every auto-approval still emits `permission.request` and `permission.resolved`
with `choice: allow_auto`, so nothing is granted invisibly. That includes the
repeats: a turn-wide allowance re-announces itself on every use, because one
record for three runs describes the decision rather than the runs.

### Local models

Point `PRIMNOX_BASE_URL` at any OpenAI-compatible server and the runtime treats
it like any other provider. Ollama, verified:

```
PRIMNOX_BASE_URL=http://127.0.0.1:11434/v1
PRIMNOX_API_TYPE=openai
PRIMNOX_MODEL=qwen2.5:7b
PRIMNOX_API_KEY=
```

`is_local` is derived from the base URL, so the UI says **local** rather than
being told to.

Tool calling on a 7B goes through the emulated protocol, and that path is now
measured rather than assumed: 19 of 20 turns on qwen2.5:7b run the code and
report the right answer. Getting there took three fixes — see defect 13 in the
verification audit. The parser accepts `run_python({…})` and
`<run_python>…</run_python>` alongside the canonical block, because those are
what a 7B actually emits, and refusing a correct call over its punctuation is
not strictness worth having.

### Skills

A capability the model needs occasionally does not belong in the string every
turn carries. Teaching it about themed documents inline cost ~209 tokens on
every question, including the ones that will never make a document; the preamble
had grown from 623 to 1,023 tokens in an afternoon.

```
skills/<name>/SKILL.md      frontmatter: name, description, triggers
```

The prompt carries one line per skill. The body is inlined by the scheduler when
the request matches a trigger — a keyword match, not a model decision, because a
round trip on the local 7B is ~8 seconds and carries the tool-loop risk. A model
that wants one regardless can call `read_skill`.

### Themed documents

Generated files come out styled rather than as library defaults. The palettes
are the app's own, by name, so a deck built in `midnight` matches the interface
that produced it:

```
dark   signature · void · carbon · midnight · ember · phosphor
light  paper · clinical · sand · mono
```

`sandbox/doc_themes.py` is copied into every Python execution as
`primnox_docs.py`, so generated code imports it with no install and no network:

```python
from primnox_docs import Deck, Report, Doc, chart_style
Deck('x.pptx', theme='midnight', title='Title').slide('Heading', ['a', 'b']).save()
```

The styling lives in the helper because the alternative is asking the model to
write forty lines of colour and geometry per document — and the measurement
behind defect 14 says a 7B writes short scripts and gets long ones wrong.
Verified end to end: asked for "a dark theme that suits the subject", qwen2.5:7b
chose `phosphor`, wrote 21 lines, and produced a 4-slide deck whose background
and title colours are that theme's exact tokens. The helper is excluded from
the snapshot diff, so it never appears as a file the model produced.

### Built-in viewers

Anything Primnox produces is readable in the app without downloading it first.
PDFs and images go straight to the browser, which already knows them; Word,
Excel, PowerPoint, CSV and SQLite are parsed server-side by the same libraries
the sandbox used to write them, so the frontend needs no new dependency to read
any of them.

Read-only in the strong sense. The preview layer has no write path — a test
asserts the module contains no write call — the SQLite branch opens its file
`mode=ro`, and the viewer renders text nodes with no input or contenteditable
anywhere in it.

The files a turn produced now survive a reload too: they are rows in
`turn_assets`, so the history read carries them. Tool rows and executions are
still event-derived and still vanish (audit gap 9); the documents no longer do.

### Incognito

A conversation that writes nothing. No rows in `conversations`, `turns`,
`messages` or `events`; its events carry no sequence number, are delivered only
to connected sockets, and never enter the log (§11.2). The transcript lives in
`chat/ephemeral.py` for as long as the process does — a page reload keeps it, a
restart ends it, and the UI says so instead of showing an empty conversation.

Whether a conversation is incognito is decided by asking its *id*, never by a
flag passed along the call chain: the event bus checks before it writes, so a
call site that forgets cannot leak a message onto the disk.

Attachments and the tools that persist — running code, creating or editing
workspaces — are unavailable there, and the model is told so up front rather
than discovering it through a refusal. §11.2.4 allows ephemeral or explicitly
promoted; neither is built, so the honest answer is that they are off.

The proof is a row count taken across every table a turn could touch, before
and after a complete incognito turn:
`test_a_whole_turn_writes_nothing`.

## The Verification Layer

```bash
cd v2/backend && python -m pytest tests/ -q       # 116 tests, ~10s
```

| Level | What it protects | Tests |
|---|---|---|
| L0 | the architecture itself — turn/event/database contracts | 33 |
| L1 | context budget, sequencing, versioning, permissions, error honesty | 40 |
| L2 | PDF conversation, tool→workspace, streaming reconnect | 12 |
| L3 | user simulation: multitask, stop halfway, switch chats, run/edit/rerun | 9 |
| L4 | chaos: real backend kill, killed sandbox, disk full, torn transaction | 8 |
| Golden | canonical conversations, compared against recorded signatures | 5 |
| Budgets | per-commit performance ceilings | 6 |
| Trace | the Replay Recorder | 6 |

Re-record golden signatures deliberately, never reflexively:

```bash
PRIMNOX2_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py
```

Measured against the budgets:

```
turn_accepted             0.7ms      50ms budget    (69x headroom)
first_token              21.6ms     400ms budget    (18x)
history_load_100_turns    0.9ms     200ms budget   (221x)
replay_1000_events        3.2ms     200ms budget    (63x)
context_build             0.2ms     250ms budget  (1408x)
```

`turn_accepted` is the one that matters: ARCH §4.1 promises the HTTP call
returns a turn_id before any model work starts. If it regresses, the runtime
has started doing work on the request path again.

## Deliberately not built

Memory (V2.2), Voice (V2.3) and Agent Workflows (V2.4) have tables and
contracts but no implementation, and the Privacy Gateway (V2.1) is a boundary
with an identity scrub rather than a real one — kept as an identity function so
nothing claims protection it is not providing.

Two decisions are still open:

**Workflow engine vs. jobs.** Jobs currently handle retry, resume and cancel.
Real resumption means making every step separately durable — a genuine
addition, not a tweak. Worth deciding whether the workflow engine sits on top
of jobs or replaces them before building on either.

**Native tool calling.** Every model goes through the emulated protocol today,
including models with native support. Behaviour is identical; native would only
shorten the prompt. Worth doing when prompt overhead starts to matter, not
before.

## The rule everything else follows from

**The event log is not the history** (§3.3). History is reconstructable from
the state tables alone; the log exists only to close the gap between a client's
last-seen state and live. That rule is what makes a single global cursor
sufficient rather than lossy, and what keeps retention from ever being able to
destroy data.
