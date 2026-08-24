# Frontend: UI, visual, logic, accessibility

Covers domains 1 (UI & Interaction), 2 (Visual Validation), 3 (Frontend Logic),
and 11 (Accessibility) — 80 of the 300 capabilities.

## Start here: there is no test runner

`frontend/package.json` has three scripts — `dev`, `build`, `typecheck` — and no
test dependency. No Vitest, no Jest, no Playwright, no visual-regression tooling.

```bash
npm --prefix frontend run typecheck
```

That is the entire automated frontend gate. It catches type errors and nothing else.

Two consequences, both worth stating out loud in any report:

1. **Don't write tests against a runner that isn't installed.** A `.test.tsx` file in
   this repo is dead code that nothing executes and that reads, to the next person,
   like coverage that exists.
2. **Don't report frontend capabilities as passing when nothing ran.** "Not checked —
   no harness" is a finding about coverage. It's useful. A false green isn't.

If a change needs regression protection that only a unit runner provides, propose
adding Vitest and let the user decide. Adding a test framework changes the project's
dependency surface and CI, which isn't a call to make silently mid-task.

## What you use instead

Drive the actual running app through the Browser pane. For UI, visual, and
accessibility work this is frequently *better* evidence than jsdom: you're asserting
against real layout, real styles, and the real accessibility tree, rather than
against a simulation of them.

Start the app with `preview_start` — never Bash, which will hang on a dev server:

| Name | Port | When |
|---|---|---|
| `primnox-v2-frontend` | 5273 | Always, for UI work |
| `primnox-v2-backend` | 4109 | When you need the real model |
| `primnox-v2-backend-echo` | 4109 | **Default for UI testing** — deterministic output |

Reach for the echo backend by default. A UI assertion made against a live model is
partly testing the model's mood; against echo, the only variable is your code. Flaky
UI tests are very often just this mistake.

## `read_page` before `screenshot`

`read_page` returns the accessibility tree with `ref_N` handles. Prefer it for
anything about text, structure, state, or naming — it's cheaper than a screenshot,
it's precise, and the refs feed straight into `computer` and `form_input`.

Screenshots are for what only pixels can show: alignment, spacing, shadows, theme
appearance, focus rings.

This ordering matters for accessibility especially. If a control is missing from
`read_page` or shows up unnamed, a screen reader user cannot operate it — and that's
invisible in a screenshot that looks perfect. Icon-only controls losing their
accessible names has been a real defect in this repo more than once.

## Computed styles beat eyeballing

For domain 2, `javascript_tool` gives you objective assertions where screenshots give
you impressions:

- **Overflow (36)**: find any element where `scrollWidth > clientWidth`
- **Spacing / radius / shadow (32–34)**: read `getComputedStyle` and compare against
  the design tokens rather than judging by eye
- **Contrast (233)**: compute the ratio — 4.5:1 for text, 3:1 for UI components
- **Font consistency (29)**: collect `font-family` across nodes and look for strays

Without a baseline image store, true pixel-diffing (27) isn't available. Say that
plainly instead of implying a comparison you didn't make.

## The checks worth running on almost any UI change

Ordered by how often they catch something real:

1. **Keyboard-only pass (232)** — Tab through the whole flow without touching the
   mouse. Assert the order matches the visual order, focus is always visible, Esc
   closes what it should, and nothing traps focus.
2. **Both themes (44, 45)** — `resize_window` with `colorScheme` light and dark.
   Theme bugs cluster in newly-added surfaces because the tokens get hardcoded.
3. **Responsive (40)** — mobile, tablet, desktop. The body must never scroll
   horizontally; wide content scrolls inside its own container.
4. **Console clean (59)** — `read_console_messages`. Hydration mismatches and key
   warnings are cheap to read and point at real bugs.
5. **Network sanity (55, 61)** — `read_network_requests`. Look for 404s on assets,
   and for a burst of identical requests where a debounce should be.

## Frontend logic without a runner

Domain 3 is the hardest to cover this way, because the failures are internal. What
still works:

- **Event listener leaks (49)** and **hook dependency mistakes (47)** are visible by
  *reading* the source — every `addEventListener` needs a matching removal; deps
  arrays that omit a referenced value produce stale closures. Static reading is a
  legitimate check here, just label it as such.
- **Re-render loops (48)** — instrument with `javascript_tool` and count renders
  during an interaction.
- **Memory cleanup (58)** — mount/unmount a route repeatedly and watch the heap.
- **Race conditions (60)** — fire overlapping requests and assert the correct one
  wins. Kill the backend mid-request to force the interleaving.
- **Persistence (51, 63)** — change state, reload, assert what survived is exactly
  what should have.

## Common false findings

Things that look like bugs in the browser pane and aren't:

- **Hover states in mobile viewport** — widths under 768px emulate touch, so hover
  stops producing hover states. Resize to desktop before testing hover.
- **Stale page after an edit** — Vite HMR usually handles it, but if the change
  touched load-time code, reload explicitly before concluding it didn't work.
- **Backend not running** — an empty or erroring UI is usually port 4109 being down,
  not a frontend defect. Check before filing.
