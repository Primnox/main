Build `RouteFlow`, a compact inline SVG diagram showing the path a request takes
through an ordered chain of upstream candidates: which ones it is refused by,
which one serves it, and what lies beyond if that one also fails.

This is the overview that sits above a detailed table. It is glanceable, not
exhaustive. If a reader has to study it, it has failed.

## Domain

A request router holds an ordered list of candidates and walks it top to bottom,
using the first eligible one. Ineligible candidates are skipped without being
called. The diagram must make three things readable in about one second:

1. Where the request actually lands.
2. How many candidates it had to skip to get there, and why each was skipped.
3. What remains as fallback depth *after* the serving candidate — a chain with
   no remaining fallbacks is a fragile chain, and that is worth seeing before it
   matters rather than after.

## Types

```ts
export type FlowStep = {
  key: string;
  label: string;              // endpoint display name
  model: string;
  eligible: boolean;
  score: number;              // 0..1
  local: boolean;
  origin: 'active' | 'profile';
  blockedBy?: string | null;  // the factor that made it ineligible
};

export type RouteFlowProps = {
  steps: FlowStep[];
  orientation?: 'horizontal' | 'vertical';  // default in constants
  onSelect?: (key: string) => void;
  selectedKey?: string | null;
  compact?: boolean;
};
```

## Rendering

Inline SVG, authored by hand. No charting library, no D3, no canvas.

The SVG must be responsive: set a `viewBox`, omit fixed `width`/`height`
attributes, and let CSS size it. It must render correctly from roughly 320px to
900px wide. In `horizontal` orientation past a candidate count held in a named
constant, either switch to vertical automatically or scroll horizontally inside
its own container — the parent must never gain a horizontal scrollbar.

Structure: an origin marker for the incoming request, then one node per
candidate in walk order, connected by edges.

- **Skipped candidates** — the edge passes *through* them and continues. Render
  the node as bypassed, and label the edge with `blockedBy`. The visual grammar
  should read as "the request did not stop here".
- **The serving candidate** — the first eligible one. The edge terminates here.
  This node is the visual anchor of the whole diagram and must be unmistakable
  at a glance, distinguished by shape and weight as well as colour.
- **Remaining candidates** — everything after the serving one. Render them
  attached by a visibly provisional edge (dashed, lighter) to say "only if that
  one fails too". Never draw them as though traffic reaches them.
- **No eligible candidate** — the edge terminates in an explicit failure
  terminal. This is a real state and needs its own deliberate rendering, not a
  diagram that simply runs off the end.

Each node carries its label, a `local` marker when applicable, and an `active`
marker for `origin === 'active'`. Score belongs on the node only when not
`compact`. Long labels truncate with an SVG `<title>` carrying the full text.

Colour comes only from the CSS custom property tokens. SVG strokes and fills
take `stroke="var(--color-outline)"` and similar — never a literal.

## Accessibility

An SVG diagram that is only a picture is not acceptable here.

- `role="img"` on the root with an `aria-label` summarising the path in one
  sentence, generated from the data.
- A visually hidden ordered list mirroring the same information for screen
  readers, so the content is not colour- or shape-dependent.
- When `onSelect` is supplied, nodes are focusable and keyboard-activatable with
  a visible focus ring. Use real `<button>` elements overlaid on the SVG, or SVG
  elements with correct roles and key handlers — either is fine, but tab order
  must follow walk order.

## Motion

- On mount, the path draws in: animate `stroke-dashoffset` from the path length
  to zero, ease-out, under 300ms total including any stagger.
- Nodes fade and scale in from `0.95` behind the advancing edge, staggered
  30–80ms.
- On a data refresh, the diagram transitions to its new shape; it does not
  redraw from scratch. Key nodes by `key`.
- When the serving candidate changes between refreshes, that transition is the
  one moment worth emphasising — give it a single deliberate transition, not a
  loop.
- Under `prefers-reduced-motion`, the path is drawn immediately and only opacity
  transitions remain.

## Deliverables and verification

Write `src/RouteFlow.tsx` and `src/RouteFlow.test.tsx`.

Extract and export as pure functions: the layout solver (given step count,
orientation, and viewport width, return node coordinates and the viewBox), the
serving-index resolver, and the `aria-label` sentence generator. Test those with
the `node:test` runner and `node:assert/strict`, covering an empty chain, a
one-candidate chain, a chain where nothing is eligible, and a chain long enough
to trigger the orientation switch.
