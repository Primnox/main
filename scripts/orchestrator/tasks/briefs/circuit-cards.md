Build `CircuitCards`, a React component that renders the observed history and
current breaker state of each upstream endpoint behind a request router, and
lets the user clear a breaker that is holding an endpoint out of service.

## Domain

Each upstream endpoint sits behind a circuit breaker with three states:

- `closed` — healthy, requests flow.
- `open` — failing, requests are refused without being attempted. The breaker
  reopens for a probe after a cooldown, reported as `opens_in_s`.
- `half_open` — the cooldown has elapsed; the **next request is a probe**. One
  success closes the breaker, one failure reopens it for another cooldown.

Two conditions look similar and must never be conflated:

1. **Cooling down** — a transient failure. Waiting fixes it. A countdown is
   meaningful and the user should be told to wait.
2. **Terminal** (`terminal: true`) — a failure that time does not fix: a
   rejected credential, an exhausted balance, an endpoint that no longer exists.
   A countdown here is a lie. Show the reason, not a timer, and make it clear
   that the user has to change something.

`health_score` is a penalty score derived from breaker *state*, not from the
success rate. Do not present it as "percent of requests that worked" — that is
`success_rate`, a different field that may be `null` when nothing has been
observed yet. Distinguish "no data yet" from "zero".

Resetting a breaker means: the user has just fixed the underlying cause and does
not want to wait out the cooldown. It is the only mutation this component
offers.

## Types

```ts
export type Circuit = {
  key: string;                                   // stable identity
  state: 'closed' | 'open' | 'half_open';
  open: boolean;
  opens_in_s: number;
  trips: number;                                 // times it has opened, ever
  calls: number;
  failures: number;
  consecutive_failures: number;
  error_rate: number;                            // 0..1
  success_rate: number | null;                   // null when never called
  latency_ms: number | null;                     // null when never measured
  health_score: number;                          // 0..1, state-derived penalty
  terminal: boolean;
  reason: string;
  last_error: string;
};

export type CircuitCardsProps = {
  circuits: Circuit[];
  onReset?: (key?: string) => void | Promise<void>;  // omit key to reset all
  busyKeys?: string[];                               // resets in flight
  labelFor?: (key: string) => string;                // key -> display name
  countdownIntervalMs?: number;                      // default in constants
};
```

The component fetches nothing. The parent polls and passes fresh `circuits`.
`opens_in_s` is a snapshot from the last fetch — you must tick it down locally
between refreshes, or the countdown will visibly freeze. Reconcile to the
authoritative value whenever new props arrive; never let local drift accumulate.
Never tick below zero, and when local time runs out, say the probe is due rather
than continuing to count.

## What each card shows

Ordered so the cards demanding attention sort first: terminal, then open, then
half-open, then closed. Ordering rules live in a named constant.

- The endpoint's display name, prominent; the raw `key` available but secondary.
- Its state, in words and by icon, never by colour alone. `half_open` must read
  as "next request is a probe", not as a third shade of broken.
- For a cooling-down breaker: a live countdown, and a progress affordance that
  drains linearly. Wrap the countdown in an `aria-live="polite"` region that is
  not itself recreated on each tick.
- For a terminal breaker: `reason` stated plainly, no countdown, and a clear
  indication that resetting alone will not help unless the cause is fixed.
- Observed history: `calls`, `failures`, `consecutive_failures`, `trips`,
  `error_rate` as a percentage, `success_rate` (or an explicit "not yet called"),
  and `latency_ms` (or "not measured"). Percentages and milliseconds format
  through named helpers, not inline template strings.
- `last_error` when present, clamped to a constant number of lines with the full
  text reachable via `title`.

Include a reset-all control, disabled when nothing is open. Per-card reset
buttons appear only where a reset would do something. Every reset button shows
its in-flight state from `busyKeys` and is disabled while busy — never let a
double-click fire two resets.

## Motion

- Cards enter with a stagger; a card already present must not replay its
  entrance when the poll refreshes. Key by `key`.
- When ordering changes because a breaker tripped, cards move to their new
  position rather than snapping. Use `motion` layout animation.
- The countdown drain is `transform: scaleX()` with `linear` easing — the only
  place linear is correct here.
- A breaker transitioning `open → closed` gets a single confirming transition on
  mount of the new state. It must not loop.
- Reset buttons take `active:scale-[0.97]` with a 160ms transform transition.
- Under `prefers-reduced-motion`, the countdown becomes a numeric readout with
  no drain animation, and layout moves become instant. Keep colour and opacity.

## Deliverables and verification

Write `src/CircuitCards.tsx` and `src/CircuitCards.test.tsx`.

Extract and export as pure functions: the card ordering comparator, the
countdown tick reconciliation (given a snapshot, an elapsed time, and a fresh
snapshot, return the value to display), and the formatters. Test those with the
`node:test` runner and `node:assert/strict`, covering `null` rates, terminal
versus cooling-down, and a countdown reaching zero between refreshes.
