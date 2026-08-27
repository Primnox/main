# Unit 4 — Response primitives

**The deliverable is a rule, not a component set.** If this document had ended
with a list of twenty-five blocks to build, it would have failed: the next
primitive would arrive and the list would be silent about it. What follows is a
function a frontend engineer can apply to a payload nobody has thought of yet.

Implementation: `frontend/src/components/proto/response-primitives/rule.ts`.
Running demonstration: the gallery's **04 · Response primitives** entry.

Every claim below is labelled **[observed industry pattern]**,
**[research-backed UX principle]**, **[inference]**, or **[proposed design]**.
Every recommendation names a real Primnox file and says CHANGE / KEEP /
PROTOTYPE.

---

## 1. The rule

A response primitive renders at one of four levels. Primnox already has all
four; none of them is new.

| Level | Surface today |
|---|---|
| `inline` | the prose measure — `frontend/src/lib/md.tsx` |
| `block` | a bounded compartment in the turn — `ThinkingBlock`, `PlanBlock`, `ExecutionBlock`, `Attachment`, `FlowchartBlock`, `Canvas variant="inline"` |
| `panel` | beside the conversation, outliving the turn — `Canvas variant="panel"` |
| `fullscreen` | the viewport — `AssetViewer`, `FlowchartBlock`'s portal |

### 1.1 Five inputs, each imposing a floor

The level is the **highest floor raised**. No weighting, no scoring, no
tie-break by taste. Each input is answerable from a CRS event payload without
reading the content, which is what makes the rule mechanical: two engineers
filling in a descriptor for the same event produce the same descriptor.

| Input | Test | Floor |
|---|---|---|
| **extent** | ≤ 3 lines *and* no columns | `inline` |
| | anything more | `block`, with a scroller past 12 lines |
| **interact** | reading it requires a gesture — pan, zoom, sort, step, scrub, play | `block` |
| **evidence** | it substantiates a claim rather than making one | `block`, opening **collapsed** |
| **blocking** | the turn is parked until the user answers | `block`, **pinned open**, not collapsible |
| **handle** \|\| **persists** | the user will act on it outside this turn; or it has an id that outlives the turn | `block`, **plus a door** |

### 1.2 The clamp

**The rule never returns `panel` or `fullscreen`.** Its only say in those levels
is whether to draw the door. Promotion is a user act.

This is the rule's teeth, and it is the part most likely to be quietly deleted
by someone who wants a chart to auto-open a canvas. The justification is in §3.

### 1.3 The door test

A door is offered on `handle || persists` — **never on size**.

### 1.4 Two hard constraints, checked rather than recommended

`decide()` returns a `violations` array. These are defects, not preferences.

1. **A visual payload without a text alternative is refused.** WCAG 2.1 §1.1.1.
   W3C's complex-image guidance is specific that a chart's long description is
   *the data behind it*, not a description of the picture
   ([W3C WAI](https://www.w3.org/WAI/tutorials/images/complex/)).
   **[research-backed UX principle]**
2. **A rich rendering must replace the prose it encodes, never sit beside it.**
   Two channels carrying identical information cost working memory and return
   nothing — Sweller's *redundancy effect*
   ([Kalyuga, Chandler & Sweller](https://pubmed.ncbi.nlm.nih.gov/9514686/);
   [split-attention overview](https://en.wikipedia.org/wiki/Split_attention_effect)).
   The distinction that matters: split attention is *necessary* information
   separated (fix by integrating); redundancy is *duplicated* information (fix
   by deleting one). A chart under a sentence that already stated the finding
   is redundancy. **[research-backed UX principle]**

### 1.5 Totality

An unrecognised primitive still has an extent, and a descriptor with all five
booleans false. It therefore lands at `inline` or `block` and falls through to
bounded, scrollable, inert text. It never crashes and never renders blank.
`describeUnknown()` in `rule.ts` is four lines and is the proof. The demo's
section 04 mounts a `plan.projection.v3` that no renderer knows.

---

## 2. Why not size — the deliberate divergence

Two shipping products converged on nearly the same gate for the equivalent of
Primnox's door: **[observed industry pattern]**

- **Claude Artifacts.** Anthropic's support documentation states an artifact is
  created when content is "significant and self-contained, typically over 15
  lines"; the Claude 101 course adds the rest of the list — likely to be
  edited, iterated on or reused; understandable without the surrounding
  conversation; intended for use outside the conversation; likely to be
  referenced again
  ([support](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them),
  [Claude Academy](https://academy.claude.com/courses/claude-101/creating-with-artifacts)).
- **ChatGPT Canvas.** OpenAI's help centre: canvas opens automatically for
  content "greater than 10 lines, or when it detects a scenario where it would
  be helpful"
  ([help centre](https://help.openai.com/en/articles/9930697)). OpenAI's launch
  post notes the trigger is trained behaviour with a stated ~83% correct
  trigger rate for writing tasks, not a deterministic switch
  ([introducing canvas](https://openai.com/index/introducing-canvas/)).

Read the criteria and notice what the line-count is doing. It is a **proxy for
reuse-intent**. Both products want to know "will the user take this away and
work on it", cannot observe that, and so guess from length — and one of them
publishes its own 17% error rate.

**Primnox does not have to guess.** `crs.ts` receives `workspace.created`,
`workspace.updated` and `asset.ready` as event kinds *distinct from* `token`.
By the time a payload reaches the renderer, the runtime has already declared
whether it produced a durable, editable, downloadable thing. `handle` and
`persists` are reads, not inferences. **[inference — the mechanism is
observable in `crs.ts`; that it yields better placement than a line count is my
argument, not a measured result]**

The practical consequence, visible in the prototype's bench: a 34-line code
payload that arrived with `workspace.created` gets a door; a 34-line
`tool_result` does not, because there is nothing to take away. Under the
line-count heuristic both would open a canvas, and one of them would be a
canvas full of log output.

CHANGE — this is the recommendation §7 records against `crs.ts` and
`TurnBlock.tsx`.

---

## 3. The visual-first question, with evidence

**The claim under test:** should the UI adapt to the *semantic type* of the
answer — data→chart, comparison→table, architecture→diagram, location→map,
timeline→timeline, plan→checklist?

**Verdict, in three parts:**

- **Semantic type must not select the LEVEL.** Rejected on the evidence below.
- **Semantic type may select the RENDERER inside a level.** Supported, with the
  §1.4 redundancy constraint attached.
- **Auto-selecting the renderer is a smaller win than it is sold as, and it is
  task-dependent rather than type-dependent.** Evidence below.

### 3.1 The comprehension evidence does not say "charts win"

The best-controlled work says the opposite of the marketing claim: format
effectiveness depends on the **task**, not on the data's type.
**[research-backed UX principle]**

- Schonlau & Peters ran two web-based experiments and found comprehension
  depended on task — **graphs were better for estimating differences, tables
  were better for estimating equality and sums**
  ([De Gruyter](https://www.degruyterbrill.com/document/doi/10.1515/2151-7509.1054/html)).
- Their American Life Panel experiment (n=897) found that **displaying data in
  a table led to more accurate answers than bar charts or pie charts**
  ([RAND WR-618](https://www.rand.org/pubs/working_papers/WR618.html)).
- A 1984 controlled comparison found tabular treatments significantly increased
  comprehension, and that graph+table combinations produced *slower but more
  accurate* performance
  ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0020737384800292)).

This is fatal to the naive form of visual-first. "The answer contains numbers"
does not tell you whether the reader is estimating a difference (chart) or
looking up a value (table). The *semantic type of the data* is the wrong
signal; the *task the reader is performing* is the right one — and an assistant
does not reliably know the task from the prompt.

**Consequence for the rule:** a table is the correct default for tabular data,
and a chart is an opt-in the model must justify. Primnox already does this by
accident — `md.tsx` renders GFM tables and has no chart path at all. That
accident is a better default than most deliberate designs. KEEP.

### 3.2 The generative-UI evidence is thin and preference-shaped

- The strongest research claim is *Generative Interfaces for Language Models*
  ([arXiv 2508.19227](https://arxiv.org/abs/2508.19227)), whose abstract reports
  generated interfaces outperforming conversational ones with "up to a 72%
  improvement in **human preference**." I could not reliably extract the
  per-task breakdown or the participant count from the PDF, so I am not
  reporting either. Note what the metric is: **preference, not comprehension or
  accuracy** — the opposite axis from §3.1, and the one where novelty effects
  live. **[observed industry pattern / weak evidence]**
- Google's own research post on generative UI states only that its interfaces
  are "strongly preferred by human raters compared to standard LLM outputs" —
  **explicitly when ignoring generation speed**, which it concedes "can
  sometimes take a minute or more"
  ([research.google](https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/)).
  **No percentages, sample sizes or significance levels appear in that post.**
  Secondary sites circulate "47% preferred" and "30% fewer steps" figures for
  Gemini Dynamic View; I checked the primary source and **those numbers are not
  in it**. Do not cite them, here or anywhere else in this repo.
- The hands-on reception is the useful part. Android Authority's verdict is
  "great, just don't use it for every prompt", with the concrete failure being
  a simple factual query — "what time is it in New York City right now" —
  taking up to 90 seconds to return an elaborate panel nobody asked for
  ([Android Authority](https://www.androidauthority.com/gemini-dynamic-view-3619662/)).
  **[observed industry pattern]**

### 3.3 The consistency objection is unanswered

NN/g's own framing of generative UI is an interface "generated in real time for
a specific end user" ([NN/g](https://www.nngroup.com/videos/genui-ai-generated-interfaces/)).
The central published objection is that this destroys the mental model: there
is no guaranteed way back to a familiar interface, and users generally value a
fast consistent experience over a perfectly personalised one
([Marschall-Miller](https://www.linkedin.com/pulse/response-generative-ui-outcome-oriented-design-marschall-miller-gnerc)).
The accessibility case for it has been argued to rest on a straw man
([axbom](https://axbom.com/nielsen-generative-ui-failure/)). **[observed
industry pattern]**

This objection lands hard on Primnox's target statement — *familiar at first
contact, revealing a deeper operating model as the work gets complex*. An
interface that rearranges itself around the shape of each answer is not
familiar at first contact and never becomes familiar at all. What produces
familiarity is a transcript that always looks the same, with doors that appear
on the things worth opening. That is precisely the clamp in §1.2.
**[inference]**

### 3.4 The accessibility cost is real and is charged per chart

Every visual encoding incurs WCAG 2.1 §1.1.1, and for complex images the
required alternative is a two-part one: a short identification plus a long
description that is, in practice, the data table
([W3C](https://www.w3.org/WAI/tutorials/images/complex/)). "Adapt the UI to the
semantic type" means "manufacture a WCAG obligation on every response", and
PRODUCT.md treats an AA regression as a defect rather than a polish item.

The mitigation is in the prototype and is worth stating as a rule of its own:
**build charts out of DOM text, not canvas or SVG-only geometry.** The bar
renderer in `PrimitiveRenderer.tsx` prints each label and value as real text
with the bar as an `aria-hidden` decoration over it. The accessible name comes
for free because the data never left the accessibility tree. **[proposed
design]**

### 3.5 So what survives

**[proposed design]** Semantic type is a **renderer hint carried on the
descriptor, consumed only after the level is fixed.** Concretely:

1. The model may *request* a renderer (`kind`). It may not request a level.
2. A requested rich renderer must supply its own text alternative or it is
   refused (§1.4.1).
3. A requested rich renderer must replace the prose it encodes (§1.4.2).
4. Tables are the default for tabular data. Charts are opt-in.
5. Latency is a level input in disguise: a renderer that cannot paint in the
   same frame as the text belongs behind a disclosure, not in front of it.
   The Gemini 90-second case in §3.2 is this rule being broken. **[inference]**

The single most over-claimed idea in AI UI design turns out to be about 20%
true, and the 20% is "let the model pick the renderer", not "let the model pick
the layout".

---

## 4. Gap audit — what `crs.ts`'s `Turn` cannot currently express

`frontend/src/lib/crs.ts` lines 104–139 define `Turn`. It is the honest answer
to "what can a Primnox response contain today", and the answer is narrower than
the brief's primitive list. Missing, in rough order of how much they cost:

### 4.1 Citations / evidence spans — **absent entirely**

`assistantText` is a flat string. There is no `Turn.citations`, and no way to
bind a claim span to a source. This is the most expensive gap because
`evidence` is one of five level inputs, so today the rule cannot even *observe*
its second-most-common trigger. Unit 3 records that `world_model.py` already
captures provenance the UI never shows
(`docs/ui-research/03-research-build-agents.md`) — so the data exists and the
transport does not. PROTOTYPE.

### 4.2 Structured tool results — **discarded in the reducer**

`ToolCall` (line 21) is `{ name, status, arguments?, summary? }` and the
`tool.result` case (line 273) keeps only `e.payload.summary`, a string. A tool
that returns 40 rows returns a sentence about 40 rows. No tool can ever render
as a table, chart, or anything else, regardless of what it computed. Needs
`result?: unknown` and `resultKind?: string`. CHANGE.

### 4.3 Charts — **no primitive at any layer**

`SheetTable.tsx` renders a sheet from an *asset preview*, not from a turn
payload. `md.tsx` has a mermaid branch (`FlowchartBlock`) and nothing numeric.
A model that wants to show a series must generate an image asset, which
immediately fails §3.4. PROTOTYPE — and per §3.1, as an opt-in behind a table
default.

### 4.4 Determinate progress — **absent**

`Execution` has `status` and `output: string[]`; `TurnStatus` is a word. There
is no "214 of 340". Unit 10's long-running-agent work needs this and cannot
synthesise it, because §8.4.3 forbids the client inventing state the runtime
did not send. CHANGE (backend event first).

### 4.5 Interactive controls and forms — **single-choice only**

`UserQuestion` (line 56) is `{ question, options[], answered }`. There is no
free-text answer, no multi-select, no numeric field, no multi-field form. A
model needing three answers must park the turn three times. CHANGE.

### 4.6 Warnings — **no non-fatal channel**

`TurnError` is set only by `turn.failed` (line 239) and is terminal. A turn that
half-worked — two of eight documents skipped for want of an OCR engine — has
nowhere to say so, so it either fails wholesale or says nothing. Given
PRODUCT.md principle 3 ("Say what actually happened"), this is a product gap,
not a UI gap. CHANGE.

### 4.7 A concrete bug this gap already causes

`TurnBlock.tsx` lines 159–162 pass `context={{ attempt: 1, maxAttempts: 3 }}` to
`RecoveryBlock` as literals. The retry count is **fabricated in the view**
because `Turn` has no field to carry it, so a user on their third retry is told
they are on their first. Either `Turn` gains `attempt`/`maxAttempts` from the
runtime, or `RecoveryBlock` stops displaying a number it does not have. CHANGE.

### 4.8 `kind` is a bare `string` in two places

`assets: { id; name; kind: string }[]` and `workspaces[].kind: string`. The
renderer switches on a stringly value with no exhaustiveness check, so a new
backend kind fails silently. Unit 6 proposes a shared `ArtifactKind` enum
(`docs/ui-research/06-artifact-model.md`); I agree and it costs nothing.
CHANGE.

### 4.9 Name collision: two different `Artifact` types

`crs.ts` line 33 exports `Artifact = { asset_id, name, path, bytes }`, meaning
*one file a sandbox execution produced*. `docs/ui-research/06-artifact-model.md`
uses `Artifact` to mean the unified workspace-or-asset metadata shape. Two
different concepts, one exported name, same codebase. Rename the `crs.ts` one
to `ExecutionArtifact` before Unit 6's model lands, or the merge will be
confusing in a way no comment can fix. CHANGE.

### 4.10 Not gaps — timelines, maps, previews, images, links, checklists

These need no new `Turn` field. Under §3.5 they are renderer hints on payloads
that already have transport: markdown lists, `assets`, or (once 4.2 lands)
structured tool results. Adding `Turn.timeline` would be adding a nav
destination's worth of type for a `<ol>`. KEEP the absence.

---

## 5. Where this contradicts the other units

The brief requires me to say so and argue it.

### 5.1 Against `05-artifact-cards.md` — frequency thresholds are unimplementable here

Unit 5 sets action visibility by session frequency: "Core | 80%+ of sessions |
Always shown", "Advanced | 10–40% of sessions | Hidden". `docs/PROGRESSIVE_DISCLOSURE_FRAMEWORK.md`
does the same, with figures like "Edit/delete message — ~70% of power users"
and "Retry button — ~55%".

**Primnox has no telemetry.** PRODUCT.md, "Evidence on Hand": *"No customer
testimonials, usage numbers, benchmarks, press, or pricing exist. Future work
must not fabricate any of these."* Those percentages are not measurements; they
are placeholders that read as measurements. An engineer asked to implement
"show if used in >40% of sessions" has no query to run, and will substitute
their own taste while believing they are following a rule.

Unit 5's own supporting statistics have the same problem: "scanning speed
increases ~40% vs. collapsed rows (research: Nielsen, card UI effectiveness
studies)" and "user recognition of content type improves by ~60%" carry no URL
and I could not locate either. I am not asserting they are wrong; I am
asserting they are uncitable and therefore unusable as a basis for a
structural decision.

**My rule uses only observable properties of the payload.** `extent` is
measured. `blocking`, `evidence`, `handle`, `persists` and `interact` are reads
off an event. Nothing in `rule.ts` requires a number nobody collected. This is
the substantive disagreement, and it is why the rule's inputs look the way they
do.

Where Unit 5 is right and I adopt it wholesale: "Anti-Pattern A: Single-Item
Containers" — a card around one line of text is overhead. That is exactly the
`extent → inline` floor, and Unit 5 got there first.

### 5.2 With `06-artifact-model.md` — agreement, with one clarification

Unit 6 concludes a unified `Artifact` model works at the metadata layer and
fails at the lifecycle layer, because Canvas owns its open state while
AssetViewer is parent-controlled. I agree and my rule does not disturb it: the
rule decides the *level*, and says nothing about which component implements
`panel` or `fullscreen`. Two components can share one level decision without
sharing a state machine. Unit 6's `capabilities.editable` / `downloadable`
fields are, in fact, the `handle` input under another name.

### 5.3 With `08` / `PROGRESSIVE_DISCLOSURE_FRAMEWORK.md` — same shape, different axis

The five-level expertise cascade and my five-input floor rule are compatible
because they answer different questions: theirs is *which users see this*,
mine is *where this payload goes*. They compose — an `evidence` block opens
collapsed for everyone, and the framework can decide whether the trigger is
even rendered for a novice.

Both rest on the same principle, which is genuinely citable: progressive
disclosure defers advanced or rarely-used features to a secondary screen,
focusing attention on the primary options
([NN/g](https://www.nngroup.com/videos/progressive-disclosure/)).
**[research-backed UX principle]** My §1.2 clamp is that principle applied to
surfaces rather than to features.

Where I diverge is §5.1's frequency numbers, which are that document's
implementation mechanism.

---

## 6. Where the rule contradicts Primnox as built

Applying §1 to the current transcript, honestly:

| Component | Rule says | Reality | Verdict |
|---|---|---|---|
| `ThinkingBlock.tsx` | `evidence` → block, collapsed | block, collapsed | **KEEP** — the rule was partly reverse-engineered from this file |
| `PlanBlock.tsx` | extent ≤ 3 → inline | a bordered block with an icon and a label | **CHANGE** — a two-line plan in a compartment is Unit 5's own anti-pattern A |
| `ToolRow.tsx` | `evidence` → block, collapsed | a one-line row, no disclosure, no payload | **KEEP the row, CHANGE the type** — the row is right; §4.2 is why it has nothing to disclose |
| `Attachment.tsx` | `persists` → block + door | block + door (`onExpand`) | **KEEP** — the reference implementation of the door test |
| `Canvas.tsx` inline | `handle` → block + door | block + door | **KEEP** |
| `PermissionBlock` / `QuestionBlock` | `blocking` → block, pinned | rendered per-request in `TurnBlock` | **KEEP**, verify they cannot be collapsed away |
| `FlowchartBlock.tsx` | `interact` → block; fullscreen on user act | block; portal on "View as graph" | **KEEP** — already obeys the clamp |
| `md.tsx` code fence | extent-dependent | always a bordered block, even for one line | **CHANGE** — a single-line command is `inline` |
| `md.tsx` tables | extent has columns → block | inline `<table>` in a scroller | **KEEP** — §3.1 says the table default is right |
| `TurnBlock.tsx` ordering | — | blocks render in a fixed order before the reply | **KEEP** — a fixed order is what §3.3 says produces familiarity |

`PlanBlock` and the `md.tsx` code fence are the two places the current UI puts a
compartment around something that should read as a line.

---

## 7. Recommendations

**KEEP**

- The fixed block order in `TurnBlock.tsx`. It is the familiarity mechanism.
- The absence of a chart path in `md.tsx` as the *default*; tables first (§3.1).
- `Attachment.tsx` and `Canvas.tsx`'s `onExpand` callback shape. The rule's
  door is that callback, and it already exists.
- `ThinkingBlock.tsx`'s collapsed-by-default reasoning. It is `evidence`,
  correctly handled, and it is where the input came from.
- Unit 6's split between Canvas and AssetViewer.

**CHANGE**

- `crs.ts` — `ToolCall.result`/`resultKind` (§4.2); `Turn.attempt` (§4.7);
  `ArtifactKind` for `assets[].kind` and `workspaces[].kind` (§4.8); rename
  `Artifact` → `ExecutionArtifact` (§4.9); a non-fatal warning channel (§4.6);
  richer `UserQuestion` (§4.5).
- `TurnBlock.tsx` — stop passing literal `attempt: 1, maxAttempts: 3` to
  `RecoveryBlock`.
- `PlanBlock.tsx` — inline a short plan; keep the block only past the extent
  floor.
- `md.tsx` — a single-line fenced command renders inline, not as a bordered
  block.
- Any future disclosure work — drop the session-frequency thresholds in
  `PROGRESSIVE_DISCLOSURE_FRAMEWORK.md` and `05-artifact-cards.md` for
  payload-observable inputs (§5.1).

**PROTOTYPE**

- `Turn.citations` with claim-span binding (§4.1) — the highest-value gap, and
  Unit 3 says the backend data already exists.
- A DOM-text chart renderer (§3.4/§4.3), opt-in, behind a table default.
- Determinate progress as a runtime event (§4.4).

None of these were performed. This unit touched only its own doc, its own proto
directory, and one entry in `proto-gallery.tsx`.

---

## 8. The prototype

`frontend/src/components/proto/response-primitives/`

- `rule.ts` — `decide()`, the whole deliverable. `kind` appears only in the
  type; grep it to confirm the level function never reads the semantic type.
- `PrimitiveRenderer.tsx` — one component, any primitive. It asks for a level,
  draws that level's chrome, and only then looks at `kind` to choose how the
  bytes are drawn.
- `fixtures.ts` — all twenty primitives from the brief, described rather than
  designed.
- `Demo.tsx` — four sections: the rule; the bench (every primitive levelled,
  with the input that caused it printed alongside); the live bench (flip an
  input, watch the level move; change the kind, watch it not); and an unknown
  primitive.

The live bench is the falsifiable part. If the rule were aesthetic rather than
mechanical, that panel could not exist.

Verified in the running app: typecheck and build clean; all twenty payload
branches mounted under `StrictMode` with an empty console (no
`validateDOMNesting`); zero nested interactive elements; zero elements with a
non-zero computed border-radius; no `text-on-surface` utility below the `/50`
floor.

---

## 9. Sources

Comprehension and cognitive load:
- Schonlau & Peters, *Comprehension of Graphs and Tables Depend on the Task* — https://www.degruyterbrill.com/document/doi/10.1515/2151-7509.1054/html
- Schonlau & Peters, RAND WR-618 (American Life Panel, n=897) — https://www.rand.org/pubs/working_papers/WR618.html
- *An experimental comparison of tabular and graphic data presentation* (1984) — https://www.sciencedirect.com/science/article/abs/pii/S0020737384800292
- Kalyuga, Chandler & Sweller, split-attention and redundancy — https://pubmed.ncbi.nlm.nih.gov/9514686/
- Split-attention effect overview — https://en.wikipedia.org/wiki/Split_attention_effect

Accessibility:
- W3C WAI, Complex Images — https://www.w3.org/WAI/tutorials/images/complex/
- W3C WAI, Images Tutorial — https://www.w3.org/WAI/tutorials/images/

Industry patterns:
- Claude Artifacts criteria — https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them
- Claude 101, Creating with artifacts — https://academy.claude.com/courses/claude-101/creating-with-artifacts
- ChatGPT Canvas FAQ — https://help.openai.com/en/articles/9930697
- OpenAI, Introducing canvas — https://openai.com/index/introducing-canvas/
- Google Research, Generative UI — https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/
- Android Authority, Gemini Dynamic View hands-on — https://www.androidauthority.com/gemini-dynamic-view-3619662/
- *Generative Interfaces for Language Models* — https://arxiv.org/abs/2508.19227

Disclosure and the generative-UI debate:
- NN/g, Progressive Disclosure — https://www.nngroup.com/videos/progressive-disclosure/
- NN/g, GenUI: AI-Generated Interfaces — https://www.nngroup.com/videos/genui-ai-generated-interfaces/
- Marschall-Miller, *A Response to "Generative UI and Outcome-Oriented Design"* — https://www.linkedin.com/pulse/response-generative-ui-outcome-oriented-design-marschall-miller-gnerc
- Axbom, *On Nielsen's ideas about generative UI* — https://axbom.com/nielsen-generative-ui-failure/

**Not cited on purpose:** the "47% preferred" and "30% fewer steps" figures
circulating for Gemini Dynamic View. I checked the primary source and they are
not in it.
