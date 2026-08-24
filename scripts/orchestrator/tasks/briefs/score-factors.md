Build `ScoreFactors`, a React component that explains a single candidate's
routing score by showing the multiplication that produced it.

## Domain

A request router scores each upstream candidate in `[0, 1]`. The score is the
**product** of nine independent factors, each in `[0, 1]`:

`capability × allocation × health × reliability × latency × preference × cost × quota × circuit`

A product, not a weighted sum. This is deliberate and it is the entire point of
the component: a weighted sum would let one strong factor carry a candidate
whose circuit breaker is open, whereas a product cannot — any factor at zero
takes the result to zero. So this component must not render nine bars in a list
and call it done. It must render a *multiplication*, so that a single zero is
visibly fatal and a chain of mild penalties is visibly cumulative.

Two factors are commonly pinned at `1.0` because nothing measures them yet
(`cost` and `quota` in the current deployment). They must still render, clearly
marked as not currently measured rather than hidden — a factor that silently
disappears is worse than one that says it is inert.

## Types

```ts
export type FactorEntry = {
  name: string;      // e.g. 'reliability'
  value: number;     // 0..1
};

export type ScoreFactorsProps = {
  factors: Record<string, number>;
  total?: number;              // the router's own product; see below
  inertFactors?: string[];     // names to mark "not measured", default in constants
  labels?: Record<string, string>;      // display names, default in constants
  descriptions?: Record<string, string>; // one-line meanings, default in constants
  dense?: boolean;             // compact layout for embedding in a row
};
```

Compute the product yourself from `factors`. If `total` is supplied and differs
from your computed product by more than a named epsilon constant, render the
router's `total` as authoritative and surface the discrepancy visibly — a silent
mismatch between what the router decided and what this panel shows would make
the panel worse than useless. Do not throw.

## What it renders

A left-to-right (or top-to-bottom when `dense`) sequence of factor cells joined
by multiplication signs, terminating in an equals sign and the final score.

Each factor cell carries:
- its display label,
- its value to two decimals,
- a proportional fill representing the value,
- a one-line description available on hover and focus, sourced from
  `descriptions` — this is the only place the meaning of `allocation` or
  `capability` is ever explained, so it must be reachable by keyboard.

Classify each factor into a band and style accordingly — a zero factor, a
severe penalty, a mild penalty, and a neutral `1.0` must be distinguishable
without reading the number. Band thresholds live in a named constant, not
inline. A factor marked inert renders in the neutral band with an explicit
"not measured" affordance regardless of its value.

The running product is worth showing: as the eye moves along the sequence, the
cumulative value after each factor communicates where the score actually died.
Render it subtly beneath the operators rather than as a second row of numbers
competing with the first.

When any factor is zero, the final score cell states in words that this
candidate cannot serve, and names the responsible factor.

## Motion

- Factor fills animate in with a stagger on mount, via `transform: scaleX()`.
- On a data refresh, fills transition to their new value; they do not restart
  from zero. Key by factor name.
- The hover/focus description is a tooltip-grade transition: 125–200ms,
  ease-out, entering from `scale(0.97)` and `opacity: 0`, with
  `transform-origin` at the trigger rather than the centre.
- The zero-factor treatment may pulse **once** on mount and must not loop. A
  looping alarm in a panel someone leaves open is hostile.

## Deliverables and verification

Write `src/ScoreFactors.tsx` and `src/ScoreFactors.test.tsx`.

Extract and export as pure functions: the product computation, the band
classification, and the running-product sequence. Test those directly with the
`node:test` runner and `node:assert/strict` — including the zero case, the
all-ones case, the epsilon-mismatch case, and an empty `factors` object.
