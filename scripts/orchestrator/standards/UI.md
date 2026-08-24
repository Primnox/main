# Engineering standards — UI components

You are implementing a single, self-contained component. The specification is in
`TASK.md`. It is complete on its own — there is no wider application for you to
ask about, and no repository beyond this directory.

## Stack

Fixed. Do not add to it.

- React 18 function components, TypeScript, ESM.
- Tailwind CSS v3 utility classes for layout and spacing.
- `motion` (v12, the package formerly published as `framer-motion`) for any
  JS-driven animation. Import from `motion/react`.
- `lucide-react` for icons.
- No other third-party packages. No CSS-in-JS, no styled-components, no charting
  library, no state manager.

Every file you write is a `.tsx` module exporting named components. No default
exports. Do not write an `index.ts`, a router, an app shell, or a build config.

## Colour

The host application defines its palette as CSS custom properties on `:root` and
swaps them for light and dark. **You must never write a colour literal** — no
hex, no `rgb()`, no Tailwind colour names like `bg-slate-800`. Every colour is a
token reference through a Tailwind arbitrary value:

```tsx
<div className="bg-[var(--color-surface-container)] text-[var(--color-on-surface)]">
```

Available tokens, and what each means:

| Token | Use |
| --- | --- |
| `--color-surface` | page ground |
| `--color-surface-container` | a raised panel on the ground |
| `--color-surface-container-high` | a raised panel on a panel |
| `--color-surface-container-highest` | the topmost raised layer |
| `--color-on-surface` | primary text |
| `--color-on-surface-variant` | secondary and label text |
| `--color-outline` | a border that should be seen |
| `--color-outline-variant` | a divider that should barely be seen |
| `--color-primary` / `--color-on-primary` | the accent and text on it |
| `--color-primary-container` / `--color-on-primary-container` | tinted accent surface |
| `--color-error` / `--color-on-error` | failure |
| `--color-error-container` / `--color-on-error-container` | tinted failure surface |
| `--color-warn` | caution, degraded, cooling down |
| `--color-success` | healthy, passing |

Never assume a token is light or dark. The same class must read correctly in both
themes, which it will if you only ever pair a surface token with its matching
`on-` token.

## Motion

Motion is justified or it is absent. Apply these rules; they are not suggestions.

- **Animate only `transform`, `opacity`, `filter`, and `clip-path`.** Never
  animate `height`, `width`, `margin`, `padding`, or `top`/`left`.
- **Never `transition: all`.** Name the properties.
- **Durations stay under 300ms.** Press feedback 100–160ms, small popovers
  125–200ms, panel-level transitions 200–250ms.
- **Easing.** Entering or exiting → ease-out. Moving or reordering on screen →
  ease-in-out. Colour and hover → ease. Continuous motion (a countdown bar,
  an indeterminate sweep) → linear. **Never `ease-in` on UI.** Use strong custom
  curves, not the CSS built-ins:
  - ease-out: `cubic-bezier(0.23, 1, 0.32, 1)`
  - ease-in-out: `cubic-bezier(0.77, 0, 0.175, 1)`
- **Never animate from `scale(0)`.** Enter from `scale(0.95)` plus `opacity: 0`.
- **Pressable elements get `active:scale-[0.97]`** with a 160ms transform
  transition. Anything clickable must visibly answer the press.
- **Exit faster than enter.** The user is deciding on the way in and the system
  is responding on the way out.
- **Stagger list entrances 30–80ms per item**, and never block interaction while
  a stagger is playing.
- **Prefer CSS transitions to keyframes** for anything that can retrigger before
  it finishes — transitions retarget from their current value, keyframes restart.
- With `motion`, animate the full `transform` string
  (`animate={{ transform: 'translateY(0px)' }}`), not the `x`/`y`/`scale`
  shorthands, which run on the main thread and drop frames under load.
- Gate hover-only effects behind `@media (hover: hover) and (pointer: fine)` —
  in Tailwind, the `hover:` variant plus a `[@media(hover:hover)]:` prefix.
- **Honour `prefers-reduced-motion`.** Use the `useReducedMotion` hook from
  `motion/react`. Reduced motion means keep opacity and colour transitions, drop
  movement and scale. It does not mean no feedback at all.

Data that updates on a poll must not re-run its entrance animation on every
refresh. Key list items by their stable identity, never by array index.

## Data

The component receives all of its data through props. It must not fetch, must
not poll, must not read a global, and must not import a client. A parent owns
loading and refresh; you own rendering and interaction. Callbacks for user
actions arrive as props and are optional — guard every one before calling it.

Render correctly for the empty case, the single-item case, and the
twenty-item case. Long identifiers must truncate, not overflow.

## No hardcoded values

Anything a caller might reasonably want to change is a prop with a default, or a
named constant in one block at the top of the module. Never inline a magic value
at its point of use. This covers thresholds, durations, stagger steps, row
limits, truncation lengths, poll hints, labels, and copy. Numbers that feed a
visual scale (bar widths, opacity ramps) are derived from named constants, not
written twice.

## Accessibility

- Every interactive element is a real `<button>` with an accessible name.
- State conveyed by colour is also conveyed by text or an icon.
- A live countdown updates through `aria-live="polite"` on a wrapper that is not
  itself re-created each tick.
- Focus is visible: `focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]`.

## Output contract

When you finish, write `NOTES.md` with exactly these sections:

```
## What I built
## Assumptions
## Public interface
## How to verify
## Not done
```

`## Public interface` must list every exported symbol with its full prop type.
`## Not done` is required; write `Nothing outstanding.` if the spec is complete.
Never silently drop scope.
