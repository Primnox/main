# Primnox V2 — IRL Validation Plan

Captured 2026-08-22.

The standard for V2 is not "does the button work?" It is **"can this survive a
real user for eight hours a day?"** Every phase below is written against that
bar. A phase passes on evidence, not on impression.

Related: the `testing` skill (L0–L4 suite) is the mechanism; this document is
the acceptance criteria it has to satisfy.

---

## Phase 1 — Solo dogfooding (2 weeks)

Primnox is the primary desktop assistant. No fallback to manual habits.

Daily load:

- 8+ hours runtime
- 200+ commands
- 100+ window open/close cycles
- Hundreds of file searches
- Voice interruptions
- Memory recall after several days have passed
- Repeated workflow execution

**Pass:** no crashes, no memory corruption, startup stays under target, no
noticeable UI lag.

---

## Phase 2 — Student stress test

The target user. Scenarios given as goals, not instructions:

- "Summarize this 200-page PDF."
- "Create flashcards."
- "Find yesterday's screenshot."
- "Open VS Code and my notes."
- "Organize downloads."

**Measure:** time saved, wrong actions taken, failed searches, whether memory
was actually useful.

---

## Phase 3 — Developer stress test

Primnox running while coding.

- Git operations
- Terminal commands
- Reading large repositories
- Explaining errors
- Switching between browser and IDE
- Architecture discussions

**Watch for:** context loss, wrong repository understanding, slow responses.

---

## Phase 4 — Computer control reliability

The critical phase. Test across Explorer, Chrome, VS Code, Discord, Spotify,
Settings, and Task Manager.

For every application, every action:

| Action | Must also survive |
| --- | --- |
| open | target already open |
| click | element moved or re-rendered |
| type | focus stolen mid-input |
| scroll | virtualised / infinite lists |
| switch windows | target minimised or on another monitor |
| recover after failure | any of the above failing once |

**Target: 99% successful execution.**

---

## Phase 5 — Memory torture test

Runs over several weeks — this one cannot be compressed.

Verify Primnox:

- remembers names
- remembers projects
- remembers preferences
- **forgets deleted memories**
- retrieves old conversations
- avoids duplicate memories

Edge cases that must be handled explicitly: contradictory memories, renamed
projects, similar file names.

---

## Phase 6 — Workflow testing

| Workflow | Expected |
| --- | --- |
| Download → rename → move | Fully automatic |
| PDF → summary → notes | One command |
| Open study setup | Opens everything |
| End coding session | Saves context |

Each must be tested under interruption, retry, and partial failure — not only
on the happy path.

---

## Phase 7 — Living UI validation

The signature feature. Observe:

- The strip never feels distracting.
- Animations hold above 60 FPS.
- Morphing matches actual AI state.
- Islands appear naturally rather than popping.
- Overlay feels instant.

Ask testers one question: **"Does it feel alive?"**

If they describe it as "a loading animation," it is a redesign, not a tweak.

---

## Phase 8 — Voice testing

Real acoustic environments, not a quiet desk:

quiet room · fan noise · classroom · café · headphones · speakers

**Measure:** wake word accuracy, interruption handling, latency, false
activations.

---

## Phase 9 — Performance torture

Primnox running continuously.

- 24-hour uptime
- Memory leaks
- CPU spikes
- GPU usage
- Thousands of conversations
- Thousands of memory entries

**Record:** RAM, VRAM, response latency, startup time — as a time series, so a
slow leak is visible before it becomes a crash.

---

## Phase 10 — Security testing

Privacy is the selling point, so this phase is load-bearing.

- No unintended internet calls
- Encrypted memory
- Permission enforcement
- Skill isolation
- Secure file handling
- Export and delete actually work

---

## Blind testing with real users

Give testers **goals**, never instructions:

- "Find the PDF you used yesterday."
- "Open your study setup."
- "Summarize this document."
- "Remember my professor's name."
- "Organize today's downloads."

Watch without helping. **The moments where they hesitate are the UX defects.**

---

## Failure injection

Break things on purpose. Primnox must degrade gracefully, not fail hard.

- Internet disconnects
- Local model crashes
- Workflow interrupted mid-step
- File deleted mid-task
- Window moved unexpectedly
- Low RAM
- High CPU
- Multiple monitors unplugged

---

## Metrics dashboard

Tracked continuously during testing.

| Metric | Target |
| --- | --- |
| Startup | under 1 s |
| Overlay | under 100 ms |
| Search | under 300 ms |
| Memory recall | over 95% relevant |
| Computer actions | over 99% success |
| Workflow completion | over 95% |
| Crash rate | under 1 per 100 hours |
| Animation | stable 60 FPS |

---

## The Iron Man Test

The final acceptance test.

Give someone who has never used Primnox a Windows laptop and exactly one
instruction:

> "Use Primnox instead of opening apps manually for an hour."

If they naturally start relying on the strip, the overlay, memory, and
one-command workflows **without needing explanations**, V2 has achieved its
goal: an operating-system companion, not another chatbot.
