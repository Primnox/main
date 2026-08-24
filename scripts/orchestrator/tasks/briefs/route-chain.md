Build `RouteChain`, a React component that renders the ordered list of upstream
candidates a request router will attempt, in the exact order it will attempt
them, and makes it obvious at a glance which one will actually serve the next
request and why the others will not.

## Domain

A request router fronts several interchangeable upstream endpoints. Before each
request it builds a *chain*: an ordered list of candidates. It walks the chain
from the top and uses the first candidate that is eligible. A candidate can be
ineligible because a circuit breaker in front of it is open, because it has been
administratively denied, because it is out of quota, or because its measured
reliability has collapsed.

Each candidate carries a score in `[0, 1]`. The score is a **product** of nine
independent factors, each also in `[0, 1]`. Because it is a product and not a
weighted sum, any single factor at zero drives the whole score to zero and makes
the candidate ineligible. That property is the most important thing this UI has
to communicate: when a candidate is skipped, exactly one number is responsible,
and the user needs to see which.

The first entry has `origin: 'active'` — it is the endpoint the user explicitly
chose, and it is always tried first regardless of score. Everything below it has
`origin: 'profile'` and is ordered by score descending. Do not visually sort or
re-rank the array you are given; the order you receive is the order the router
will walk.

## Types

Define and export these exactly. Do not rename fields.

```ts
export type RouteStep = {
  provider: string;                    // display label for the endpoint
  model: string;                       // model identifier served there
  key: string;                         // stable identity: endpoint + model
  score: number;                       // 0..1, the product of factors
  eligible: boolean;
  reasons: string[];                   // human-readable notes, may be empty
  factors: Record<string, number>;     // factor name -> 0..1
  origin: 'active' | 'profile';
  local: boolean;                      // runs on this machine, no network
  error?: string;                      // last error seen, if any
};
```

The nine factor keys are `capability`, `allocation`, `health`, `reliability`,
`latency`, `preference`, `cost`, `quota`, `circuit`. Treat this list as data —
put it in a named constant with display labels, and render whatever keys are
actually present rather than assuming all nine arrive.

## Props

```ts
export type RouteChainProps = {
  steps: RouteStep[];
  selectedKey?: string | null;         // controlled highlight
  onSelect?: (key: string) => void;    // a row was activated
  maxVisible?: number;                 // collapse past this, default in constants
  busy?: boolean;                      // parent is refreshing
};
```

The component fetches nothing and polls nothing.

## What each row shows

- Its position in the walk order, as an ordinal.
- The endpoint label, prominent; the model identifier, secondary and truncating.
- A badge when `origin === 'active'` reading that the user chose it, and a
  distinct badge when `local` is true.
- The score, both as a number to two decimals and as a proportional bar.
- For an ineligible row: **the single named factor that is zero**, stated in
  words — not the full factor table, and not a generic "unavailable". If more
  than one factor is zero, name the first in a defined precedence order held in
  a constant. If none is exactly zero but the row is still ineligible, fall back
  to the first entry of `reasons`, and only then to a generic label.
- `error` when present, truncated to a constant length, full text in `title`.

Exactly one row is the one that will serve: the first with `eligible === true`.
Mark it unmistakably and state it in text, not by colour alone. If no row is
eligible, say so in a distinct empty-ish state — that is a real and important
condition, not an error.

Ineligible rows stay legible. Do not drop them below 60% opacity; the user
opened this panel specifically to read them.

## Interaction and motion

- Rows are buttons when `onSelect` is supplied and inert `<li>` elements when it
  is not. Never render a dead button.
- Rows enter with a stagger. The list re-renders on every parent refresh, so
  entrance animation must run on genuinely new keys only — a row that was
  already present must not replay it.
- When the order changes between refreshes, rows move to their new positions
  rather than snapping. Use `motion` layout animation, keyed by `key`.
- The score bar animates its width via `transform: scaleX()`, never `width`.
- Collapse beyond `maxVisible` behind a disclosure that names how many are
  hidden. Expanding animates opacity and transform only.

## Deliverables and verification

Write `src/RouteChain.tsx` and `src/RouteChain.test.tsx`. Test with the
`node:test` runner plus `@testing-library/react` **only if** you can do so
without adding dependencies; if you cannot, write the tests as pure functions
over the helper logic you extract (blocking-factor selection, ordinal
formatting, the serving-row predicate) and say so in `NOTES.md`. Extract that
logic into exported pure functions regardless — it is the part worth testing.
