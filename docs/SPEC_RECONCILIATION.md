# Your spec vs. what's built

Written 2026-08-14. Three parts: what I changed to match your spec, what I kept
and why, and what isn't built yet.

---

## 1. Changed to match your spec

### Turn states

You split one state into three. You were right, and it's done.

I had a single `preparing` state covering everything before tokens arrived.
You split it, and the split matters:

| State | What's happening |
|---|---|
| `building_context` | Putting the prompt together |
| `thinking` | Waiting for the model's first token |
| `streaming` | Tokens are arriving |

The reason to keep `thinking` and `streaming` apart: a slow provider and a long
reply look exactly the same under one spinner. Now the app can say which.

A turn moves to `streaming` when the first token lands, not before.

I ran a real turn and watched it go `building_context → thinking → streaming`.

### Job names

Jobs are now named by the service that owns them: `chat.reply`, `tool.python`,
`asset.ocr`, `context.build`.

The database checks the prefix rather than listing every allowed name. So a new
job type is just a line of code in its own service — no database migration —
but an unprefixed name still gets rejected.

The scheduler looks jobs up in a table instead of a chain of `if` statements.
That's the difference between the kernel coordinating work and the kernel
growing a new branch every time you add a feature.

---

## 2. Kept, and why

### `awaiting_input`

Your state list has eight states and doesn't include one for "waiting on the
user". But your Kernel section lists a Permission Manager.

Those two don't fit together. When the app asks permission to run something, the
turn has to sit somewhere, and every other state would be untrue while it waits.

I read that as an oversight, so I kept `awaiting_input`. If you left it out on
purpose, then permission prompts need somewhere else to live and it's worth
deciding where.

### "The event log isn't the history"

This isn't in your spec, and it's the rule that makes your global counter work.

The idea: you can rebuild every conversation from the normal tables, without
reading the event log at all. The log only exists to catch a client up after it
disconnects.

That's what lets a client skip past events it never saw — events belonging to
conversations it doesn't have open. Without the rule, every client would have to
receive every event for every conversation, and filtering them would quietly
lose data.

It's also why deleting old events can never destroy anything.

### Counting events without gaps

I don't use `AUTOINCREMENT` for the event counter.

If a transaction fails, `AUTOINCREMENT` still uses up its number and leaves a
permanent hole. A client seeing a hole can't tell "nothing happened" from "I
missed something" — which is the only question the counter is there to answer.

Instead the counter is a row that gets bumped inside the same transaction, so a
failure takes the number back with it.

### Failures say whether retrying will help

Your spec has a `failed` state but doesn't say what a failure looks like.

A missing API key and a rate limit are both failures, but only one is worth a
retry button. So each failure carries a flag saying whether retrying will
actually help — and it has to be honest, not decorative.

---

## 3. Not built yet

On purpose, and in your roadmap order. Each one plugs into the runtime rather
than changing it.

Roadmap revised 2026-08-14: Sandbox, Assets and Workspaces folded into V2.0 as
ship scope, and the Privacy Gateway promoted to its own stage.

| Stage | Focus | Status |
|---|---|---|
| V2.0 | Chat runtime — Conversation, Turn, Job, Event, **Sandbox, Assets, Workspaces** | **built and tested** (116 tests) |
| V2.1 | Privacy Gateway | boundary exists, scrub is an identity function |
| V2.2 | Memory System | **built** — store, dedupe, search, soft delete |
| V2.3 | Voice | not started |
| V2.4 | Agent Workflows | planner built, multi-agent not started |

One thing needs a decision first.

**Workflow engine vs. jobs.** You describe both a durable workflow engine and a
job scheduler. They do overlapping things — both handle retries, resuming, and
cancelling.

Right now jobs handle all three. If the app crashes mid-reply, the turn is
marked failed and keeps whatever text it had; it doesn't pick up where it left
off.

Real resuming means making every step separately durable. That's a genuine
addition, not a tweak. Worth deciding whether the workflow engine sits on top of
jobs or replaces them before building anything on either.

Planner mode has since been built, so it is no longer an open question. The
`<plan>` block you spec'd is emitted as a `plan.proposed` event from the turn
loop (`kernel/scheduler.py`), asserted by a golden test, and rendered by the
client — a first-class event rather than prose scraped out of the token stream.

---

## 4. Three things I only found by running it

**Renaming a table breaks other tables' links to it.** Since SQLite 3.25,
renaming `turns` to `turns_old` also quietly rewrites every other table's
reference to point at `turns_old`. Dropping the old table then leaves all of
them pointing at nothing — 104 broken references, measured. Fixed by turning on
`legacy_alter_table` during the rebuild. Any future migration that rebuilds a
table others link to needs the same thing.

**`executescript()` commits behind your back.** Used inside a transaction it
ends the transaction early, so if a later step fails you're left half-migrated
with nothing to roll back. Worse, the failed rollback then throws its own error
and hides the real one.

**A migration's "already done?" check has to cover everything it touches.** Mine
only checked the `turns` table. So when a run died partway, the next startup
thought the whole migration was finished and left the `jobs` table on the old
rules forever — while the version number said it was up to date.

All three are fixed. The migration now works on both paths: a fresh install, and
a real v1 database with data in every table that links to `turns`. Nothing lost,
no broken references, and running it twice does nothing the second time.
