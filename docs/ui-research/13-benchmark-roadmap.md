# Unit 13: Benchmark & Roadmap

**Date:** 2026-08-26
**Role:** synthesis unit. The other twelve units produced findings; this one turns them into a decision.

**Target statement under test:** *Primnox should look familiar at first contact, and reveal a deeper
operating model as the user's work becomes more complex.*

**The model being benchmarked:**

```
Conversation → AI Response → { Text | Rich Block | Action } → Artifact
             → { Quick preview | Canvas } → Persistent object → Project
```

Agent activity is **orthogonal** — a layer around the work, never another nav destination.

---

## How to read this document

Every claim carries one of four labels:

- **[observed]** — an industry behaviour I verified against a vendor's own documentation, with a URL.
- **[principle]** — a research-backed UX principle with a citation.
- **[inference]** — my reasoning from evidence, which could be wrong.
- **[proposed]** — a design I am recommending, not a fact.

Every recommendation ends in **CHANGE**, **KEEP** or **PROTOTYPE**, and names a real Primnox file.

Where I could not verify a competitor's behaviour, the cell says **UNKNOWN**. There are **26** of
those, counted off the rendered table rather than off my memory of writing it. A matrix with no
UNKNOWN cells is a matrix somebody guessed at.

---

## Part 0 — Two corrections before anything is scheduled

The single most useful thing a synthesis unit can do is stop the program from paying twice. Two
findings from other units are **stale against the current code**, and both sit near the top of a
"critical gaps" list.

### 0.1 Copy already exists

`docs/ui-research/01-mainstream-assistants.md` lists "No copy-to-clipboard action" as a **High**
severity gap and recommends "Add [Copy] button to every message."

It is already there. `frontend/src/components/TurnBlock.tsx:138` renders `<CopyButton text=
{turn.assistantText} label="Copy reply" />`, and `frontend/src/lib/md.tsx:66` puts one on every code
block. `frontend/src/components/Canvas.tsx:194` has a third.

What is *actually* wrong is narrower and worth stating precisely, because the fix is different.
`TurnBlock.tsx:136–141` wraps it in `opacity-0 group-hover/reply:opacity-100 focus-within:opacity-100`.
Keyboard users are covered by `focus-within`. Pointer users are covered by hover. **Touch users are
covered by nothing** — there is no hover state on a touchscreen, so on a touch-capable display the
button is invisible and unreachable until something else focuses inside the reply.

**Verdict: CHANGE — `frontend/src/components/TurnBlock.tsx:136–141`.** Not "add copy". Make the
existing copy button unconditionally visible, or gate it on `@media (hover: hover)` rather than on
hover alone. This is a two-line change, not a feature.

### 0.2 Conversation search already exists

The same document lists "No search across conversations" as a **Medium** gap: "Primnox **lacks
search**, which all mainstream assistants provide."

`frontend/src/App.tsx:479–500` is a labelled `<input type="search" id="chat-search">` with an
`sr-only` label, a clear button, and a documented decision to flatten folders and day-groups into one
result list while a query is active. `App.tsx:305–312` holds the client-side filter. Unit 11 saw it
(`11-navigation-composer.md` §9.5: "Implemented (client-side, in-memory)"). Unit 1 did not.

**Verdict: KEEP — `frontend/src/App.tsx:479–500`.** Nothing to build. Remove it from the gap list.

**[inference]** Two of unit 1's six listed gaps do not exist. That is not a criticism of unit 1 so
much as the reason a synthesis unit has to re-read the code rather than sum the summaries. Everything
that follows was checked against files, not against other documents.

---

## PART A — CAPABILITY MATRIX

### A.0 What is being compared, and what cannot be

The comparison set is **ChatGPT, Claude, Gemini, Perplexity, Microsoft Copilot, Cursor and Manus** —
AI interfaces, not productivity suites.

Three of Primnox's constraints make some rows genuinely incomparable rather than won or lost:

1. **Desktop-only, Windows, Tauri.** `PRODUCT.md:54` — "Desktop app on Windows (current beta). A
   Tauri shell hosts the UI." Every product in the comparison set is a web app with mobile clients.
2. **Loopback-only backend.** `PRODUCT.md:79` — "The backend binds localhost and verifies Origin on
   every request." A mobile client is not an unbuilt feature; it is a different architecture.
3. **Multi-provider by design.** `PRODUCT.md:45` — "Runs fully local, any provider." Every mainstream
   competitor ships exactly one vendor's models. Primnox "wins" customisation for a structural
   reason, not a design reason, and the matrix should say so rather than take credit.

**[inference]** Rows where Primnox appears ahead because of these constraints are marked **N/A** or
annotated, not marked BETTER. A capability matrix in which the home product wins every row is a
marketing document.

### A.1 Verdict vocabulary

| Token | Meaning for the Primnox column |
|---|---|
| **BETTER** | The proposed design is genuinely ahead, and I can say why in one sentence. |
| **PARITY** | Equivalent outcome by a different route. |
| **BEHIND** | Mainstream is simply better. Say it plainly. |
| **CONVENTIONAL** | Primnox should deliberately not innovate here. Copying is the correct answer. |
| **N/A** | Not comparable — a constraint, not a gap. |
| **UNKNOWN** | Not verified. Do not act on this cell. |

### A.2 The matrix

Competitor cells state a **behaviour**, not a score. A number would imply a measurement nobody took.

| Dimension | Primnox (proposed) | ChatGPT | Claude | Gemini | Perplexity | Copilot | Cursor | Manus |
|---|---|---|---|---|---|---|---|---|
| **Ease of learning** | **BEHIND** — the track metaphor is unfamiliar at first contact | Suggested prompts, sidebar list | Flat recency + projects | Flat recency list | Query-first | Search-integrated | Steep; IDE + modes | Medium; agent framing |
| **Speed (first useful output)** | **UNKNOWN** — depends on local hardware | UNKNOWN | UNKNOWN | UNKNOWN | Research ~3–4 min; Assets 10 min+ | UNKNOWN | UNKNOWN | Minutes to hours |
| **Speed (observability of)** | **BETTER** — first-token latency and success rate are surfaced | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| **Discoverability** | **BEHIND** — hover-gated actions, model selector off-composer | Model selector in composer | Model selector in composer | Canvas button in prompt bar | Mode selector | Tone selector | `Shift+Tab` mode rotation | Computer panel always visible |
| **Agent transparency** | **BETTER** — four-valued outcomes incl. `unknown` | Reasoning summary | Reasoning summary | UNKNOWN | Assets tab of generated files | UNKNOWN | Diff view + checkpoints | Computer panel + replayable sessions |
| **Artifact handling** | **BEHIND today** — split Canvas / modal viewer | Writing + code blocks, inline | Artifacts, publish, sidebar section | Canvas panel, export to Docs | Assets: PPTX/DOCX/XLSX/HTML | Pages, `.loop` in SharePoint | Files in repo + diffs | Files + replay |
| **Canvas workflow** | **CONVENTIONAL, then narrow** — keep docs-only | **Deprecated** for GPT-5.5+ | Artifacts panel | Canvas panel with code/preview | Inline app/dashboard | Pages side-by-side | The editor *is* the canvas | UNKNOWN |
| **Rich blocks in the response** | **BEHIND** — every non-document goes straight to a modal | Writing + code blocks, editable inline | Artifacts open beside the chat | Canvas panel | Assets below the query | Pages beside the chat | Inline diffs in the editor | UNKNOWN |
| **Visual comprehension** | **BETTER (measured)** — 0 contrast failures, state in form before hue | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| **Customisation** | **BETTER (structural)** — provider, model, routing, 10 themes | Custom instructions, Projects | Projects, styles | Gems | Spaces + custom instructions | Tenant policy | Rules, model choice | UNKNOWN |
| **Scalability (many objects)** | **BEHIND** — no Project object | Projects w/ project-only memory | Projects | UNKNOWN | Spaces/Projects, Brain tab, Tasks | Pages in SharePoint, audited | Workspaces/repos | UNKNOWN |
| **Mobile usability** | **N/A** — no mobile client; loopback-only | Native apps | Native apps | Native apps | Native apps | Native apps | Desktop IDE | Web |
| **Cognitive load** | **BEHIND today / PARITY proposed** — ContextRail shows 15+ points at once | Progressive | Progressive | Progressive | Progressive | Progressive | High by design | Medium |

**Cell-by-cell sourcing follows. Every non-UNKNOWN competitor cell traces to vendor documentation.**

### A.3 Row notes — where Primnox is genuinely better

#### Agent transparency — BETTER, conditional on shipping

**[observed]** Manus is the best competitor here. Its third panel, "Manus's Computer," shows steps,
tools and intermediate results in real time, and sessions are replayable step by step
([MIT Technology Review review](https://www.technologyreview.com/2025/03/11/1113133/manus-ai-review/),
[WorkOS](https://workos.com/blog/introducing-manus-the-general-ai-agent)). **[observed]** Cursor
applies edits as it works and gives you a diff view to reject from, plus automatic Checkpoints that
snapshot agent changes — with the explicit caveat in its own docs that checkpoints "are not version
control" and do not track manual edits
([Cursor: Checkpoints](https://docs.cursor.com/agent/chat/checkpoints),
[Cursor: Reviewing and Testing](https://cursor.com/learn/reviewing-testing)).

**[inference]** Both show you *what happened*. Neither has a vocabulary for *we do not know what
happened*. `backend/v2/task_state.py` does: outcomes are `completed | failed | partial | unknown`,
and unit 10 identified exactly why that fourth value is load-bearing — a tool that crashes mid-write
did not fail cleanly, and calling it `failed` invites a destructive blind retry
(`docs/ui-research/10-long-running-agents.md` §"Four-valued outcomes").

This is the strongest genuinely-differentiated row in the matrix, and it is currently **worth
nothing**, because no UI reads it. Unit 10 confirmed: "`task_state.render()` exists; no UI uses it."
`grep` over `frontend/src` finds `task_state` only inside unit 10's own prototype directory.

**Verdict: PROTOTYPE → then CHANGE — surface `backend/v2/task_state.py` through the agent-status
layer, not through a new nav destination.** Sequencing is in Part B; it depends on the status layer
existing first.

#### Visual comprehension — BETTER, and it is the only cell in this row I can defend

`DESIGN.md:121–128` treats WCAG 2.1 AA as a defect line and records the measurement: the `/50` step
computes to 4.61:1 on this substrate, 71 sub-floor usages were raised to it, and the current state is
"0 contrast failures across 19 distinct text styles." `App.tsx:24–33` carries state in the mark's
*form* before its hue — solid for a confirmed fix, hollow and dashed while reckoning forward, struck
on refusal — which survives greyscale and satisfies WCAG 1.4.1.

**Every competitor cell in this row is UNKNOWN and must stay UNKNOWN.** I did not measure ChatGPT's
or Claude's contrast ratios. **[inference]** Primnox is not necessarily more legible than they are;
it is the only one of the eight where somebody wrote the number down. That is a real and unusual
advantage, and it is a smaller advantage than "we are more accessible than ChatGPT" would sound.

**Verdict: KEEP — `DESIGN.md:121–128`.** With one caveat from unit 12, below.

#### Customisation — BETTER for a structural reason

**[observed]** ChatGPT Projects carry files, instructions and a project-only memory mode that walls
project context off from global memory
([OpenAI: Projects in ChatGPT](https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt)).
**[observed]** Perplexity Spaces (now Projects) carry a Brain tab for generated memory, a Settings
tab, custom instructions, files and links, and scheduled Tasks
([Perplexity Help Center](https://www.perplexity.ai/help-center/en/articles/10352961-what-are-spaces)).
These are deep customisation surfaces.

None of them let you choose the model vendor, because none of them can. `frontend/src/components/OmniRoute.tsx`,
`ModelProfiles.tsx`, `Tunables.tsx`, `ThemePicker.tsx` and `PrivacySettings.tsx` exist because
`PRODUCT.md:45` commits to running "fully local, any provider."

**Verdict: KEEP.** And **[inference]** stop treating this as a UI achievement. Primnox wins this row
by architecture. The UI's job is to not squander it — which, per unit 11 §3.1, it partly does by
leaving the model selector as a non-interactive status label in the composer.

### A.4 Row notes — where Primnox should deliberately stay conventional

#### Ease of learning — BEHIND, and the fix is to copy

**[principle]** Jakob's Law: "Users spend most of their time on other sites. This means that users
prefer your site to work the same way as all the other sites they already know"
([Laws of UX](https://lawsofux.com/jakobs-law/); NN/g frames consistency as its corollary in
[The Power Law of Learning](https://www.nngroup.com/articles/power-law-learning/)). NN/g's
[Mental Models](https://www.nngroup.com/articles/mental-models/) makes the mechanism explicit: a
user's model of your product is largely assembled from other products.

Unit 1 called the Dead Reckoning track "proprietary and **incompatible** with mainstream
expectations." Unit 12 defended the archetype on radius and monospace and was right to. **[inference]**
These are not in conflict, because they are about different layers. Unit 12's verdicts concern the
*visual* language — a user does not need a mental model to read a sharp-cornered button. The track
metaphor concerns the *navigational* language, which is exactly where Jakob's Law bites.

**Verdict: KEEP the track (`frontend/src/components/TrackRow.tsx`) — CHANGE the first contact.** The
target statement resolves this and is the reason it is a good target statement: familiar at first
contact means the shell, the composer and the message actions match convention. Deeper operating
model means the track, the fix, the four-valued outcome. A new user should not have to learn "dead
reckoning" to send a message; they should discover it when their work gets long enough to need it.

#### Canvas workflow — CONVENTIONAL, and this is the roadmap's most consequential finding

**[observed]** ChatGPT has **deprecated canvas**. OpenAI's help centre states canvas is not supported
by GPT-5.5 or later, that it is unavailable in GPT-5.5 Instant or Thinking, that paid users may use
it only through legacy models until those sunset, and that writing and coding are now supported
"directly in chat responses through writing blocks and code blocks" — editable areas for draft text,
and code blocks kept separate from the rest of the response so they can be read, edited, copied,
previewed or run, with edits saved back to the conversation
([OpenAI Help Center: canvas](https://help.openai.com/en/articles/9930697),
[OpenAI Help Center: writing blocks and code blocks](https://help.openai.com/en/articles/20001246-working-with-writing-blocks-and-code-blocks-in-chatgpt)).
*Sourcing note: help.openai.com returns HTTP 403 to direct fetches; this is the help centre's own
text as surfaced through search on 2026-08-26, not a paraphrase of secondary coverage.*

The rest of the field still has canvases. **[observed]** Gemini Canvas is a panel with Code/Preview
views, a console, auto-saved document edits, Export to Docs and Export to Colab
([Google: Create docs, apps & more with Canvas](https://support.google.com/gemini/answer/16047321)).
**[observed]** Claude Artifacts are documents, code and single-file HTML, publishable to a public
link that adds them to an Artifacts section in the sidebar, with the sharp edge that unpublishing is
irreversible for that artifact
([Anthropic: publish and share artifacts](https://support.claude.com/en/articles/9547008-publish-and-share-artifacts),
[Anthropic: what are artifacts](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them)).
**[observed]** Copilot Pages is a persistent, shareable, co-authored canvas backed by `.loop` files in
a per-user SharePoint Embedded container, with audit-log attribution
([Microsoft: How Copilot Pages works](https://support.microsoft.com/en-us/microsoft-365-copilot/how-microsoft-365-copilot-pages-works)).
**[observed]** Perplexity Assets (formerly Labs) collects generated charts, CSVs and code into an
Assets section below the query, exporting PPTX, DOCX, XLSX and HTML
([Perplexity: creating assets](https://www.perplexity.ai/help-center/en/articles/12528830-creating-assets-with-perplexity-overview)).

**[inference]** The largest deployment of a canvas in the world just walked it back toward inline
blocks. That does not mean canvas is wrong — four other vendors still ship one — but it is strong
evidence against *expanding* Primnox's canvas as the next big investment, which is the obvious read
of "Canvas.tsx handles documents only while SlideDeck, SheetTable, WebPreview and FlowchartBlock open
as modals."

The model already says this, and it took the ChatGPT deprecation for me to notice: the model's chain
is `{ Text | Rich Block | Action } → Artifact → { Quick preview | Canvas }`. **Rich Block comes
before Canvas, and Quick preview is listed before Canvas.** Canvas is the escape hatch, not the
destination.

**Verdict: KEEP `frontend/src/components/Canvas.tsx` scoped to documents. PROTOTYPE inline rich
blocks for `SlideDeck.tsx`, `SheetTable.tsx`, `WebPreview.tsx` and `FlowchartBlock.tsx`** — which
today are reachable only as modals via `AssetViewer.tsx`. Promoting a modal to a bounded inline block
is a smaller change than unifying two surfaces, and it is the one the evidence supports.

#### Discoverability — BEHIND, fix by convention

**[observed]** ChatGPT and Claude both put the model selector in or beside the composer; Gemini puts
Canvas in the prompt bar; Cursor rotates modes with `Shift+Tab` from the chat input
([Cursor: Plan Mode](https://cursor.com/docs/agent/plan-mode)). **[principle]** NN/g's Heuristic #6,
recognition rather than recall: "it's much easier for users to recognize a visible, labeled icon or
action than to recall a keyboard shortcut"
([NN/g: Memory Recognition and Recall](https://www.nngroup.com/articles/recognition-and-recall/)).

Primnox's composer shows the model as text and nothing else — `App.tsx:944–950` per unit 11 §2.1,
formatted `"${model} · ${local|cloud}"`. Unit 11 recommended Option A, an inline dropdown, on the
grounds that A/B testing between models is core to the product.

**Verdict: CHANGE — make the composer's model label interactive.** Unit 11 already specified it;
this unit only confirms the sequencing (MVP, because it is the cheapest familiarity win and blocks
nothing).

### A.5 Row notes — where Primnox is behind and should admit it

#### Artifact handling — BEHIND today

The gap is real: `Canvas.tsx` has version history and revert; `SlideDeck`, `SheetTable`, `WebPreview`
and `FlowchartBlock` open as modals through `AssetViewer.tsx` and have neither. Claude, by contrast,
gives an artifact a durable home in the sidebar and a public URL.

But unit 6 tested the obvious fix and it failed. Its verdict, which the roadmap must respect rather
than restate: **a unified artifact *metadata* layer works; a unified *lifecycle* does not.**
`06-artifact-model.md` enumerates why — Canvas owns its own open/close state and lazily loads on
first open; AssetViewer is parent-controlled and fetches on mount; Canvas is `<aside>`, AssetViewer
is `<div class="fixed">`; Canvas mutates into new versions, assets are immutable and content-addressed.
Its conclusion: "Trying to merge them trades two focused, correct implementations for one confused,
branchy one."

**Verdict: CHANGE, but only the layers unit 6 cleared.** Build `ArtifactMetadata` and a shared
`ArtifactPreview` renderer (unit 6's two DO items). Do **not** build a unified `Artifact` component.
This is the difference between a roadmap item that ships and a refactor that stalls.

#### Scalability — BEHIND, and it is the model's last unbuilt step

**[observed]** Every mainstream competitor has a project object: ChatGPT Projects with project-only
memory; Claude Projects; Perplexity Spaces with a Brain tab and scheduled Tasks; Copilot Pages living
in SharePoint with per-page sensitivity labels and audit attribution.

Primnox has folders and pinning in the conversation list (`App.tsx`, `ContextSidebar.tsx`) and
`backend/v2/world_model.py` scopes facts by project internally. It has no Project surface. The model
ends `Persistent object → Project`, and that arrow points at nothing.

**Verdict: PROTOTYPE, V2 not MVP.** It depends on the artifact metadata layer — a Project is a
container of persistent objects, and there is no common shape for a persistent object until
`ArtifactMetadata` exists. Building Projects first produces a folder with a nicer name.

#### Cognitive load — BEHIND today

Unit 7 counted it: ContextRail presents 15+ data points simultaneously, including stream cursor
position and socket state (`ContextRail.tsx:146–153`), during a two-second turn. Its proposed
three-level hierarchy — Glance / Expand / Deep Inspect, with level 2 auto-opening past 2s — is the
fix, and it is the same shape as unit 8's five-level cascade in
`docs/PROGRESSIVE_DISCLOSURE_FRAMEWORK.md`. **[principle]** Progressive disclosure "defers secondary
options to a subsidiary screen, focusing users' attention on the primary options"
([NN/g: Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/)).

**Verdict: CHANGE — `frontend/src/components/ContextRail.tsx` and `TurnBlock.tsx`'s `LiveStatus`.**
MVP. See Part B for why this one comes before the task panel.

#### Mobile — N/A, and unit 5's mobile work should be labelled as speculative

`05-artifact-cards.md` Part 3 and Part 7 specify bottom action sheets, swipe-to-reveal, 44px touch
targets and a three-breakpoint behaviour matrix. It is careful work. It also describes a device class
Primnox does not ship to and, per `PRODUCT.md:79`, cannot ship to without changing the loopback
security model.

**[inference]** The one part of unit 5's mobile analysis that *does* apply today is the touch-capable
desktop case — Windows laptops with touchscreens — and that is precisely what breaks the hover-gated
copy button in §0.1. That is the whole of the current mobile surface area.

**Verdict: KEEP as research, do not schedule.** Mark unit 5 Part 3 as pending a mobile client.

### A.6 The UNKNOWN cells, counted

**26 competitor cells are UNKNOWN.** That number is not an estimate: it was counted off the rendered
matrix in the prototype, by walking `tbody` and skipping the Verdict and Primnox columns. An earlier
draft of this document said "eleven" from memory and was wrong by more than a factor of two — which is
a small, useful demonstration of Principle 5 catching its own author.

Distribution:

| Product | UNKNOWN cells (of 13) |
|---|---|
| Manus | 6 |
| Gemini | 5 |
| Copilot | 4 |
| ChatGPT | 3 |
| Claude | 3 |
| Cursor | 3 |
| Perplexity | 2 |

**[inference]** The shape of that distribution is itself a finding. Manus and Gemini are the least
documented of the seven — Manus has no first-party documentation I could locate at all, which is why
both of its sources in this document are independent journalism. The two products Primnox would most
want to benchmark against on agent transparency are the two it can verify least. Any strategy resting
on "we are more transparent than Manus" is resting on six blanks.

What went unverified, by kind: first-token latency for six of seven competitors; Gemini's and
Copilot's agent step-transparency; measured contrast ratios for **all seven**; Manus's customisation,
project model and canvas behaviour; Gemini's project/space model.

**Do not build against an UNKNOWN cell.** If a decision needs one, go and measure it — the cost is an
afternoon with seven browser tabs, and the alternative is a quarter spent on an assumption.

---

## PART B — ROADMAP

Sequenced by dependency and by evidence of value, not by ease. Every item states what it unblocks.

### B.1 Recommended MVP — the smallest set that delivers the target statement

The target statement has two halves. The MVP must deliver **both**, or it proves nothing: familiar at
first contact, deeper model as work gets complex. Four build items and one scoping item.

---

**M0 — Correct the gap list. (Scoping, zero build.)**

Copy exists (`TurnBlock.tsx:138`). Search exists (`App.tsx:479–500`). Remove both from unit 1's
Phase 1.

*Unblocks:* roughly a third of what unit 1 called Phase 1, freed for M1–M4.

---

**M1 — Message actions become unconditionally visible, and gain regenerate.**
**CHANGE — `frontend/src/components/TurnBlock.tsx:136–141`.**

Ungate the existing copy button from hover. Add regenerate beside it — `api.retry` already exists at
`TurnBlock.tsx:157` but is reachable only through `RecoveryBlock` on a *failed* turn, so a user who
got a mediocre-but-successful answer has no path to another one. Every competitor has this.

*Depends on:* nothing.
*Unblocks:* the "familiar at first contact" half. It is the cheapest item on the list and the one a
first-time user meets first.
*Evidence:* unit 1 §2 (the deviation), NN/g Heuristic #6 (recognition over recall), §0.1 (the touch
hole).

---

**M2 — The composer's model label becomes a selector.**
**CHANGE — the composer block in `frontend/src/App.tsx` (unit 11 §2.1 locates it at 944–950).**

*Depends on:* nothing.
*Unblocks:* the customisation advantage from §A.3, which is currently structural-only. This is where
Primnox's one architectural edge over every mainstream competitor becomes visible to a user.
*Evidence:* unit 11 §3.2 Option A, with its stated rationale that A/B testing between models is core
to the product; **[observed]** ChatGPT, Claude and Cursor all place mode/model selection at the input.

---

**M3 — AgentStatus levels 1 and 2 replace LiveStatus and thin out ContextRail.**
**CHANGE — `frontend/src/components/TurnBlock.tsx` (LiveStatus, ~35–48) and `ContextRail.tsx:55–162`.**

Level 1 is status word plus elapsed time. Level 2 auto-opens past 2s and shows progress steps, recent
files, and the single most critical warning. Level 3 is deferred to V2.

*Depends on:* nothing.
*Unblocks:* **everything in the agent layer.** This is the load-bearing MVP item and the reason it
sits above the task panel that looks more impressive. The model insists agent activity is a layer,
not a destination. Level 2 *is* that layer. Without it, the next person who needs to surface
long-running work will reach for the only container that exists — a fifth entry in `AppRail`'s
`Section` union (`AppRail.tsx:6`) — and the orthogonality is gone permanently.
*Evidence:* unit 7's three-level hierarchy and its count of 15+ simultaneous data points; unit 8's
five-level cascade; NN/g on progressive disclosure.

---

**M4 — `ArtifactMetadata` + one shared `ArtifactPreview` renderer. No unified component.**
**CHANGE — new shared module; `Canvas.tsx` and `AssetViewer.tsx` both consume it. Their lifecycles
stay separate.**

*Depends on:* nothing technically, but should land after M3 so the artifact rows in level 2 have a
shape to render.
*Unblocks:* M5 (inline rich blocks need one preview renderer, not five), V4 (a Project is a container
of persistent objects and needs them to have a common shape), and the "Quick preview" node of the
model.
*Evidence:* unit 6, precisely and only its two DO items. Unit 6's DO NOT — a unified component — is
excluded from this roadmap at every level, including Future. It was tested and it failed; it does not
get to come back as an aspiration.

---

**M5 — `SlideDeck`, `SheetTable`, `WebPreview` and `FlowchartBlock` render inline as bounded rich
blocks, with the modal kept as the expand action.**
**PROTOTYPE → CHANGE — `frontend/src/components/{SlideDeck,SheetTable,WebPreview,FlowchartBlock}.tsx`,
`AssetViewer.tsx`.**

*Depends on:* M4.
*Unblocks:* the `{ Text | Rich Block | Action }` node — the step the model puts *before* artifact and
canvas, and the step Primnox currently skips entirely by sending every non-document straight to a
modal.
*Evidence:* **[observed]** OpenAI replaced canvas with inline writing and code blocks for GPT-5.5+;
unit 5's finding that cards work as metadata-first progressive disclosure and become noise as bare
containers; the model's own ordering.

**MVP stops here.** Five items, four of them code. It delivers familiar-at-first-contact (M1, M2) and
a deeper model that appears as work gets complex (M3's auto-expand at 2s, M5's blocks appearing only
when there is something to show).

### B.2 Recommended V2 — once the MVP is proven

"Proven" means specifically: M3's level 2 is where people actually look when a turn runs long, and M5's
inline blocks are opened more often than the modals were. If they are not, V1 and V3 below are built
on sand.

---

**V1 — Task panel and catch-up summary, surfacing `backend/v2/task_state.py`.**
**PROTOTYPE exists (unit 10's `long-running-agents` prototype) → CHANGE.**

Background task indicator, task goal and status, progress through planned actions, and the four-valued
outcome rendered as four visually distinct states — `completed`, `failed`, `partial`, `unknown` — with
`verify()` offered before any retry on an `unknown`.

*Depends on:* **M3, hard.** The task panel must be an expansion of the agent-status layer, not a new
rail entry. This is the single sequencing decision in the roadmap most likely to be got wrong under
schedule pressure, because a rail entry is easier to build than a layer.
*Unblocks:* the matrix's one genuinely differentiated row (§A.3), and V5.
*Evidence:* unit 10's Phases 1–2 and its gap audit; **[observed]** Manus's Computer panel and
replayable sessions as the pattern to match, and its absence of an "unknown" state as the thing to
beat.

---

**V2 — Light theme as an accessibility accommodation.**
**CHANGE — `frontend/src/styles/themes.css`.**

Unit 12's one CHANGE verdict out of three, and it is narrow on purpose: dark stays primary and the
archetype is untouched; light exists for users with photophobia, migraine or low vision who currently
have no workaround. Contrast must be re-verified in the running app, not asserted — `DESIGN.md:121`
says as much, and a light substrate invalidates every measured ratio in the current table.

*Depends on:* nothing. Placed in V2 rather than MVP only because it is orthogonal to the target
statement, not because it matters less.
*Unblocks:* nothing. It closes a compliance gap.
*Evidence:* unit 12 §3. Note that unit 12's other two verdicts — zero radius, monospace by default —
are **KEEP**, and appear on this roadmap nowhere. That is the correct outcome for a design review: two
of three choices survived scrutiny.

---

**V3 — Approval gate for state-mutating actions, with the diff as a rich block.**
**PROTOTYPE exists (unit 2's `coding-agents` prototype) → CHANGE.**

*Depends on:* M5. The diff is a rich block; building it before rich blocks exist means building a
sixth one-off modal.
*Unblocks:* the `Action` branch of `{ Text | Rich Block | Action }`, which is the least-developed of
the three.
*Evidence:* **[observed]** every coding agent surveyed in unit 2 stages edits before applying them;
**[observed]** Cursor's own best-practices page warns that "AI-generated code can look right while
being subtly wrong" and that faster agents make review more important, not less
([Cursor: agent best practices](https://cursor.com/blog/agent-best-practices)).
**[inference]** Unit 2's own risk section is right that this adds friction, and its mitigation —
auto-accept below a size threshold — should ship *with* the gate, not after it.

---

**V4 — The Project object.**
**PROTOTYPE — new surface; `frontend/src/App.tsx` shell, `backend/v2/world_model.py` already scopes
facts by project.**

*Depends on:* M4. A Project is a container of persistent objects; it needs `ArtifactMetadata` to
contain anything coherent.
*Unblocks:* the final `Persistent object → Project` arrow of the model, and the matrix's Scalability
row.
*Evidence:* **[observed]** ChatGPT Projects, Claude Projects, Perplexity Spaces and Copilot Pages all
converge on this object, which is about as strong as convergent evidence gets;
**[observed]** ChatGPT's project-only memory mode is the specific variant worth copying, because it
matches `PRODUCT.md`'s privacy posture better than a global memory does.

---

**V5 — Citation and provenance blocks, surfacing `backend/v2/world_model.py`.**
**PROTOTYPE exists (unit 3's `research-build-agents` prototype) → CHANGE.**

*Depends on:* M5 for the block, V1 for the pattern of surfacing a tested-but-invisible backend.
*Unblocks:* the trust argument for a local-first assistant — a claim you can trace.
*Evidence:* unit 3's survey and its `Citation` primitive, which deliberately reuses `world_model`'s
existing `source / origin / confidence` triad rather than inventing a parallel one.
**[inference]** This is sequenced last in V2 rather than in MVP because unit 3's own backend audit
lists six schema gaps (execution-trace tracking, TTL, citation backlinks, result bundling, query
storage, confidence evolution). It is not a UI change with a backend detail; it is a backend change
with a UI.

### B.3 Future / advanced — worth wanting, not worth building yet

Each of these fails at least one of: it has no proven dependency below it, or nobody has measured
that anyone wants it, or a constraint blocks it outright.

| Item | Why not yet |
|---|---|
| **Episodic timeline — "what was I doing yesterday" (`backend/v2/episodes.py`)** | Needs V1's task panel as a home, or it becomes a sixth nav destination. And nobody has measured how often a Primnox user returns to work after a >30 minute gap — `episodes.py` picks 30 minutes as the consolidation boundary, which is an assumption, not a finding. Build V1, instrument the gap distribution, then decide. |
| **Voice input** | Unit 11 §2.3 leaves local-vs-cloud transcription undecided, and `PRODUCT.md:118` says "Local is the default, not the fallback." A cloud STT default would contradict the product thesis; a local one is a model-shipping problem, not a UI one. |
| **Mobile client** | Blocked by `PRODUCT.md:79`, loopback-only. Not a backlog item — an architecture decision nobody has asked for. |
| **Parallel / delegated agent sessions (Devin, Hermes fan-out)** | Unit 10 documents the pattern well. It requires task-switching UI, and V1 deliberately ships one active task at a time. Prove one task first. |
| **Published / shareable artifacts** | **[observed]** Claude publishes artifacts to public URLs; Copilot Pages shares through Teams. Both are network products. A loopback-only desktop app publishing to the internet is a new trust boundary and `PRODUCT.md:115` requires every privacy boundary to be measured. Worth wanting. Not worth doing casually. |
| **Unified Canvas/AssetViewer component** | **Struck from every horizon.** Unit 6 built it and it failed. Listing it as "future" would let it return as an aspiration. |

### B.4 Sequencing summary

```
M0 scoping ──┐
M1 actions ──┤ (independent, cheapest, first contact)
M2 selector ─┘
M3 agent-status L1+L2 ──┬──────────────► V1 task panel ──► V5 citations
                        │                                    ▲
M4 artifact metadata ───┼──► M5 rich blocks ──► V3 approval ─┤
                        └──► V4 project object                │
V2 light theme (independent) ─────────────────────────────────┘
```

**The two edges that matter most:** M3 → V1 (or agent work becomes a nav destination and the model
breaks), and M4 → M5 → V3/V4 (or every artifact type gets its own bespoke surface, which is the
condition Primnox is already in).

---

## PART C — FINAL PRINCIPLES

Seven. Each is written to settle an argument this research did not anticipate. A principle that
cannot decide a coin-flip is a slogan; these are meant to be quoted at each other in a review.

---

**1. Familiar at the edges, novel at the centre.**

Jakob's Law governs the shell — the composer, the message actions, the conversation list, the model
selector. The archetype governs the content — the track, the fix, the four-valued outcome, the
monospace, the zero radius. When a proposal is unconventional, ask which layer it lives in. Shell
innovation costs a new user their first five minutes and buys nothing. Content innovation is the
product.

*Settles:* "Should our composer look like ChatGPT's?" — yes. "Should our turn look like ChatGPT's?" —
no.

---

**2. Agent activity is a layer, never a destination.**

If a proposal's answer to "where does it go?" is a new entry in the rail, the proposal is wrong. The
rail has four sections and the fifth one is where this model dies. Agent state expands *around* the
work — level 2 of the status hierarchy, a block in the turn, a panel over the transcript.

*Settles:* every "add a tab for X" argument, permanently.

---

**3. Unify what things ARE. Never unify what they DO.**

Unit 6's verdict, generalised: a shared metadata shape and a shared renderer are cheap and correct; a
shared lifecycle is a `type` field and a branch at every decision point. Two focused components beat
one branchy one. Before merging any two surfaces, write down their state machines. If the machines
differ, you are unifying the wrong layer.

*Settles:* any future "these two components are basically the same" refactor.

---

**4. `unknown` is a shippable state, and often the honest one.**

A tool that crashed mid-write did not fail. A competitor behaviour nobody checked is not "probably
fine." A contrast ratio nobody measured is not "looks OK." The interface must be able to say it does
not know, in the same visual vocabulary it uses to say yes and no — because the alternative is a
confident wrong answer, and in a retry loop a confident wrong answer is destructive.

*Settles:* "what do we show while we're not sure?" — say so. Do not pick the nearest certain state.

---

**5. Measure the claim, or drop the claim.**

`DESIGN.md` already holds this line for contrast: "Measured in the running app rather than assumed."
Extend it to everything the interface asserts. Do not ship a latency number nothing timed, a "faster
than" nothing benchmarked, or a competitor comparison nobody opened the competitor to check. An
UNKNOWN in a document is a cost of one line. An UNKNOWN acted on as a fact is a cost of a quarter.

*Settles:* "is this accessible / faster / better than theirs?" — go and look, or say UNKNOWN.

---

**6. A backend capability that no UI reads does not exist — and surfacing it must earn its space
like a new feature.**

`task_state.py`, `episodes.py` and `world_model.py` are tested, working, and worth nothing to a user
today. That argues for surfacing them. It does not argue for surfacing them *cheaply*: "the backend
is already done" is not a reason to skip the question of whether anyone wants it, or to bolt it on
somewhere convenient. Sunk backend cost is sunk.

*Settles:* "we already built it, just expose it" — expose it *well*, or leave it.

---

**7. When the industry retreats from a pattern, that is evidence.**

OpenAI deprecated canvas for inline blocks. That does not make canvas wrong — four other vendors
still ship one — but it does mean "everyone has a canvas, ours should be better" is no longer an
argument. Convergence is evidence. So is divergence. So is a retreat. Read the direction of travel,
not just the current position, and treat a vendor walking something back as the most informative
signal on offer, because they paid for the lesson.

*Settles:* any "the market has X, we need X" claim — check whether the market is still moving toward X.

---

## Prototype

`frontend/src/components/proto/benchmark-roadmap/` renders the Part A matrix as a comparison
component: 13 dimensions across 8 products, with the verdict vocabulary as text rather than colour,
expandable per-row detail carrying the citations, and filters for the three questions a reader
actually arrives with — where is Primnox ahead, where is it behind, and what did nobody verify. A
second tab renders Part B, with `depends on` and `unblocks` on every item.

Reachable from `frontend/proto.html` (dev server on port 5273) as entry 13.

**Verified in the running app**, not asserted:

| Check | Result |
|---|---|
| `npm --prefix frontend run typecheck` | 0 errors |
| `npm --prefix frontend run build` | succeeds, 2131 modules |
| Contrast, measured via `getComputedStyle` + canvas colour resolution | **0 failures**, minimum **4.61:1** across 13–25 distinct text styles per view |
| Views audited | matrix, matrix with a row expanded, all four filters, roadmap tab |
| Nested interactive elements (`button > button`, `button > a`) | 0 |
| Non-zero computed `border-radius` | 0 — DESIGN.md's structural zero holds |
| Console under `React.StrictMode` | clean; no `validateDOMNesting` |
| Table semantics | `<caption>` present, every `<th>` scoped `col` or `row` |

Two notes on the contrast method, because the first two attempts produced false failures and the
method is the part worth reusing. Chrome returns theme colours as `color(srgb 0…1)` and Tailwind's
opacity modifiers as `oklab(…)`; a regex that assumes `rgb(0…255)` reads white-on-black as 1.03:1.
Resolving every colour by painting it to a 1×1 canvas and reading the pixel handles all three. And
the substrate is painted on `:root` — `bg-bg` computes to `transparent` on the gallery's own root and
on this prototype's — so the audit must walk to the first opaque ancestor and composite down, or the
translucent zebra fill is measured against nothing.

---

## Sources

Vendor documentation:
- [OpenAI Help Center — canvas](https://help.openai.com/en/articles/9930697)
- [OpenAI Help Center — writing blocks and code blocks](https://help.openai.com/en/articles/20001246-working-with-writing-blocks-and-code-blocks-in-chatgpt)
- [OpenAI Help Center — Projects in ChatGPT](https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt)
- [Anthropic — What are artifacts](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them)
- [Anthropic — Publish and share artifacts](https://support.claude.com/en/articles/9547008-publish-and-share-artifacts)
- [Google — Create docs, apps & more with Canvas](https://support.google.com/gemini/answer/16047321)
- [Microsoft — How Microsoft 365 Copilot Pages works](https://support.microsoft.com/en-us/microsoft-365-copilot/how-microsoft-365-copilot-pages-works)
- [Perplexity — Creating assets: overview](https://www.perplexity.ai/help-center/en/articles/12528830-creating-assets-with-perplexity-overview)
- [Perplexity — What are Spaces/Projects](https://www.perplexity.ai/help-center/en/articles/10352961-what-are-spaces)
- [Cursor — Plan Mode](https://cursor.com/docs/agent/plan-mode)
- [Cursor — Checkpoints](https://docs.cursor.com/agent/chat/checkpoints)
- [Cursor — Reviewing and Testing Code](https://cursor.com/learn/reviewing-testing)
- [Cursor — Best practices for coding with agents](https://cursor.com/blog/agent-best-practices)

Manus (no first-party documentation located; both sources are independent):
- [MIT Technology Review — We put Manus to the test](https://www.technologyreview.com/2025/03/11/1113133/manus-ai-review/)
- [WorkOS — Introducing Manus: the general AI agent](https://workos.com/blog/introducing-manus-the-general-ai-agent)

UX principles:
- [NN/g — Memory Recognition and Recall in User Interfaces](https://www.nngroup.com/articles/recognition-and-recall/)
- [NN/g — Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/)
- [NN/g — Mental Models and User Experience Design](https://www.nngroup.com/articles/mental-models/)
- [NN/g — The Power Law of Learning](https://www.nngroup.com/articles/power-law-learning/)
- [Laws of UX — Jakob's Law](https://lawsofux.com/jakobs-law/)

Primnox research units, read in full for this synthesis:
`01-mainstream-assistants.md`, `02-coding-agents.md`, `03-research-build-agents.md`,
`05-artifact-cards.md`, `06-artifact-model.md`, `07-agent-status.md`, `10-long-running-agents.md`,
`11-navigation-composer.md`, `12-familiarity-design-system.md`,
`../PROGRESSIVE_DISCLOSURE_FRAMEWORK.md`, `../failure-recovery-ux.md`.
Unit 4 was rerunning in parallel — see `04-response-primitives.md` for the response-primitive rule,
whose conclusions this document does not assume.

Primnox source read for verification:
`frontend/src/App.tsx`, `components/TurnBlock.tsx`, `components/ThinkingBlock.tsx`,
`components/Canvas.tsx`, `components/AppRail.tsx`, `components/ui/*`, `vite.config.ts`,
`DESIGN.md`, `PRODUCT.md`, `backend/v2/{task_state,episodes,world_model}.py`.
