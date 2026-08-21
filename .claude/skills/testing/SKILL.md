---
name: testing
description: Primnox's master testing capability — 300 specialized checks spanning UI, visual validation, frontend logic, backend/API, performance, chaos and reliability, security, AI systems, hardware, filesystem, accessibility, installer/updates, observability, CI/CD, data integrity, and privacy. Use this whenever the user wants to test, verify, validate, QA, reproduce a bug, hunt a regression, harden a change, or asks "does this work", "is this broken", "why did this fail", or "can you check". Also use when a code change needs verification before it ships, when writing or extending tests in the L0–L4 suite, when triaging a failing test, or when a finding needs a report with severity, confidence, evidence, and reproduction steps. Prefer this over ad-hoc pytest invocations or eyeballing the UI — it selects the sub-capabilities that actually apply to the change, runs them against the real harness, and refuses to call something verified without evidence.
---

# Primnox Testing

A router over 300 testing capabilities, not a checklist to execute. The value here
is **selection**: running eight relevant checks on a change beats running three
hundred irrelevant ones, and a report that says "these eight applied, here's why"
is far more useful than a wall of green.

The full catalog lives in `references/catalog.md`. Don't read it to pick checks —
use the routing table below, then open the one or two domain references you need.

## The pipeline

Every investigation follows the same eight steps. They exist because the
expensive failure mode in testing is not missing a bug, it's reporting a bug
that isn't real or a fix that didn't work.

1. **Identify what changed.** `git diff --stat` / `git status`. Read the diff, not
   just the filenames — a one-line change in `kernel/events.py` has a wider blast
   radius than fifty lines in a component.
2. **Select sub-capabilities.** Use the routing table. Name them explicitly before
   running anything, so the user can tell you you've missed one.
3. **Run in parallel where possible.** Independent suites and independent browser
   checks go in one batch. Nothing here is serial by nature except reproduce → fix → verify.
4. **Collect evidence.** Command output, screenshots, console messages, network
   traces, timings. Evidence is what separates a finding from a guess.
5. **Reproduce consistently.** A failure you've seen once is a lead. A failure you
   can trigger on demand is a bug. If it won't reproduce, say so and report it as
   flaky rather than quietly dropping it.
6. **Isolate the probable root cause.** Read the code path. Narrow to a file and a
   line where you can.
7. **Verify the fix** by re-running the exact reproduction that failed — not the
   whole suite, and not a similar case. Then run the suite to catch collateral damage.
8. **Report** in the format at the bottom of this file.

## The real harness

These commands are verified against this repo. Run them from `C:\project`.

**Backend — 599 tests, pytest.** The venv lives at `backend/venv` (not `v2/backend/venv`):

```bash
C:/project/backend/venv/Scripts/python.exe -m pytest v2/backend/tests -q
```

The suite is layered, and the layer names are meaningful — target them directly
instead of running everything when you know the blast radius:

| Layer | File | What it protects |
|---|---|---|
| L0 | `test_l0_contracts.py` | Schemas and contracts — shape of the API and events |
| L1 | `test_l1_unit.py` | Pure units |
| L2 | `test_l2_http.py`, `test_l2_integration.py` | HTTP surface and wired-together components |
| L3 | `test_l3_scenarios.py` | End-to-end user scenarios |
| L4 | `test_l4_chaos.py` | Kill the backend mid-stream, fill the disk, interrupt transactions |
| Perf | `test_perf_budgets.py` | Millisecond budgets; `turn_accepted` (50ms) is the one that matters |

Single file: append the path. Single test: `-k <name>`. Use `-x` when triaging so
you stop at the first failure instead of reading 40 cascading ones.

**Frontend — typecheck only:**

```bash
npm --prefix v2/frontend run typecheck
```

**There is no frontend unit-test runner, no Vitest, no Playwright, no visual
regression tooling.** This is the single most important fact about this repo's
test coverage. Domains 1, 2, 3 and 11 (UI, Visual, Frontend Logic, Accessibility —
80 of the 300 capabilities) have **no automated harness**. Don't pretend otherwise
and don't write tests against a runner that isn't installed.

What you do instead: drive the running app through the Browser pane. That covers
most of those 80 capabilities for real, against real rendered output, which is
often better evidence than a jsdom assertion anyway. See `references/frontend.md`.

If a change genuinely needs regression protection that only a unit runner can
give, propose adding Vitest and let the user decide — don't add it silently.

**Running the app** (`preview_start`, never Bash — a dev server under Bash will hang):

| Name | Port | Use |
|---|---|---|
| `primnox-v2-frontend` | 5273 | The V2 UI |
| `primnox-v2-backend` | 4109 | Real backend |
| `primnox-v2-backend-echo` | 4109 | **Deterministic model output** — use this whenever the assertion is about the app, not the model |

The echo backend is the highest-leverage tool here. Any UI or flow test against a
live model is testing the model's mood as much as your code; against echo it tests
your code.

## Routing: what changed → what to check

Match on the paths in the diff. When several rows match, the union applies.

| Changed path | Domains to consider |
|---|---|
| `v2/frontend/src/components/**` | UI (1), Visual (2), Frontend Logic (3), Accessibility (11) |
| `v2/frontend/src/lib/**`, hooks, state | Frontend Logic (3), Reliability (6) |
| `v2/backend/primnox2/app.py`, routes | Backend/API (4), Security (7), Observability (13) |
| `kernel/scheduler.py`, `kernel/events.py` | Backend (4), Performance (5), Reliability (6), Observability (13) |
| `storage/db.py`, `storage/vault.py` | Data Integrity (15), Security (7), Reliability (6), Privacy (16) |
| `models/gateway.py` | AI Systems (8), Performance (5), Backend (4) |
| `privacy/**` | Privacy (16), Security (7), AI Systems (8) |
| `settings/service.py` | Backend (4), UI settings persistence (1), Data Integrity (15) |
| `src-tauri/**`, `.github/workflows/**` | Installer (12), CI/CD (14), Security (7) |
| Dependency or lockfile changes | Security (7), CI/CD (14), Performance (5) |

Two selection rules worth internalizing:

**Widen on shared infrastructure.** Changes to the event bus, the scheduler, or the
database touch everything downstream. Their diffs look small and their blast radius
isn't. L4 chaos and perf budgets earn their runtime here specifically.

**Narrow on leaves.** A change to one component's hover state does not warrant the
backend suite. Selecting three checks and saying why you skipped the rest is a
better answer than running everything.

## Reference files

Read the one that matches your selected domains. Each is self-contained.

| File | Covers |
|---|---|
| `references/catalog.md` | All 300 capabilities, numbered, with how to check each |
| `references/backend.md` | Domains 4, 5, 6, 15 — pytest harness, fixtures, chaos and perf patterns |
| `references/frontend.md` | Domains 1, 2, 3, 11 — Browser-pane driven UI, visual, logic, a11y |
| `references/ai-systems.md` | Domain 8 — memory, context, tools, routing, hallucination, prompt injection |
| `references/security.md` | Domains 7, 16 — injection, secrets, authz, CSRF/CSP, PII, retention |
| `references/platform.md` | Domains 9, 10, 12, 13, 14 — hardware, filesystem, installer, observability, CI/CD |

## Evidence discipline

The rules that keep this skill trustworthy:

- **Never report a pass without the output that proves it.** "Tests pass" with no
  command output is an assertion, not a result.
- **Never report a fix as verified without re-running the failing reproduction.**
  A fix that compiles is not a fix that works.
- **Report failures plainly, including your own.** If a check couldn't run — missing
  dependency, no harness, environment problem — that is a finding about coverage, and
  it's more valuable surfaced than swallowed.
- **Distinguish "passed" from "not checked".** Silence on a domain reads as a pass.
  Say which domains you skipped and why.
- **Don't fix and report in the same breath without separating them.** The user needs
  to know what was broken independently of what you did about it.

## Report format

Lead with the verdict. Engineers read the first three lines and skim the rest.

```markdown
## Verdict
<Ship / Don't ship / Ship with caveats> — one sentence why.

## Scope
Changed: <what>
Domains selected: <names + numbers>
Skipped: <domains> — <why>

## Findings

### [SEV] Title
- **Severity**: Critical | High | Medium | Low
- **Confidence**: High | Medium | Low — <what makes it uncertain>
- **Evidence**: <output, screenshot, trace — the actual artifact>
- **Reproduction**:
  1. <exact steps or command>
- **Probable cause**: <file:line and the mechanism>
- **Suggested fix**: <what would resolve it>

## Passed
<checks run that found nothing, so the reader knows what's covered>
```

Severity is about user impact, not effort to fix. Data loss and security holes are
Critical even when the fix is one line. Confidence is separate on purpose: a
high-severity, low-confidence finding is worth reporting, and conflating the two
either buries real bugs or cries wolf.
