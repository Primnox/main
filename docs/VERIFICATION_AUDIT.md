# Verification Layer — audit against the specification

Audited 2026-08-14 against *Primnox V2.0 — Verification Layer Specification*.
Every row is either implemented and passing, or listed as a gap. Nothing is
marked done on the strength of intent.

**190 tests, ~15 seconds, all passing.**

```bash
cd backend && python -m pytest tests/ -q
```

---

## 1. Kernel pillars

| Pillar | Responsibility | Where | State |
|---|---|---|---|
| Workflow Engine | durable turn execution | `kernel/scheduler.py` | built |
| Event Bus | live events + replay | `kernel/events.py` | built |
| Sandbox Manager | safe execution | `sandbox/` | built |
| Context Service | build model context | `context/service.py` | built |
| Verification Layer | prevent regressions | `tests/` | built |

The spec lists five pillars; a sixth — the **Privacy Gateway** — appears in the
architecture as a kernel service. It exists as a boundary (`models/gateway.py`,
every outbound call passes through it) but its scrub is an identity function.
That is V2.1 and is deliberately not claimed as done.

---

## 2. The five levels

| Level | Spec purpose | Tests | State |
|---|---|---|---|
| L0 | Contract tests | 33 | passing |
| L1 | Unit tests | 39 | passing |
| L2 | Integration tests | 12 | passing |
| L3 | User simulation | 9 | passing |
| L4 | Chaos testing | 8 | passing |
| — | Golden Conversations | 5 | passing |
| — | Performance Budgets | 6 | passing |
| — | Replay Recorder | 6 | passing |

### L0 — Contract tests

| Requirement | Test | State |
|---|---|---|
| Turn requires `turn_id`, `conversation_id`, `status`, `created_at` | `test_required_fields_present` | ✅ |
| Every declared transition is legal | `test_declared_transitions_are_legal` (parametrised) | ✅ |
| Illegal transition fails immediately | `test_illegal_transition_is_refused` | ✅ |
| Terminal states never transition | `test_terminal_states_never_transition` | ✅ |
| Event carries id, sequence, timestamp, type, payload | `test_no_anonymous_events` | ✅ |
| No anonymous events, ever | same | ✅ |
| Unregistered event kind refused | `test_unregistered_kind_is_refused` | ✅ |
| Turn completion is atomic | `test_turn_completion_is_atomic` | ✅ |
| No completed turn without its event | same | ✅ |
| No event without its state change | `test_rollback_returns_the_sequence_number` | ✅ |
| Single `primnox.db` validated | `test_single_database` | ✅ |

**Two documented deviations**, both deliberate:

1. **`cancelled` is reachable from every non-terminal state.** The spec's
   transition table allows `cancelled` only from `thinking` and `streaming`.
   CRS §9.1.3 requires cancelling a *queued* turn to take effect immediately,
   and without that the stop button cannot work on a turn that has not started
   — the exact V1 defect this rewrite exists to remove. Encoded as
   `test_cancel_reachable_from_every_live_state`, which asserts it from all six
   live states.

2. **`turn_id` is required on conversation-scoped events, not all events.**
   Ambient events (`scope: ambient`) and system events (`sync.complete`) have
   no turn by construction. Enforcing it universally would make the reconnect
   handshake illegal.

### L1 — Unit tests

| Requirement | Test | State |
|---|---|---|
| Context: token budget respected | `test_token_budget_respected` | ✅ |
| Context: ordering preserved | `test_ordering_preserved` | ✅ |
| Context: asset references intact | `test_asset_references_intact` | ✅ |
| Sequencer: 1,2,3 never 1,3,2 | `test_monotonic_under_concurrency` | ✅ |
| Workspace: create → modify → version → diff | `test_create_modify_version_diff` | ✅ |
| Workspace: every operation preserves history | `test_history_is_never_destroyed` | ✅ |
| Sandbox: write workspace ✅ | `test_workspace_write_allowed` | ✅ |
| Sandbox: read Documents → prompt | `test_documents_prompts_rather_than_allows` | ⚠️ see gap 2 |
| Sandbox: registry ❌ | `test_registry_denied_by_default` | ⚠️ see gap 3 |
| Sandbox: System32 ❌ | `test_system_denied_by_default` | ✅ manifest-level |

### L2 — Integration tests

| Requirement | Test | State |
|---|---|---|
| One asset created | `test_upload_ingest_context_chat` | ✅ |
| Turn references asset | same | ✅ |
| Citations preserved | same (asserts filename reaches the model) | ✅ |
| No duplicate ingestion | `test_no_duplicate_ingestion` | ✅ |
| Tool: one job | `test_generate_execute_workspace` | ✅ |
| Tool: one execution session | same | ✅ |
| Tool: workspace snapshot exists | same | ✅ |
| Tool: logs attached | same (asserts stdout on the session) | ✅ |
| Streaming: replay only missing events | `test_disconnect_reconnect_replays_only_the_gap` | ✅ |
| Streaming: no duplicated tokens | `test_duplicate_delivery_is_idempotent` | ✅ |
| Streaming: delayed/out-of-order packets | `test_out_of_order_delivery_is_buffered` | ✅ |
| Streaming: identical final message | asserted in all three | ✅ |

### L3 — User simulation

| Scenario | Test class | State |
|---|---|---|
| 001 React app + PDF summary | `TestScenario001MultiTask` | ✅ |
| 008 Stop halfway | `TestScenario008StopHalfway` | ✅ |
| 017 Switch conversations mid-stream | `TestScenario017SwitchConversations` | ✅ |
| 029 Generate → run → edit → run again | `TestScenario029RunEditRerun` | ✅ |

All four assert the spec's stated expectations, including "no orphan tokens"
(what was streamed equals what was stored) and "execution isolated" (the second
run cannot see the first run's files — verified live, not asserted on faith).

### L4 — Chaos

| Requirement | Test | State |
|---|---|---|
| Crash backend during streaming | `test_crash_mid_stream_then_recover` | ✅ real `kill`, not simulated |
| Reconnect, replay gap, resume | same (asserts delivered events survive) | ✅ |
| Kill Python during execution | `test_timeout_kills_and_reports_failure` | ✅ |
| Sandbox reports failure | same | ✅ |
| Workspace preserved, logs retained | same | ✅ |
| Disk full → graceful, no corruption | `test_asset_write_failure_is_graceful` | ✅ |
| Transaction interrupted → rollback | `test_rollback_leaves_no_inconsistent_turn_event_pair` | ✅ |
| No inconsistent turn/event state | same + `test_concurrent_writers_do_not_tear_state` | ✅ |

The crash test spawns a real child process, waits until it is genuinely
`streaming`, kills it, and then asserts the boot sweep resolves it — including
that events already delivered are *not* destroyed by recovery.

### Golden Conversations

| Requirement | State |
|---|---|
| Coding — "Write Fibonacci": workspace created, code valid, order preserved | ✅ the generated code is `compile()`d and executed, and its output checked against the real sequence |
| Explanation — "Explain recursion": deterministic, no duplicate paragraphs, no malformed markdown | ✅ |
| Behavioural signature compared on every run | ✅ |

Signatures deliberately exclude token *counts*, which are timing-dependent
(events batch every 100ms or 5 tokens). The concatenated text is compared
instead. A suite that fails randomly gets ignored, which is worse than none.

Re-record intentionally: `PRIMNOX2_UPDATE_GOLDEN=1 pytest tests/test_golden.py`

### Replay Recorder

Implemented in `kernel/trace.py`. Records, per turn: workflow states, every
event, sandbox actions, and provider calls. Off by default; enable globally
with `PRIMNOX2_TRACE=1` or per-turn via `POST /turns/{id}/trace`. Read back
with `GET /turns/{id}/trace`, which returns both the raw entries and a
human-readable timeline.

Database transactions are recorded via `recorder.note()` rather than
automatically — see gap 5.

---

## 3. Performance budgets

The spec's budget table was truncated in transmission, so these targets are
**mine, not yours** — set roughly an order of magnitude above measured values.
They need your review.

| Metric | Measured | Budget | Headroom |
|---|---|---|---|
| `turn_accepted` | 0.7 ms | 50 ms | 69× |
| `first_token` | 21.6 ms | 400 ms | 18× |
| `history_load_100_turns` | 0.9 ms | 200 ms | 221× |
| `replay_1000_events` | 3.2 ms | 200 ms | 63× |
| `context_build` | 0.2 ms | 250 ms | 1408× |
| `event_emit` | 0.1 ms | 25 ms | 412× |

`turn_accepted` is the load-bearing one: ARCH §4.1 promises the HTTP call
returns a `turn_id` before any model work begins. A regression there means the
runtime has started doing work on the request path again.

---

## 3a. Defects found by auditing (fixed)

Nineteen real bugs surfaced only because the audit asked "what did you actually
*observe*, versus what are you asserting". All are fixed, and all but the
UI-only ones carry regression tests.

**1. Abandoned turns poisoned the context. (Serious.)**

A turn cancelled before its first token has a user message and no assistant
message. History included it anyway, so pressing stop twice and then asking
something new produced three consecutive `user` messages in the prompt — and
the model answered the *first* one. Observed live: a question about an
uploaded file was answered with a lecture on TCP congestion control, because
that was an abandoned question two turns earlier.

Anyone who presses stop and then asks something else hits this. Fixed by
requiring a turn to have an assistant message before it enters history; a
cancelled turn *with* partial text is a real exchange and still counts.
Covered by `test_abandoned_turns_do_not_pollute_history`, which also asserts
no two `user` messages ever sit adjacent.

The duplicate `turns.context_messages()` carried the same bug and had no
callers. Deleted rather than fixed — two implementations of "build the prompt"
is one too many.

**2. The Retry button did nothing.**

It rendered, it hovered, it had no `onClick`. Clicking it was silently
inert — the same class of defect as V1's "hint overlay that lied". Now wired
to `POST /turns/{id}/retry`, which creates a *new* turn carrying
`retry_of_turn_id` (CRS §5.2.3) rather than reopening the failed one, so the
original stays as evidence. Three tests cover it. A sweep for other handler-less
buttons found none.

**3. Rapid Enter sent the same message five times.**

Measured: five `POST /turns` within **1.4ms**, identical text, composer already
cleared after the first. This is V1's exact defect, reintroduced — `send()`
read the draft from React state, and state updates are asynchronous, so every
keystroke in the same tick saw the pre-update value and the empty-guard never
fired. Fixed with a synchronous ref for both the in-flight flag and the draft
text. Re-measured: 1 POST.

**4. The composer lied about concurrent sends.**

While a turn was running, Send was *replaced* by Stop — implying you could not
send — but pressing Enter sent anyway, and worked. The runtime handles
concurrent turns correctly (verified: separate turns, separate tokens, zero
token events without a `turn_id`), so the fix was to make the UI honest: Stop
and Send now coexist.

**5. A crash left the UI showing "Writing" forever.**

`sweep_on_boot()` marked interrupted turns `failed` in the database and emitted
nothing. A reconnecting client replayed the gap, saw no terminal event, and sat
on a spinner permanently — the stuck-loading-state defect. The sweep now emits
`turn.failed` for every turn it resolves, inside the same transaction as the
state change (§4.2), so a reconnecting client learns about it in the replay.
Verified live: kill mid-stream → reconnect → "This reply was interrupted when
Primnox restarted", with the partial text kept and a working Retry.

**6. Reloading during a permission prompt stranded the turn. (Serious.)**

Found by turning `PRIMNOX2_AUTO_APPROVE=off` — the setting that makes the
prompt appear at all — and refreshing the page while one was on screen. The
turn came back as **"Waiting for you"** with no question, no buttons and no
way to answer it. The worker sat on the unanswered request for the full
600-second timeout, then denied itself.

The cause is a seam between two correct rules. Opening a conversation is a
state read, never a replay (§3.3.3), and the pending question lived only in
the broker's memory — the `permission.request` event that announced it was
behind the client's cursor. So the state read rebuilt a turn parked on a
question it could not see.

Fixed by making the question part of the state a client can read:
`broker.pending_for_turn()` exposes it and `GET /history` attaches it to any
turn in `awaiting_input`. Verified live: reload mid-prompt now restores the
question, the code preview and all three buttons, and answering from the
reloaded page runs the tool. Six regression tests cover the broker, which had
none at all before — including cancel-while-parked and "allow for this turn"
not asking twice.

**7. A manual approval reported itself as automatic.**

After answering, the settled block read *"run_python — approved
automatically"* whatever you had clicked, because the copy tested only for
`deny`. Someone reviewing what ran would have been told the machine let it
through when they had allowed it themselves. Now each resolution says what
actually happened: *you allowed this once* / *for the turn* / *you declined*,
with *approved automatically* reserved for the auto-approval it describes.

**8. Declining a tool made the model blame the sandbox.**

The denial reached the model as `"You declined this action."` and the reply
began *"The sandbox tool isn't available in this environment"* — false, and it
blamed the machine for the user's own choice. The tool result now states
plainly that the tool works and the user declined this call, and says not to
report it as unavailable.

**9. Silent grants were not all recorded. (Serious — it undercut the default.)**

`PRIMNOX2_AUTO_APPROVE=all` is defended in the source on one ground: every
auto-approval still emits `permission.request` and `permission.resolved`, "so
the UI and the event log show exactly what was granted". Measured against a
live two-tool turn, the log held **one** grant for **two** runs.

The first grant recorded a turn-wide allowance for the reusable action; every
later use hit a short-circuit that returned without emitting anything. So the
log described the *decision* and not the *runs* — which is the one thing the
justification claimed it did.

Now every grant announces itself, including reused ones, carrying the choice
that actually granted it. Verified live: two `run_python` calls, two records,
two executions. `test_every_silent_grant_is_still_recorded` asserts three
grants leave three records with three distinct ids.

Two things fell out of this:

- **Request ids could collide.** They were built from `id(arguments)` — a
  memory address, which CPython reuses the moment the previous dict is
  collected. Two questions in one turn could share an id, and answering one
  would have answered the other. Now a real `perm_` uuid7.
- **The UI kept only the newest question per turn.** A second grant overwrote
  the first in the reducer. A turn now holds a list, and every question it
  asked is shown in the order it asked them.

**10. Incognito returned 500 on its first turn.**

`POST /conversations {"incognito": true}` succeeded and handed back an id;
posting a turn to it died on `FOREIGN KEY constraint failed` and returned an
unhandled 500. Correct in isolation on both sides — an incognito conversation
writes no rows (§11.2.1), and a turn needs a conversation row — but nothing
joins them: there is no ephemeral turn path, and the HTTP layer never passed
the flag. The endpoint now refuses with **501 and the reason**, so the failure
lands where the ask is instead of two calls later. Incognito remains
unimplemented; see gap 7.

**11. Incognito, built.** §11.2 is implemented rather than refused: an
in-memory runtime (`chat/ephemeral.py`) holding conversations, turns and jobs,
because a job row's payload *is* the user's message and the table was never an
option. The event bus decides by asking whether the conversation id is
incognito, so a call site that forgets the flag cannot write the conversation
to disk — the same mistake that produced defect 10 in the first place.

Measured on the live app, not asserted: row counts across eleven tables, taken
before and after four incognito turns including a failure, a retry, a
multi-turn recall and a refused tool call. Every count identical. The same
counts move as expected for an ordinary turn immediately afterwards, which is
the part that proves the measurement means anything.

Two things fell out of building it:

- **Retry was still reading turns out of the table.** `POST /turns/{id}/retry`
  re-read the new turn to find out what to run. For an incognito turn there is
  no row, so it raised — leaving a turn queued that no worker would ever pick
  up. It now uses what `create_turn` already returned.
- **A restarted backend left the screen showing a transcript that no longer
  existed anywhere.** Every other conversation recovers by replay; an incognito
  one has nothing to replay. The client now re-reads on reconnect and says the
  chat has ended, which is what §11.2.3 asks for.

**12. Two model calls in one turn ran their prose together.** Found while
verifying the above: a turn whose first call ended `12 * 12 = 144` and whose
second began `12 * 12 = 144` was stored as `14412 * 12 = 144`. The turn loop
joined each call's visible text with nothing between. A separator is now
inserted when the previous call did not end in whitespace, and emitted as a
token so the live stream and the stored message agree.

**13. The tool grammar did not survive contact with a 7B.** (Serious — it is
the design bet the universal tool protocol rests on.)

Installed qwen2.5:7b locally and pointed the runtime at it. Twenty independent
turns, each asking for `137 * 449` — a value the model cannot reach without
actually running code, so a correct answer proves the whole path.

| | tool call parsed | answered correctly |
|---|---|---|
| canonical grammar only | **0/5** | 0/5 |
| + parser accepts the shapes models emit | 5/5 | 3/5 |
| + all three fixes, 20 turns | **19/20** | **19/20** |

Every one of the five original failures **named the right tool and carried
valid JSON**. The model was calling the tool correctly and being refused over
its punctuation — it wrote `run_python({...})` and
`<run_python>{...}</run_python>` instead of `<tool name="run_python">{...}</tool>`.

Three separate defects, each found by the run before it:

- **The parser accepted one shape.** It now accepts the two the model actually
  produces, both anchored to a *registered* tool name so prose cannot match.
  The stream filter suppresses them too, or the user watches the call type
  itself out before the runtime quietly runs it.
- **A silent execution looked like a success.** REPL-style code
  (`result = 137 * 449; result`) prints nothing. Reported as "completed
  successfully" with `(no output)`, the model filled the silence with an
  invented number — 61,013 and 60,913 for a value that is 61,513. The result
  now says the run printed nothing, that this is a script and not a REPL, and
  not to state a figure it has not seen.
- **An unfinished tool block produced a blank reply.** 2 of 8 turns finished
  with an empty assistant message: the model opened a block and never closed
  it, the filter correctly withheld the markup, and there was no prose behind
  it. A turn that completes having said nothing is now a `failed` turn with a
  reason and a Retry (§10.1), not a silent success.

The prompt also carries a worked example naming the three wrong shapes
explicitly, which is what moved the middle column from 5/8 to 19/20.

Two honest caveats. The samples are small — the 8-turn run in the middle scored
*worse* than the 5-turn run before it, which is noise, not regression, and the
20-turn figure is the only one worth quoting. And 1 in 20 still loops until
`MAX_TOOL_STEPS` stops it, burning about 90 seconds to produce nothing but the
stop message; the guard works, the turn is still wasted.

**14. JSON could not carry the code it existed to carry.** (Serious — and it
hid behind a passing measurement.)

Defect 13 measured the tool protocol at 19/20 using `137 * 449`. Asking for
documents instead — a PDF, a deck, a Word file, a spreadsheet, a chart, a CSV —
scored **0/6**. Three tasks in a row burned all eight tool steps, ~90 seconds
each, with **zero executions**.

The model was not the problem. It emitted a flawless canonical block:

```
<tool name="run_python">
{"code": "title = f'Deep Sea - {datetime.now().strftime("%Y-%m-%d")}'…"}
</tool>
```

`"%Y-%m-%d"` closes the JSON string 272 characters in. **Every payload
containing a double quote was rejected**, and `print(137 * 449)` contains none
— so the earlier measurement had accidentally chosen the one shape of input
that cannot trigger the bug. A green number over the wrong sample.

Three fixes:

- **Code no longer travels as JSON.** `run_python` and `run_shell` take exactly
  one string argument, so the envelope carries nothing the block does not
  already have. Both now accept a fenced or bare body — nothing to escape,
  nothing to get wrong — and the prompt teaches that form first. Multi-argument
  tools still require JSON, and a raw body sent to one is still refused.
- **Broken JSON is salvaged** for single-argument tools, recovering the value
  and decoding its escapes, rather than discarding a call that is obviously
  correct.
- **The correction loop stops after one attempt**, as its comment always
  claimed. It `continue`d unconditionally, so a model repeating the same
  escaping mistake consumed every step and produced nothing but the stop
  message — which is why this read as "the model loops" for three runs before
  anyone looked at what it was actually emitting.

Re-measured on the same six tasks, with every file opened and parsed rather
than merely counted: **5 of 6 valid**. A 1-page PDF with 278 characters of
extractable text, a 4-slide deck, a 9-row spreadsheet, a 640×480 chart, an
11-line CSV with correct atomic numbers. The sixth — a Word file — is
structurally valid but nearly empty; a direct re-run of the same prompt
produced a correct heading and three paragraphs, so that one is variance, not a
systematic failure.

**15. What an execution ran was not recorded.** Sessions kept stdout, stderr
and the file diff — everything about the result, nothing about the cause. When
the Word file came back nearly empty there was no way to tell whether the model
had written thin code or the parser had mangled good code on its way in. The
source is now stored on the session (migration v4, plain `ADD COLUMN`; verified
against the live 56-row database with no foreign-key violations).

**16. A failed tool left the model narrating instead of retrying.** Asked for
a JSON dataset, the run failed on `timedelta(months=...)`. The model replied
"let's correct this and try again" and put the corrected script in a markdown
fence in its ordinary prose. Prose is never executed — deliberately, since a
model showing the user a snippet must not have it run — so the turn finished
having produced nothing. A failing tool result now states how to actually
retry, and that a code fence in a reply is shown rather than run.

---

## 3b. What the dataset battery says about testing

Four datasets, each validated by **recomputing what it claims** rather than by
checking that a file appeared. The results are worth keeping mostly for what
they say about measurement.

| dataset | verdict | |
|---|---|---|
| 500-row CSV | consistent | model's stated mean pH matched the column exactly |
| 3-table SQLite | correct | 12/30/60 rows, clean foreign keys, 60 rows across a 3-way join |
| 2-sheet XLSX | **wrong** | Summary disagrees with its own Data sheet in 2 of 4 regions |
| nested JSON | no file | defect 16 |

Three things this measured that a file-exists check cannot:

1. **A valid file can be false.** The spreadsheet is a well-formed 240-row
   workbook whose per-region totals are right for North and East and wrong by
   exactly 15 for South and West. Nobody reviewing it would notice; it only
   fails because the check re-sums the rows.

2. **Consistent is not the same as meaningful.** The CSV passed — the model
   computed its stated mean from the data instead of inventing one, which is
   the failure mode defect 14 was about. The data is still nonsense: 326 of
   500 pH values fall outside the physically possible 0–14 scale. The check
   asked whether the claim matched the data, not whether the data made sense,
   and reported OK on a garbage dataset. Worth remembering before quoting it.

3. **The harness itself was wrong twice.** It graded the *first* artifact of a
   turn, and a turn that retries writes the same filename twice — so the
   SQLite dataset was scored as an empty database when the second, correct copy
   was sitting right beside it. Earlier, defect 14 was invisible because the
   emulation measurement used `print(137 * 449)`, the one payload shape with no
   quote characters in it. Both times the system was fine and the measurement
   was not, which is the failure mode an audit is least able to see in itself.

A minor product wrinkle also surfaced: a turn that re-runs writes two assets
with the same filename, and the transcript shows them as two identical chips
with nothing to say which is current.

**17. The built-in viewer was invisible, and every check I ran said it worked.**

The asset viewer mounted with its `initial` styles — `opacity: 0`,
`translateY(8px)` — and no animation ever started. `getAnimations()` returned
zero. The dialog was in the DOM at full size with correct content, so reading
its text, counting its rows and switching its sheet tabs all passed. A person
looking at the screen would have seen nothing at all.

The cause is a custom component as the direct child of `AnimatePresence` under
StrictMode's double-mount; the rail, which animates correctly, is a bare
`motion.div`. The fix was to stop depending on it: the modal is now plain divs,
because a viewer that silently fails to appear is a far worse defect than one
without a fade.

The lesson is bigger than the bug. **Every verification in this session has
been DOM-based, and the DOM is opacity-blind.** Screenshots were unavailable
for the whole session — the browser pane was never displayed — so "I checked
it" has meant "a script found the right text in the tree". That is sufficient
for logic and useless for visibility. Checks that involve appearance now assert
computed opacity, a non-zero bounding box, and that `elementFromPoint` at the
element's own coordinates lands inside it.

Three defects in one session came from measurement rather than code: sampling
only quote-free payloads (14), grading a stale artifact (§3b), and this. The
audit's own instrument is the least audited thing in it.

**18. Everything taught to the model was billed to every question.**

Each capability added today went into the system prompt, which is the one
string every turn carries. Measured: **623 tokens this morning, 1,023 by the
afternoon** — a 64% rise in fixed per-turn cost, of which ~209 tokens was
document-theming instruction paid for on "what is a race condition?".

Capabilities now live in `skills/<name>/SKILL.md`. The prompt carries one line
each — name and when to use it — and the body is inlined by the runtime only
when the request matches the skill's triggers. Selection is a keyword match in
the scheduler rather than a model decision, because asking the model to fetch a
skill costs a round trip, and on the local 7B a round trip is ~8 seconds with a
1-in-20 chance of the tool loop running away. `read_skill` exists as a tool for
a model that wants one anyway.

Two defects fell out of testing it, both of which had been hidden by the
instructions sitting next to the tool list:

- **The skill never said which tool runs the code.** Given a deck request, the
  model wrote correct `primnox_docs` code, filed it with `create_workspace`,
  and announced "the deck has been created successfully". Nothing had executed
  and no file existed. The skill now says to run it with `run_python`, and
  `create_workspace` replies that nothing was executed — plus, for a `.pptx` or
  `.pdf` path, that a workspace stores text so the file is not a real document.
- **`theme='light'` silently produced a dark deck.** The themes are *described*
  in two groups, light and dark, so that is what the model passed; the lookup
  missed and fell back to midnight without a word. The categories now resolve to
  a theme of that kind, and a genuinely unknown name prints what it used
  instead. The API invited the mistake, so the API absorbed it.

**19. The chat menu was clipped, and I reported it working.** (The same
mistake as 17, one feature later.)

The conversation list is `overflow-y-auto`, and the row menu was an absolutely
positioned child of it — so a scroll container clipped it. Measured on a row
near the bottom of the list: the menu overflowed by **124px**, and everything
past "Archive", including "Delete permanently", was cut off. On a sidebar of
seventy conversations that is most of them.

I had already declared this feature verified. Every check drove it with
`element.click()`, which ignores clipping, occlusion and visibility entirely —
so a menu nobody could see passed every one. The user found it in about a
minute.

The menu now renders through a portal into `<body>` with fixed coordinates,
measures its own height, and flips above the button when there is no room
below. Verified differently, and this is the part that matters: each item is
located by `elementFromPoint` at its own centre and the click is dispatched to
**whatever is actually on top**, so anything invisible or covered fails the
test rather than passing it.

Defect 17 ended with "checks that involve appearance now assert computed
opacity, a non-zero bounding box, and that `elementFromPoint` lands inside the
element". I wrote that, then built the next feature and did not do it. Writing
the lesson down is not the same as applying it, and an audit that records a
practice nobody follows is worth less than no audit.

---

**Where these came from.** Eighteen of the nineteen were found by using the product —
turning the prompt on, reloading mid-question, reading what the screen claimed
against what the log held. Only one came from reading code. Six sat in the UI layer, which
still has no automated tests; the backend regressions added here pin the
runtime behaviour beneath them, not the rendering.

---

## 4. Gaps — things this audit does not let you claim

1. **No CI.** The spec assigns each level a cadence — L0/L1/L2 every commit,
   L3 on PR, L4 nightly. Nothing enforces that; the suite runs when someone
   runs it. This is the single biggest gap, and the cheapest to close.

2. **"Read Documents → Prompt" does not prompt.** The manifest declares
   `documents: ask`, and the test asserts that. But `PRIMNOX2_AUTO_APPROVE`
   defaults to `all` (by explicit instruction), so at run time the answer is
   granted without asking. The manifest is honest; the runtime default
   overrides it. Set `PRIMNOX2_AUTO_APPROVE=off` to get the specified
   behaviour.

3. **Registry is only partly denied.** Measured against the live sandbox: all
   registry *writes* fail, including `HKLM` and the `Run` persistence key, and
   protected-key reads fail — but reads of general machine configuration
   (`HKLM\SOFTWARE\…`, `HKCU\Environment`) succeed and cannot be blocked by
   AppContainer. `registry: deny` means "no writes, no protected reads". A
   disclosure boundary, not an integrity one.

4. **System32 denial is asserted at the manifest level only.** The manifest
   refuses to grant it and that is tested; there is no live probe proving a
   sandboxed process cannot read System32 the way there is for Documents,
   source files and network.

5. **Database transactions are not auto-traced.** The Replay Recorder captures
   states, events, sandbox actions and provider calls automatically; DB writes
   require an explicit `recorder.note()` call, so a trace shows fewer
   transactions than actually occurred.

6. **Weak-model tool emulation: measured twice, because the first measurement
   was over the wrong sample.** qwen2.5:7b (Q4_K_M, Ollama) scores **19/20** on
   arithmetic (defect 13) and **5/6** on real document generation (defect 14) —
   but the arithmetic figure alone read as healthy while every document task
   was failing, because `print(137 * 449)` contains no quote characters. What
   remains unmeasured is breadth: one model, two task shapes. A different 7B
   may fail in shapes this parser does not accept, and the lesson worth keeping
   is that a passing number says nothing about the inputs it never saw.

7. **Incognito is built, minus the tools.** §11.2.1 through §11.2.3 are
   implemented and measured — a complete turn moves the row count of every
   table by zero. §11.2.4 is not: assets, workspaces and executions are
   *refused* in an incognito chat rather than made ephemeral or promotable.
   Refusing satisfies the clause (nothing is silently persisted) but it is a
   narrower feature than the section describes, and running code there would
   need the sandbox threaded with the same distinction.

8. **"Allow for this turn" is proven in tests, not on screen.** The broker
   grants a reusable action once and never asks again — covered by
   `test_an_allowance_for_the_turn_is_not_asked_twice`. The button that says
   so was not clicked in a live two-tool turn: the provider
   (`capi.aerolink.lat`) was returning 503 to every request for the duration
   of that check, confirmed by direct probe. Allow-once and deny were both
   exercised live.

9. **A reload strips a finished turn of everything but its text.** History
   returns turns, messages, status and (now) a pending question. Plans, tool
   rows, executions and settled permission lines are event-derived and vanish
   on refresh — the transcript survives, the account of how it was produced
   does not. Consistent with §3.3.3 as written, and probably not what a reader
   of that section expects.

---

## 5. Token economics

Measured live against the configured provider, not estimated.

**Fixed overhead, sent on every turn:**

| Component | Tokens |
|---|---|
| Primnox system prompt | 32 |
| Tool grammar and rules | 211 |
| Tool descriptions (7 tools) | 269 |
| Sandbox library list | 111 |
| **Total** | **~623** |

**What that actually costs, measured:**

| Turn | Prompt total | Fresh | Cache write | Cache read | Output |
|---|---|---|---|---|---|
| 1 — plain question, cold | 624 | 2 | 622 | 0 | 2 |
| 2 — plain question, warm | 643 | 2 | 19 | 622 | 2 |
| 3 — tool call (2 model calls) | 1459 | 4 | 152 | 1303 | 121 |

**The overhead is cached.** After the first turn, the ~620-token preamble
arrives as a cache *read*, which Anthropic bills at roughly a tenth of normal
input. So the steady-state cost of Primnox's tool machinery is closer to
**~62 effective input tokens per turn**, not 623.

**Against a bare chat client:**

- A plain "what is 2+2" costs a normal user ~10 tokens of input.
- The same question through Primnox costs ~643, of which 622 is a cache read
  → roughly **72 effective tokens**, about 7× a bare request.
- By turn 10 of a real conversation, history dominates and the fixed overhead
  is under 15% of the prompt.
- **Tool turns are the real cost:** each step re-sends the whole conversation.
  A one-tool turn is 2 model calls; the observed `/tmp` retry made it 3. Fixing
  that retry (done — the prompt now states the sandbox is Windows and files go
  in the working directory) removes an entire round trip.

The honest summary: the overhead is real but largely cached, and it buys tool
calling on any model. The thing worth watching is tool *step count*, not prompt
size.
